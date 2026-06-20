import csv
import json
import math
import os
import re
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


def build_headers() -> dict[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "uz-UZ,uz;q=0.9,en-US;q=0.8,en;q=0.7,ru;q=0.6",
        "Origin": "https://app.jett.uz",
        "Referer": "https://app.jett.uz/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }
    cookie = os.getenv("JETT_COOKIE", "").strip()
    token = os.getenv("JETT_AUTH_TOKEN", "").strip()
    if cookie:
        headers["Cookie"] = cookie
    if token:
        headers["Authorization"] = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    return headers


def load_config() -> dict[str, Any]:
    return json.loads((ROOT / "tci_config.json").read_text(encoding="utf-8"))


def as_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        num = float(value)
        return num if math.isfinite(num) else None
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
        return num if math.isfinite(num) else None
    except Exception:
        return None


def normalize_ticker(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "")


def fetch_json(session: requests.Session, url: str, *, params: dict[str, Any] | None = None) -> Any:
    r = session.get(url, params=params, headers=build_headers(), timeout=30)
    if r.status_code == 403:
        print("[ERROR] Jett API returned 403 Forbidden.")
        print("[ERROR] GitHub Actions server is blocked or JETT_COOKIE/JETT_AUTH_TOKEN is missing/expired.")
        print("[ERROR] URL:", r.url)
        print("[ERROR] Add repo secret: Settings -> Secrets and variables -> Actions -> JETT_COOKIE")
    r.raise_for_status()
    return r.json()


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


def fetch_all_stocks(session: requests.Session, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    jett = cfg.get("jett", {})
    url = jett.get("stocks_url", "https://api.jett.uz/stockv3")
    limit = int(jett.get("limit", 100))
    offset = 0
    out: list[dict[str, Any]] = []
    seen: set[int] = set()

    while offset <= 2000:
        params = {
            "offset": offset,
            "limit": limit,
            "period": jett.get("period", "today"),
            "sort_by": jett.get("sort_by", "gross_trade_amount"),
            "order_by": jett.get("order_by", "desc"),
            "query": "",
        }
        payload = fetch_json(session, url, params=params)

        if offset == 0:
            print(f"[DEBUG] payload type: {type(payload).__name__}")
            if isinstance(payload, dict):
                print(f"[DEBUG] payload keys: {list(payload.keys())}")
            items_raw = unwrap_items(payload)
            if items_raw:
                first = items_raw[0]
                print(f"[DEBUG] first item keys: {list(first.keys())}")
                print(f"[DEBUG] first item: {json.dumps(first, ensure_ascii=False)[:600]}")
            else:
                print("[DEBUG] unwrap_items returned EMPTY!")
                print(f"[DEBUG] raw payload: {json.dumps(payload, ensure_ascii=False)[:800]}")

        items = unwrap_items(payload)
        if not items:
            print(f"[DEBUG] No items at offset={offset}, stopping.")
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

    print(f"[DEBUG] Total stocks fetched: {len(out)}")
    return out


def stock_name(item: dict[str, Any]) -> str:
    for key in ["issue_name", "name", "company_name", "issuer_name", "title"]:
        val = item.get(key)
        if val:
            return str(val)
    return ""


def price_from_dict(d: dict[str, Any]) -> float | None:
    for key in [
        "last_price", "lastPrice", "current_price", "currentPrice", "close_price", "closePrice",
        "price", "narx", "rate", "value", "best_price", "bestPrice",
        "best_sell_price", "bestSellPrice", "best_buy_price", "bestBuyPrice",
        "sell_price", "sellPrice", "buy_price", "buyPrice",
    ]:
        if key in d:
            n = as_number(d.get(key))
            if n is not None and n > 0:
                return n
    return None


def extract_price_from_text(text: str) -> float | None:
    patterns = [
        r"Best Sell Price:\s*UZS\s*([0-9 ,.]+)",
        r"Best Buy Price:\s*UZS\s*([0-9 ,.]+)",
        r"price[^0-9]{0,20}([0-9]+(?:[.,][0-9]+)?)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            n = as_number(m.group(1))
            if n is not None and n > 0:
                return n
    return None


def extract_price_from_rows(rows: list[Any], side: str) -> float | None:
    prices: list[float] = []
    for row in rows:
        p = None
        if isinstance(row, dict):
            p = price_from_dict(row)
        elif isinstance(row, (list, tuple)) and row:
            nums = [as_number(x) for x in row]
            nums = [x for x in nums if x is not None and x > 0]
            if nums:
                p = max(nums)
        if p is not None and p > 0:
            prices.append(p)
    if not prices:
        return None
    return min(prices) if side == "ask" else max(prices)


def find_order_lists(obj: Any, side: str) -> list[list[Any]]:
    lists: list[list[Any]] = []
    if isinstance(obj, dict):
        for key, val in obj.items():
            k = str(key).lower()
            if isinstance(val, list):
                if side == "ask" and any(w in k for w in ["ask", "sell", "offer", "sot"]):
                    lists.append(val)
                if side == "bid" and any(w in k for w in ["bid", "buy", "xarid"]):
                    lists.append(val)
            if isinstance(val, (dict, list)):
                lists.extend(find_order_lists(val, side))
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                lists.extend(find_order_lists(item, side))
    return lists


def extract_orderbook_price(payload: Any) -> tuple[float | None, str]:
    if not isinstance(payload, (dict, list)):
        return None, "bad_orderbook"

    if isinstance(payload, dict):
        p = price_from_dict(payload)
        if p is not None:
            return p, "top_level_price"

    for rows in find_order_lists(payload, "ask"):
        p = extract_price_from_rows(rows, "ask")
        if p is not None:
            return p, "best_ask"

    for rows in find_order_lists(payload, "bid"):
        p = extract_price_from_rows(rows, "bid")
        if p is not None:
            return p, "best_bid"

    # Last fallback: search raw JSON text for price-like phrases.
    p = extract_price_from_text(json.dumps(payload, ensure_ascii=False)[:20000])
    if p is not None:
        return p, "text_price"

    return None, "no_price"


def fetch_orderbook(session: requests.Session, cfg: dict[str, Any], stock_id: Any) -> tuple[float | None, dict[str, Any], str]:
    url_template = cfg.get("jett", {}).get("orderbook_url", "https://api.jett.uz/orderbook/{id}")
    url = url_template.format(id=stock_id)
    payload = fetch_json(session, url)
    price, method = extract_orderbook_price(payload)
    wrapped = payload if isinstance(payload, dict) else {"raw": payload}
    return price, wrapped, method


def stock_fallback_price(item: dict[str, Any]) -> float | None:
    return price_from_dict(item)


def build_tci_data() -> dict[str, Any]:
    cfg = load_config()
    wanted = [normalize_ticker(x) for x in cfg.get("tickers", [])]
    session = requests.Session()

    all_stocks = fetch_all_stocks(session, cfg)

    if all_stocks:
        sample = all_stocks[0]
        ticker_candidates = ["ticker", "symbol", "code", "secCode", "isin", "short_name"]
        print("[DEBUG] Ticker field check on first stock:")
        for f in ticker_candidates:
            print(f"  {f}: {sample.get(f)}")

    by_ticker = {normalize_ticker(item.get("ticker")): item for item in all_stocks if normalize_ticker(item.get("ticker"))}

    print(f"[DEBUG] by_ticker count: {len(by_ticker)}")
    print(f"[DEBUG] by_ticker sample keys: {list(by_ticker.keys())[:10]}")
    print(f"[DEBUG] wanted tickers: {wanted}")

    matched = [t for t in wanted if t in by_ticker]
    unmatched = [t for t in wanted if t not in by_ticker]
    print(f"[DEBUG] Matched: {matched}")
    print(f"[DEBUG] Unmatched: {unmatched}")

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
            "last_price": None,
            "current_price": None,
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
                "raw": json.dumps(item, ensure_ascii=False)[:1200],
            })

            fallback = stock_fallback_price(item)
            if fallback is not None:
                row["price"] = fallback
                row["last_price"] = fallback
                row["current_price"] = fallback
                row["price_method"] = "stockv3_price"

            if stock_id is not None:
                try:
                    price, ob_payload, method = fetch_orderbook(session, cfg, stock_id)
                    if price is not None:
                        row["price"] = price
                        row["last_price"] = price
                        row["current_price"] = price
                    row["price_method"] = method
                    row["raw_orderbook"] = json.dumps(ob_payload, ensure_ascii=False)[:1200]
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
        "items": rows,
        "stocks": rows,
        "data": rows,
        "results": rows,
        "source_note": "Live data from Jett public API: stockv3 and orderbook/{id}. If 403, add JETT_COOKIE repository secret.",
    }
    return latest


def save_outputs(latest: dict[str, Any]) -> None:
    rows = latest["constituents"]
    csv_path = DATA_DIR / "raw_jett_latest.csv"
    fields = [
        "date", "ticker", "id", "issue_name", "price", "last_price", "current_price", "price_method",
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
