"""Backtest: soil-matched companies + palm oil rain signal.

Run:  docker compose run --rm stockFutures backtest [image]

How the pieces fit together:
  1. The soil run (trader --soil) saves the companies that fit the soil in
     trading/soil_matches.csv. Those companies are the pool to choose from.
  2. main.py's rain signal says each month whether to buy, sell or stay out of palm oil.
  3. For every company in the pool we measure how strongly its monthly return
     follows palm oil's (its "palm beta"), using TRAIN_END_YEAR and earlier only.
  4. Strategy: in a month with a BUY signal, hold the TOP_N highest-beta companies
     for the next month. In SELL or neutral months hold cash (no short-selling).
  5. Compare with holding the whole pool all the time, and with main.py's palm oil bot.

Needs the price history from:  docker compose run --rm stock history
"""
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter

import main as palm   # data/main.py: rain + palm oil price loading, features, signal, stats

HERE = Path(__file__).resolve().parent
PALM_FILE = HERE / "climatestatistics.csv"
HISTORY_DIR = HERE / "stock_history"
MATCHES_FILE = HERE.parent / "trading" / "soil_matches.csv"
COMPANIES_FILE = HERE.parent / "trading" / "malaysia_agriculture_companies.csv"

TOP_N = 3                 # how many of the most palm-sensitive companies to hold on a BUY signal
MIN_TRAIN_MONTHS = 36     # a company needs this many months up to TRAIN_END_YEAR to get a beta
MIN_POOL = 3              # warn when fewer companies than this can be ranked
CHART_FILE = HERE.parent / "images" / "results" / "stockFutures.png"
# Line colours checked for colour-blind safety; palm oil lines are dashed so colour is not the only cue.
CHART_LINES = [("strategy", "Strategy (top stocks on BUY signals)", "#2a78d6", "-"),
               ("hold_pool", "Hold all matched stocks", "#eb6834", "-"),
               ("palm_bot", "Palm oil bot (main.py)", "#1baf7a", (0, (5, 2))),
               ("palm_hold", "Hold palm oil", "#eda100", (0, (5, 2)))]
SIGNAL_NAMES = {1.0: "BUY", -1.0: "SELL", 0.0: "NEUTRAL"}


def load_pool(use_all):
    """Companies to choose from: the soil matches, or every traded company with --all."""
    if use_all:
        pool = pd.read_csv(COMPANIES_FILE, dtype=str).fillna("")
        pool["Matched"] = "-"
        source = "all traded companies (soil match skipped)"
    else:
        if not MATCHES_FILE.exists():
            sys.exit(f"ERROR: {MATCHES_FILE} not found. Run the soil analysis first "
                     "(docker compose run --rm stockFutures backtest does both).")
        pool = pd.read_csv(MATCHES_FILE, dtype=str).fillna("")
        source = "companies matched to the soil image"
    pool.columns = [c.strip() for c in pool.columns]
    pool = pool.rename(columns={"Company Name": "company", "Bursa Ticker": "ticker",
                                "Primary Products/Activities": "products", "Matched": "matched",
                                "Live Price (MYR)": "live_price"})
    if "live_price" not in pool.columns:
        pool["live_price"] = ""
    pool = pool[~pool["ticker"].isin(["", "N/A"]) & ~pool["ticker"].str.contains("elisted")]
    return pool.reset_index(drop=True), source


def load_palm():
    """Monthly palm oil table from main.py, with the rain signal and next month's return."""
    rain, prices = palm.load_data(PALM_FILE)
    df = palm.build_monthly(rain, prices)
    df = palm.add_features(df)
    df = palm.add_signal(df)
    df["palm_return"] = df["price"] / df["price"].shift(1) - 1   # return during that month
    return df


def load_stock(ticker):
    """Monthly closes for one company, or None when no history file exists."""
    path = HISTORY_DIR / f"{ticker}.csv"
    if not path.exists():
        return None
    stock = pd.read_csv(path, parse_dates=["date"]).dropna().sort_values("date").set_index("date")
    stock["return"] = stock["close"] / stock["close"].shift(1) - 1          # return during that month
    stock["next_month_return"] = stock["close"].shift(-1) / stock["close"] - 1
    return stock


def palm_beta(stock, palm_df):
    """How much the stock moves when palm oil moves 1%, from TRAIN_END_YEAR and earlier only.
    Returns (beta, correlation, months used); beta is NaN when there is too little history."""
    both = pd.DataFrame({"stock": stock["return"],
                         "palm": palm_df.set_index("date")["palm_return"]}).dropna()
    both = both[both.index.year <= palm.TRAIN_END_YEAR]
    if len(both) < MIN_TRAIN_MONTHS:
        return np.nan, np.nan, len(both)
    beta = both["stock"].cov(both["palm"]) / both["palm"].var()
    return beta, both["stock"].corr(both["palm"]), len(both)


def build_returns(palm_df, stocks, picks):
    """One row per month: the strategy, the whole pool held all the time, and the palm oil bot."""
    months = palm_df.dropna(subset=["signal", "next_month_return"]).set_index("date")
    next_returns = pd.DataFrame({t: s["next_month_return"] for t, s in stocks.items()})
    next_returns = next_returns.reindex(months.index)

    out = pd.DataFrame(index=months.index)
    out["signal"] = months["signal"]
    out["hold_pool"] = next_returns.mean(axis=1)                 # equal weight, every month
    picked = next_returns[picks].mean(axis=1) if picks else pd.Series(np.nan, index=months.index)
    out["strategy"] = np.where(out["signal"] == 1, picked, 0.0)  # cash unless the signal says BUY
    out["palm_bot"] = months["bot_return"]
    out["palm_hold"] = months["next_month_return"]
    # Keep only months where the pool had prices, so every column covers the same months.
    out = out.dropna(subset=["hold_pool", "strategy"])
    return out.reset_index().rename(columns={"index": "date"})


def print_period(name, data):
    print("-" * 78)
    if data.empty:
        print(f"{name}: no months with data")
        return
    start = data["date"].min().strftime("%b %Y")
    end = data["date"].max().strftime("%b %Y")
    columns = [("Strategy", "strategy"), ("Hold pool", "hold_pool"),
               ("Palm oil bot", "palm_bot"), ("Palm oil hold", "palm_hold")]
    print(f"{name} ({start} - {end}, {len(data)} months)")
    print(f"  {'':<22}" + "".join(f"{label:>15}" for label, _ in columns))
    rows = [("Total return", lambda r: palm.total_return(r)),
            ("Hit rate", lambda r: palm.stats(r)["hit_rate"]),
            ("Volatility (yearly)", lambda r: palm.stats(r)["volatility"]),
            ("Max drawdown", lambda r: palm.stats(r)["max_drawdown"])]
    for label, fn in rows:
        print(f"  {label:<22}" + "".join(f"{fn(data[col]):>15.2%}" for _, col in columns))
    n_buy = int((data["signal"] == 1).sum())
    print(f"  Strategy held stocks in {n_buy} of {len(data)} months (BUY signals) and cash in the rest.")


def print_company_table(table):
    # Same layout as the trader's table: [n/total] counter, then one padded column per field.
    total = len(table)
    digits = len(str(total))
    company_w = max(len("Company"), table["company"].str.len().max())
    products_w = max(len("Products"), table["products"].str.len().max())
    ticker_w = max(len("Ticker"), table["ticker"].str.len().max())
    matched_w = max(len("Matched"), table["matched"].str.len().max())
    indent = " " * (digits * 2 + 4)

    header = (f"{indent}{'Company':<{company_w}}  {'Products':<{products_w}}  {'Ticker':<{ticker_w}}  "
              f"{'Price':>10}  {'Matched':<{matched_w}}  {'Months':>6}  {'Palm beta':>9}  {'Corr':>5}  "
              f"{'Test: buy months':>16}  {'Test: hold':>10}  Picked")
    print()
    print(header)
    print("-" * len(header))
    for i, r in enumerate(table.to_dict("records"), start=1):
        price = f"RM {float(r['live_price']):>7.3f}" if r["live_price"] not in ("", "N/A") else "N/A"
        beta = f"{r['beta']:.2f}" if pd.notna(r["beta"]) else "-"
        corr = f"{r['corr']:.2f}" if pd.notna(r["corr"]) else "-"
        buy = f"{r['test_buy']:+.1%}" if pd.notna(r["test_buy"]) else "-"
        hold = f"{r['test_hold']:+.1%}" if pd.notna(r["test_hold"]) else "-"
        print(f"[{i:>{digits}}/{total}] {r['company']:<{company_w}}  {r['products']:<{products_w}}  "
              f"{r['ticker']:<{ticker_w}}  {price:>10}  {r['matched']:<{matched_w}}  {r['months']:>6}  "
              f"{beta:>9}  {corr:>5}  {buy:>16}  {hold:>10}  {r['picked']}")


def plot_growth(returns, pool_size, n_picks, save_path=CHART_FILE):
    """Value of $1 over time for each column of the backtest, in the same style as main.py's chart."""
    test_start = palm.TEST_START
    test_label = test_start.strftime("%b %Y")
    fig, ax = plt.subplots(figsize=(11, 6.5))

    ends = []
    for column, label, color, style in CHART_LINES:
        growth = (1 + returns[column]).cumprod()
        ax.plot(returns["date"], growth, label=label, color=color, linestyle=style, linewidth=2)
        ends.append((growth.iloc[-1], label.split(" (")[0], color))

    # Dashed line marks where the test period starts: everything to the right is unseen data.
    ax.axvline(test_start, color="gray", linestyle="--", linewidth=1,
               label=f"Test period starts ({test_label}): unseen data, the fair check")
    ax.set_yscale("log")
    ax.yaxis.set_major_locator(FixedLocator([0.25, 0.5, 1, 2, 5, 10, 20, 50, 100]))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"${y:g}"))
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.text(test_start, 0.98, f"  Training data (<= {palm.TRAIN_END_YEAR})  ", transform=ax.get_xaxis_transform(),
            ha="right", va="top", fontsize=9, color="gray")
    ax.text(test_start, 0.98, f"  Test data ({test_label} on)", transform=ax.get_xaxis_transform(),
            ha="left", va="top", fontsize=9, color="gray")

    # Label each line at its right end with its final value, spaced so the labels never overlap.
    last_date = returns["date"].max()
    label_x = last_date + pd.DateOffset(months=5)
    ax.set_xlim(returns["date"].min() - pd.DateOffset(months=4), label_x)   # labels sit just outside the plot, to its right
    placed = None
    for value, name, color in sorted(ends):
        y = value if placed is None else max(value, placed * 1.22)
        placed = y
        ax.plot([last_date, label_x], [value, y], color=color, linewidth=1)
        ax.text(label_x, y, f" {name}: ${value:,.2f}", va="center", ha="left", fontsize=9, color="#333333",
                clip_on=False)

    ax.set_title(f"Soil-matched stocks ({pool_size} companies) + palm oil rain signal: value of $1")
    ax.set_ylabel("Value of $1 (log scale)")
    ax.set_xlabel("Date")
    ax.legend(loc="upper left", bbox_to_anchor=(0.0, 0.93), fontsize=9)
    ax.grid(True, alpha=0.3)

    start = returns["date"].min().strftime("%b %Y")
    caption = (
        f"How to read: each line is what $1 invested in {start} grew to, month by month. Solid lines are stocks, dashed lines are palm oil.\n"
        f"Strategy holds the {n_picks} most palm-sensitive matched companies only in months with a BUY signal, and cash otherwise.\n"
        "Log scale: each step up doubles your money, so equal slopes mean equal % growth.\n"
        f"Left of the dashed line the rule was built; right of it ({test_label} on) is unseen data, the fair test. Fees are ignored."
    )
    fig.text(0.5, 0.01, caption, ha="center", va="bottom", fontsize=8.5, color="dimgray")
    fig.tight_layout(rect=(0, 0.11, 1, 1))
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Chart saved to: {save_path}")


def upcoming_signal(palm_df):
    """Signal for the month that starts now, from rain LAG months ago (works past the last price)."""
    anomaly = palm_df.set_index("date")["rain_anomaly"].dropna()
    train_std = palm_df.loc[palm_df["date"].dt.year <= palm.TRAIN_END_YEAR, "rain_anomaly"].std()
    this_month = pd.Timestamp.today().to_period("M").to_timestamp()
    rain_month = this_month - pd.DateOffset(months=palm.LAG)
    if rain_month not in anomaly.index:
        return None
    z = anomaly[rain_month] / train_std
    signal = 1.0 if z < -palm.NEUTRAL_Z else (-1.0 if z > palm.NEUTRAL_Z else 0.0)
    return {"signal": signal, "z": z, "rain_month": rain_month,
            "held_month": this_month + pd.DateOffset(months=1)}


def main():
    use_all = "--all" in sys.argv[1:]
    pool, source = load_pool(use_all)
    if pool.empty:
        sys.exit("No companies in the pool, so there is nothing to backtest.")
    palm_df = load_palm()
    test_start = palm.TEST_START

    # ---- Each company: history, palm beta, and how it did in the test period ----
    stocks = {}
    rows = []
    buy_months = set(palm_df.loc[palm_df["signal"] == 1, "date"])
    for company in pool.to_dict("records"):
        row = dict(company, months=0, beta=np.nan, corr=np.nan, test_buy=np.nan, test_hold=np.nan, picked="")
        stock = load_stock(company["ticker"])
        if stock is None:
            row["picked"] = "no history file"
        else:
            stocks[company["ticker"]] = stock
            row["months"] = len(stock)
            row["beta"], row["corr"], _ = palm_beta(stock, palm_df)
            test = stock.loc[stock.index >= test_start, "next_month_return"].dropna()
            if len(test):
                row["test_hold"] = palm.total_return(test)
                row["test_buy"] = palm.total_return(test[test.index.isin(buy_months)])
            if pd.isna(row["beta"]):
                row["picked"] = f"too little history before {palm.TRAIN_END_YEAR + 1}"
        rows.append(row)
    table = pd.DataFrame(rows)

    if not stocks:
        sys.exit("ERROR: no price history found. Run: docker compose run --rm stock history")

    # ---- Pick the most palm-sensitive companies (decided on training data only) ----
    rankable = table[table["beta"] > 0].sort_values("beta", ascending=False)
    picks = list(rankable["ticker"].head(TOP_N))
    table.loc[table["ticker"].isin(picks), "picked"] = "yes"
    table = table.sort_values("beta", ascending=False, na_position="last").reset_index(drop=True)

    print("=" * 78)
    print("Stock backtest: soil-matched companies + palm oil rain signal")
    print(f"Pool: {len(pool)} {source}")
    print(f"Rule: on a BUY signal hold the {len(picks)} highest palm-beta companies for the next month, "
          "otherwise hold cash.")
    print_company_table(table)
    print()
    print("  Palm beta = how much the share price moved when palm oil moved 1%, "
          f"measured up to {palm.TRAIN_END_YEAR} only.")
    print(f"  Test: buy months = return from {test_start.strftime('%b %Y')} on, holding that company only "
          "in BUY-signal months.")
    print(f"  Test: hold       = return from {test_start.strftime('%b %Y')} on, holding it the whole time.")
    if len(rankable) < MIN_POOL:
        print(f"  WARNING: only {len(rankable)} companies could be ranked, so the result depends on very few stocks.")
    if not picks:
        sys.exit("No company has enough history and a positive palm beta, so there is no strategy to test.")

    # ---- Backtest ----
    returns = build_returns(palm_df, stocks, picks)
    print_period("Training period", returns[returns["date"] < test_start])
    print_period("Test period (the fair check)", returns[returns["date"] >= test_start])
    print("-" * 78)
    plot_growth(returns, len(pool), len(picks))

    # ---- What the signal says now ----
    print("-" * 78)
    now = upcoming_signal(palm_df)
    if now is None:
        print("Current signal: not available (the rain data does not reach back far enough from today).")
    else:
        name = SIGNAL_NAMES[now["signal"]]
        print(f"Current palm oil signal: {name} for {now['held_month'].strftime('%B %Y')} "
              f"(rain in {now['rain_month'].strftime('%b %Y')} was {now['z']:+.2f} standard swings from normal)")
        if now["signal"] == 1:
            names = ", ".join(picks)
            print(f"  Model candidates from the soil-matched pool: {names}")
        elif now["signal"] == -1:
            print("  The rule holds no stocks on a SELL signal. main.py's palm oil bot would sell palm oil.")
        else:
            print("  The rule holds no stocks and the palm oil bot stays out: rain was close to normal.")

    print("-" * 78)
    print("Notes:")
    print("  - The soil image only chooses which companies are in the pool. It is not tested here and")
    print("    a good result does not show that the soil photo predicts share prices.")
    print("  - The pool is companies listed today. Delisted ones are missing, which flatters past results.")
    print("  - Returns ignore trading fees and assume trades at month-end closing prices.")
    print("  - This is a research backtest, not investment advice. Past performance does not guarantee future returns.")
    print("=" * 78)


if __name__ == "__main__":
    main()
