import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
PUBLIC_DIR = ROOT / "public"
DATA_DIR.mkdir(exist_ok=True)
PUBLIC_DIR.mkdir(exist_ok=True)

NUM_RE = re.compile(r"[-+]?\d+(?:[\s,]\d{3})*(?:[.,]\d+)?|[-+]?\d+(?:[.,]\d+)?")


def clean(x):
    if x is None:
        return ""
    return re.sub(r"\s+", " ", str(x).replace("\xa0", " ")).strip()


def to_num(x):
    s = clean(x).replace("%", "").replace("UZS", "")
    m = NUM_RE.search(s)
    if not m:
        return None
    n = m.group(0).replace(" ", "")
    if "," in n and "." in n:
        n = n.replace(",", "")
    elif "," in n:
        parts = n.split(",")
        if len(parts[-1]) == 3 and len(parts) > 1:
            n = "".join(parts)
        else:
            n = n.replace(",", ".")
    try:
        return float(n)
    except Exception:
        return None


def all_nums(text):
    out = []
    for m in NUM_RE.finditer(clean(text)):
        val = to_num(m.group(0))
        if val is not None:
            out.append((m.group(0), val, m.start()))
    return out


def load_config():
    cfg_path = ROOT / "tci_config.json"
    return json.loads(cfg_path.read_text(encoding="utf-8"))


def has_ticker(text, tickers):
    u = clean(text).upper()
    for t in sorted(tickers, key=len, reverse=True):
        if re.search(rf"(?<![A-Z0-9]){re.escape(t)}(?![A-Z0-9])", u):
            return t
    return None


def number_after_label(text, labels):
    txt = clean(text)
    upper = txt.upper()
    for label in labels:
        p = upper.find(label.upper())
        if p >= 0:
            part = txt[p + len(label):]
            nums = all_nums(part)
            if nums:
                return nums[0][1]
    return None


def pick_price(raw, ticker):
    txt = clean(raw)

    # Best source on UZSE asking_prices table.
    labelled = number_after_label(txt, ["Best Sell Price", "Best Buy Price", "Last Price", "Close Price", "Price"])
    if labelled is not None:
        return labelled

    pos = txt.upper().find(ticker.upper())
    after = txt[pos + len(ticker):] if pos >= 0 else txt
    nums = all_nums(after)
    if not nums:
        return None

    uzs_pos = after.upper().find("UZS")
    if uzs_pos >= 0:
        nums_after_uzs = [(tok, val, p) for tok, val, p in nums if p > uzs_pos]
        if nums_after_uzs:
            return nums_after_uzs[0][1]

    for tok, val, _ in nums:
        if ("." in tok or "," in tok) and 0 < val < 1_000_000_000:
            return val

    for _, val, _ in nums:
        if val > 0 and val not in range(1, 101) and val not in range(1900, 2101):
            return val
    return None


def extract_row(row, ticker, source):
    raw = " | ".join(f"{clean(k)}: {clean(v)}" for k, v in row.items())
    lower = {clean(k).lower(): v for k, v in row.items()}

    def by_name(words):
        for k, v in lower.items():
            if any(w in k for w in words):
                n = to_num(v)
                if n is not None:
                    return n
        return None

    # Force UZSE asking rows to use explicit Best Sell/Buy label from the full raw row.
    price = pick_price(raw, ticker)
    if price is None:
        price = by_name(["close", "last", "price", "цена", "narx", "quotation"])

    prev_close = by_name(["prev", "previous", "oldingi", "пред", "закр"])
    volume = by_name(["volume", "quantity", "объем", "количество", "hajm"])
    trades = by_name(["trades", "deals", "transactions", "битим", "сдел"])
    traded_value = by_name(["value", "сумма", "стоимость", "qiymat"])

    daily_return = None
    if price is not None and prev_close not in (None, 0):
        daily_return = price / prev_close - 1

    return {
        "date": str(date.today()),
        "ticker": ticker,
        "price": price,
        "prev_close": prev_close,
        "daily_return": daily_return,
        "volume": volume,
        "trades": trades,
        "traded_value": traded_value,
        "source": source,
        "raw": raw[:700],
    }


def parse_source(url, tickers):
    headers = {"User-Agent": "Mozilla/5.0 TCI Data Engine"}
    html = requests.get(url, headers=headers, timeout=30).text
    rows = []

    try:
        tables = pd.read_html(html)
    except Exception:
        tables = []

    for df in tables:
        df.columns = [clean(c) for c in df.columns]
        for _, r in df.iterrows():
            d = {clean(c): r[c] for c in df.columns}
            txt = " ".join(clean(v) for v in d.values())
            t = has_ticker(txt, tickers)
            if t:
                rows.append(extract_row(d, t, url))

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["tr", "li"]):
        txt = clean(tag.get_text(" "))
        t = has_ticker(txt, tickers)
        if t:
            rows.append(extract_row({"raw": txt}, t, url))

    return rows


def price_score(row):
    src = row.get("source", "")
    price = row.get("price")
    if price is None or price == 1:
        return -1
    if "asking_prices" in src:
        return 100
    if "isu_infos" in src:
        return 10
    return 1


def merge(rows, tickers):
    out = {t: {
        "date": str(date.today()), "ticker": t, "price": None, "prev_close": None,
        "daily_return": None, "volume": None, "trades": None, "traded_value": None,
        "source": "", "raw": "", "_score": -1
    } for t in tickers}

    for r in rows:
        t = r["ticker"]
        if t not in out:
            continue
        cur = out[t]
        sc = price_score(r)
        if sc > cur.get("_score", -1):
            cur["price"] = r.get("price")
            cur["raw"] = r.get("raw") or cur["raw"]
            cur["_score"] = sc
        if r.get("prev_close") is not None:
            cur["prev_close"] = r["prev_close"]
        if r.get("daily_return") is not None:
            cur["daily_return"] = r["daily_return"]
        for f in ["volume", "trades", "traded_value"]:
            if r.get(f) is not None:
                cur[f] = (cur[f] or 0) + r[f]
        if r.get("source") and r["source"] not in cur["source"]:
            cur["source"] = (cur["source"] + "; " + r["source"]).strip("; ")
        if r.get("raw") and not cur["raw"]:
            cur["raw"] = r["raw"]

    for item in out.values():
        item.pop("_score", None)
    return list(out.values())


def main():
    cfg = load_config()
    tickers = [x.upper() for x in cfg["tickers"]]
    sources = cfg["sources"]
    base_value = float(cfg.get("base_value", 10000))

    found = []
    for url in sources:
        try:
            print("Reading", url)
            part = parse_source(url, tickers)
            print("Found", len(part), "rows")
            found.extend(part)
        except Exception as e:
            print("Source error", url, type(e).__name__, e)

    rows = merge(found, tickers)
    active = [r for r in rows if r["daily_return"] is not None]
    daily = sum(r["daily_return"] for r in active) / len(active) if active else 0

    latest = {
        "date": str(date.today()),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "base_value": base_value,
        "tci_value": round(base_value * (1 + daily), 4),
        "daily_return": round(daily, 8),
        "constituents_count": len(rows),
        "active_price_count": len([r for r in rows if r["price"] is not None]),
        "active_return_count": len(active),
        "constituents": rows,
        "source_note": "Data parsed from public UZSE pages. Verify before publication."
    }

    pd.DataFrame(rows).to_csv(DATA_DIR / "raw_uzse_latest.csv", index=False, encoding="utf-8-sig")
    (PUBLIC_DIR / "tci_latest.json").write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("TCI latest saved:", latest["tci_value"])
    print("Active prices:", latest["active_price_count"])


if __name__ == "__main__":
    main()
