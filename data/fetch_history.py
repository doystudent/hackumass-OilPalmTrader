"""Download monthly price history for every traded company in
trading/malaysia_agriculture_companies.csv (the same list the trader uses).

Run:  docker compose run --rm stock history

Yahoo Finance lists Bursa Malaysia stocks under their numeric stock code
(for example 5285.KL), so yahoo_tickers.csv maps each Bursa ticker from the
companies file (SDG, IOICORP, ...) to its Yahoo symbol. A company that has no
row in yahoo_tickers.csv is reported and skipped. Delisted companies stay in
the table with status N/A, since there is nothing to download for them.

Output: data/stock_history/<BURSA_TICKER>.csv with columns date,close
        (one row per month, dated the 1st, adjusted for dividends and splits)
        data/stock_history/_summary.csv with what was downloaded and when.
"""
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import yfinance as yf

HERE = Path(__file__).resolve().parent
COMPANIES_FILE = HERE.parent / "trading" / "malaysia_agriculture_companies.csv"
TICKER_FILE = HERE / "yahoo_tickers.csv"
OUT_DIR = HERE / "stock_history"
WORKERS = 25          # a few at a time; too many parallel requests get refused by Yahoo
ATTEMPTS = 2
IGNORED_WORDS = {"berhad", "bhd", "holdings", "group", "corporation", "corp", "malaysia", "the"}


def name_words(name):
    words = re.findall(r"[a-z0-9]+", str(name).lower())
    return {w for w in words if w not in IGNORED_WORDS}


def names_match(expected, yahoo_name):
    """True when Yahoo's company name shares a meaningful word with the name we expect."""
    return bool(name_words(expected) & name_words(yahoo_name))


def is_traded(ticker):
    """Same rule as the trader: skip blanks, "N/A" and anything marked delisted."""
    return bool(ticker) and ticker != "N/A" and "elisted" not in ticker


def load_companies():
    """Every company from the trader's list, each with its Yahoo symbol ("" when not mapped yet)."""
    companies = pd.read_csv(COMPANIES_FILE, dtype=str).fillna("")
    companies.columns = [c.strip() for c in companies.columns]
    companies = companies.rename(columns={"Company Name": "company", "Bursa Ticker": "bursa_ticker",
                                          "Primary Products/Activities": "products"})
    for column in ("company", "bursa_ticker", "products"):
        companies[column] = companies[column].str.strip()

    symbols = pd.read_csv(TICKER_FILE, dtype=str).fillna("")
    symbols = symbols.apply(lambda col: col.str.strip())
    lookup = dict(zip(symbols["bursa_ticker"], symbols["yahoo_symbol"]))
    companies["yahoo_symbol"] = companies["bursa_ticker"].map(lookup).fillna("")
    return companies[["company", "products", "bursa_ticker", "yahoo_symbol"]].to_dict("records")


def fetch_one(row):
    """Download one company's monthly history. Returns a dict describing the result."""
    result = {"company": row["company"], "products": row["products"],
              "bursa_ticker": row["bursa_ticker"], "yahoo_symbol": row["yahoo_symbol"],
              "yahoo_name": "", "months": 0, "first_month": "", "last_month": "", "status": ""}
    if not is_traded(row["bursa_ticker"]):
        result["yahoo_symbol"] = ""
        result["status"] = "N/A"
        return result
    if not row["yahoo_symbol"]:
        result["status"] = "NO YAHOO SYMBOL"
        return result
    error = "no data returned"
    for attempt in range(ATTEMPTS):
        try:
            ticker = yf.Ticker(row["yahoo_symbol"])
            history = ticker.history(period="max", interval="1mo", auto_adjust=True)
            closes = history["Close"].dropna()
            if closes.empty:
                raise ValueError("no data returned")

            # Date every row to the first of its month, to line up with the palm oil months in main.py.
            dates = pd.to_datetime(closes.index).tz_localize(None).to_period("M").to_timestamp()
            monthly = pd.DataFrame({"date": dates, "close": closes.to_numpy()})
            monthly = monthly.drop_duplicates("date", keep="last").sort_values("date")

            # The current month is not finished yet, so its "monthly" price would be misleading.
            this_month = pd.Timestamp.today().to_period("M").to_timestamp()
            monthly = monthly[monthly["date"] < this_month]
            if monthly.empty:
                raise ValueError("no complete months returned")

            metadata = ticker.history_metadata or {}
            result["yahoo_name"] = metadata.get("longName") or metadata.get("shortName") or ""

            monthly["close"] = monthly["close"].round(4)
            monthly.to_csv(OUT_DIR / f"{row['bursa_ticker']}.csv", index=False, date_format="%Y-%m-%d")
            result["months"] = len(monthly)
            result["first_month"] = monthly["date"].iloc[0].strftime("%Y-%m")
            result["last_month"] = monthly["date"].iloc[-1].strftime("%Y-%m")
            if not result["yahoo_name"]:
                result["status"] = "ok (Yahoo gave no name to check)"
            elif names_match(row["company"], result["yahoo_name"]):
                result["status"] = "ok"
            else:
                result["status"] = "CHECK NAME"
            return result
        except Exception as e:  # network errors, unknown symbols, empty replies
            error = str(e).splitlines()[0][:80] if str(e) else type(e).__name__
            if attempt + 1 < ATTEMPTS:
                time.sleep(2)
    result["status"] = f"FAILED: {error}"
    return result


def print_table(results):
    # Same layout as the trader's table: a [n/total] counter, then one padded column per field.
    total = len(results)
    digits = len(str(total))
    company_w = max(len("Company"), max(len(r["company"]) for r in results))
    products_w = max(len("Products"), max(len(r["products"]) for r in results))
    ticker_w = max(len("Ticker"), max(len(r["bursa_ticker"]) for r in results))
    yahoo_w = max(len("Yahoo"), max(len(r["yahoo_symbol"]) for r in results))

    indent = " " * (digits * 2 + 4)   # width of "[ 1/25] "
    header = (f"{indent}{'Company':<{company_w}}  {'Products':<{products_w}}  {'Ticker':<{ticker_w}}  "
              f"{'Yahoo':<{yahoo_w}}  {'Months':>6}  {'From':<7}  {'To':<7}  Status")
    print()
    print(header)
    print("-" * (len(header) + 12))
    for i, r in enumerate(results, start=1):
        months = str(r["months"]) if r["months"] else "-"
        print(f"[{i:>{digits}}/{total}] {r['company']:<{company_w}}  {r['products']:<{products_w}}  "
              f"{r['bursa_ticker']:<{ticker_w}}  {r['yahoo_symbol'] or '-':<{yahoo_w}}  {months:>6}  "
              f"{r['first_month'] or '-':<7}  {r['last_month'] or '-':<7}  {r['status']}")
        if r["status"] == "CHECK NAME":
            print(f"{indent}expected '{r['company']}' but Yahoo says '{r['yahoo_name']}'")


def main():
    rows = load_companies()
    OUT_DIR.mkdir(exist_ok=True)

    print(f"Downloading monthly history for {len(rows)} companies ({WORKERS} at a time)...")
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(fetch_one, rows))

    print_table(results)

    summary = pd.DataFrame(results)
    summary["downloaded_on"] = pd.Timestamp.today().strftime("%Y-%m-%d")
    summary.to_csv(OUT_DIR / "_summary.csv", index=False)

    ok = sum(r["status"].startswith("ok") for r in results)
    check = sum(r["status"] == "CHECK NAME" for r in results)
    unmapped = sum(r["status"] == "NO YAHOO SYMBOL" for r in results)
    not_traded = sum(r["status"] == "N/A" for r in results)
    failed = len(results) - ok - check - unmapped - not_traded
    print()
    print(f"{ok} downloaded, {check} to check, {failed} failed, {unmapped} without a Yahoo symbol, "
          f"{not_traded} N/A (not traded). Files are in {OUT_DIR}")
    if unmapped:
        print("NO YAHOO SYMBOL: add a row for that Bursa ticker to yahoo_tickers.csv and run again.")
    if check:
        print("CHECK NAME: the Yahoo symbol may belong to a different company. "
              "Fix the symbol in yahoo_tickers.csv and run again.")
    if failed:
        print("FAILED: the symbol may be wrong, or Yahoo refused the request. "
              "Check yahoo_tickers.csv, wait a minute, and run again.")
    if ok + check == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
