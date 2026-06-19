import csv
import json
import math
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
PUBLIC_DIR = ROOT / "public"
DATA_DIR.mkdir(exist_ok=True)
PUBLIC_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 TCI Data Engine",
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://app.jett.uz",
    "Referer": "https://app.jett.uz/",
}


def load_config() -> dict[str, Any]:
    return json.loads((ROOT / "tci_config.json").read_text(encoding="utf-8"))


def as_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if math.isfinite(float(value)):
            return float(value)
        return None
    text = str(value).strip().replace("\xa0", " ").replace("UZS", "").replace("%", "")
    text = text.replace(" ", "")
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        num = float(text)
        if math.isfinite(num):
            return num
    except Exception:
        return None
    return None


def normalize_ticker(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def unwrap_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ["results", "data", "items", "stocks", "securities"]:
        val = payload.get(key)
        if isinstance(val, list):
            return [x for x in val if isinstance(x, dict)]
        if isinstance(val, dict):
            nested = unwrap_items(val)
            if nested:
                return nested
    return []


def fetch_json(session: requests.Session, url: str, *, params: dict[str, Any] | None = None) -> Any:
    r = session.get(url, params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.json()


def fetch_all_stocks(session: requests.Session, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    jett = cfg.get("jett", {})
    url = jett.get("stocks_url", "https://api.jett.uz/stockv3")
    limit = int(jett.get("limit", 100))
    offset = 0
    out: list[dict[str, Any]] = []
    seen: set[int] = set()

    while offset <= 1000:
        params = {
            "offset": offset,
            "limit": limit,
            "period": jett.get("period", "today"),
            "sort_by": jett.get("sort_by", "gross_trade_amount"),
            "order_by": jett.get("order_by", "desc"),
            "query": "",
        }
        payload = fetch_json(session, url, params=params)
        items = unwrap_items(payload)
        if not items:
            break

        added = 0
        for item in items:
            stock_id = item.get("id")
            try:
                key = int(stock_id)
            except Exception:
                key = hash(json.dumps(item, ensure_ascii=False, sort_keys=True))
            if key not in seen:
                seen.add(key)
                out.append(item)
                added += 1

        if len(items) < limit or added == 0:
            break
        offset += limit
        time.sleep(0.15)

    return out


def list_from_keys(obj: dict[str, Any], keys: list[str]) -> list[Any]:
    for key in keys:
        val = obj.get(key)
        if isinstance(val, list):
            return val
    return []


def price_from_order_list(rows: list[Any], side: str) -> float | None:
    prices: list[float] = []
    for row in rows:
        price = None
        if isinstance(row, dict):
            for key in ["price", "narx", "rate", "value", "p"]:
                if key in row:
                    price = as_number(row.get(key))
                    break
        elif isinstance(row, (list, tuple)) and row:
            price = as_number(row[0])
        if price is not None and price > 0:
            prices.append(price)
    if not prices:
        return None
    # Sell side: best ask is the lowest sell price. Buy side: best bid is the highest buy price.
    return min(prices) if side == "ask" else max(prices)


def recursive_price_candidates(obj: Any) -> list[float]:
    candidates: list[float] = []
    if isinstance(obj, dict):
        for key, val in obj.items():
            k = str(key).lower()
            if any(word in k for word in ["last_price", "lastprice", "current_price", "close_price", "price", "narx"]):
                n = as_number(val)
                if n is not None and n > 0:
                    candidates.append(n)
            candidates.extend(recursive_price_candidates(val))
    elif isinstance(obj, list):
        for item in obj:
            candidates.extend(recursive_price_candidates(item))
    return candidates


def extract_orderbook_price(payload: Any) -> tuple[float | None, str]:
    if not isinstance(payload, dict):
        return None, "bad_orderbook"

    # 1) Explicit last/current price fields are best if Jett returns them.
    for key in ["last_price", "lastPrice", "current_price", "currentPrice", "price", "close_price", "closePrice"]:
        n = as_number(payload.get(key))
        if n is not None and n > 0:
            return n, key

    # 2) Ask/sell side from orderbook.
    ask_rows = list_from_keys(payload, ["asks", "ask", "sell", "sells", "sell_orders", "sellOrders", "offers"])
    ask = price_from_order_list(ask_rows, "ask")
    if ask is not None:
        return ask, "best_ask"

    # 3) Bid/buy side from orderbook.
    bid_rows = list_from_keys(payload, ["bids", "bid", "buy", "buys", "buy_orders", "buyOrders"])
    bid = price_from_order_list(bid_rows, "bid")
    if bid is not None:
        return bid, "best_bid"

    # 4) Deep fallback for unknown structure.
    candidates = [x for x in recursive_price_candidates(payload) if 0 < x < 1_000_000_000]
    if candidates:
        return candidates[0], "recursive_price"

    return None, "no_price"


def fetch_orderbook(session: requests.Session, cfg: dict[str, Any], stock_id: Any) -> tuple[float | None, dict[str, Any], str]:
    url_template = cfg.get("jett", {}).get("orderbook_url", "https://api.jett.uz/orderbook/{id}")
    url = url_template.format(id=stock_id)
    payload = fetch_json(session, url)
    price, method = extract_orderbook_price(payload)
    return price, payload if isinstance(payload, dict) else {"raw": payload}, method


def stock_name(item: dict[str, Any]) -> str:
    for key in ["issue_name", "name", "company_name", "issuer_name", "title"]:
        val = item.get(key)
        if val:
            return str(val)
    return ""


def build_tci_data() -> dict[str, Any]:
    cfg = load_config()
    wanted = [normalize_ticker(x) for x in cfg.get("tickers", [])]
    wanted_set = set(wanted)
    session = requests.Session()

    all_stocks = fetch_all_stocks(session, cfg)
    by_ticker = {normalize_ticker(item.get("ticker")): item for item in all_stocks if normalize_ticker(item.get("ticker"))}

    rows: list[dict[str, Any]] = []
    found_count = 0

    for ticker in wanted:
        item = by_ticker.get(ticker)
        row = {
            "date": str(date.today()),
            "ticker": ticker,
            "id": None,
            "issue_name": "",
            "price": None,
            "prev_close": None,
            "daily_return": None,
            "percentage": None,
            "volume": None,
            "trades": None,
            "traded_value": None,
            "total": None,
            "source": "jett",
            "price_method": "not_found_in_stockv3",
            "raw": "",
        }

        if item:
            found_count += 1
            stock_id = item.get("id")
            pct = as_number(item.get("percentage"))
            row.update({
                "id": stock_id,
                "issue_name": stock_name(item),
                "daily_return": (pct / 100) if pct is not None else None,
                "percentage": pct,
                "traded_value": as_number(item.get("gross_trade_amount")) or as_number(item.get("total")),
                "total": as_number(item.get("total")),
                "volume": as_number(item.get("volume")) or as_number(item.get("quantity")),
                "trades": as_number(item.get("deals")) or as_number(item.get("trades")),
                "raw": json.dumps(item, ensure_ascii=False)[:900],
            })
            if stock_id is not None:
                try:
                    price, ob_payload, method = fetch_orderbook(session, cfg, stock_id)
                    row["price"] = price
                    row["price_method"] = method
                    if price is not None:
                        row["raw_orderbook"] = json.dumps(ob_payload, ensure_ascii=False)[:900]
                except Exception as e:
                    row["price_method"] = f"orderbook_error:{type(e).__name__}"
                time.sleep(0.12)

        rows.append(row)

    active_returns = [r["daily_return"] for r in rows if r.get("daily_return") is not None]
    daily = sum(active_returns) / len(active_returns) if active_returns else 0
    base_value = float(cfg.get("base_value", 10000))

    latest = {
        "date": str(date.today()),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "jett",
        "base_value": base_value,
        "tci_value": round(base_value * (1 + daily), 4),
        "daily_return": round(daily, 8),
        "constituents_count": len(rows),
        "found_in_stockv3_count": found_count,
        "active_price_count": len([r for r in rows if r.get("price") is not None]),
        "active_return_count": len(active_returns),
        "constituents": rows,
        "source_note": "Live data from Jett public API: stockv3 and orderbook/{id}. Verify before publication.",
    }
    return latest


def save_outputs(latest: dict[str, Any]) -> None:
    rows = latest["constituents"]
    csv_path = DATA_DIR / "raw_jett_latest.csv"
    fields = [
        "date", "ticker", "id", "issue_name", "price", "price_method",
        "percentage", "daily_return", "volume", "trades", "traded_value", "total", "source", "raw",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    (PUBLIC_DIR / "tci_latest.json").write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    latest = build_tci_data()
    save_outputs(latest)
    print("TCI source:", latest["source"])
    print("TCI latest saved:", latest["tci_value"])
    print("Found tickers:", latest["found_in_stockv3_count"])
    print("Active prices:", latest["active_price_count"])


if __name__ == "__main__":
    main()
