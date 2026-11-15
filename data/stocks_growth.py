"""Stocks-only backtest: what $1 in each company's shares grew to, as a chart.

Run:  docker compose run --rm stocks backtest

No soil analysis and no palm oil signal: this just holds every traded company
from trading/malaysia_agriculture_companies.csv and saves
images/results/stocks.png.

Needs the price history from:  docker compose run --rm stock history
"""
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FixedLocator, FuncFormatter, NullFormatter

HERE = Path(__file__).resolve().parent
HISTORY_DIR = HERE / "stock_history"
COMPANIES_FILE = HERE.parent / "trading" / "malaysia_agriculture_companies.csv"
CHART_FILE = HERE.parent / "images" / "results" / "stocks.png"
START = pd.Timestamp("2007-04-01")   # same first month as the palm oil charts, so they can be compared

AVERAGE_COLOR = "#2a78d6"
COMPANY_COLOR = "#9a9a94"
INK = "#333333"


def load_tickers():
    companies = pd.read_csv(COMPANIES_FILE, dtype=str).fillna("")
    companies.columns = [c.strip() for c in companies.columns]
    tickers = companies["Bursa Ticker"].str.strip()
    return [t for t in tickers if t and t != "N/A" and "elisted" not in t]


def load_growth(ticker):
    """Value of $1 in one company from START (or from its first month, if it listed later)."""
    path = HISTORY_DIR / f"{ticker}.csv"
    if not path.exists():
        return None
    close = pd.read_csv(path, parse_dates=["date"]).dropna().sort_values("date").set_index("date")["close"]
    close = close[close.index >= START]
    if len(close) < 2:
        return None
    return close / close.iloc[0]


def main():
    growth = {}
    for ticker in load_tickers():
        line = load_growth(ticker)
        if line is not None:
            growth[ticker] = line
    if not growth:
        sys.exit("ERROR: no price history found. Run: docker compose run --rm stock history")

    # Equal-weight portfolio: each month, the average return of every company that has a price.
    closes = pd.DataFrame(growth)
    monthly_returns = closes.pct_change(fill_method=None)
    average = (1 + monthly_returns.mean(axis=1).fillna(0)).cumprod()

    finals = {ticker: line.iloc[-1] for ticker, line in growth.items()}
    best = max(finals, key=finals.get)
    worst = min(finals, key=finals.get)
    last_date = closes.index.max()

    fig, ax = plt.subplots(figsize=(11, 6.5))
    for ticker, line in growth.items():
        ax.plot(line.index, line, color=COMPANY_COLOR, linewidth=1, alpha=0.55,
                label="Individual companies" if ticker == best else None)
    ax.plot(average.index, average, color=AVERAGE_COLOR, linewidth=2.5,
            label=f"All {len(growth)} companies, equal weight")

    ax.set_yscale("log")
    ax.yaxis.set_major_locator(FixedLocator([0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 50, 100]))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"${y:g}"))
    ax.yaxis.set_minor_formatter(NullFormatter())

    # Label the average and the best and worst company at the right end, spaced so they never overlap.
    label_x = last_date + pd.DateOffset(months=5)
    ax.set_xlim(START - pd.DateOffset(months=4), label_x)
    ends = sorted([(average.iloc[-1], "All companies", AVERAGE_COLOR),
                   (finals[best], f"{best} (best)", COMPANY_COLOR),
                   (finals[worst], f"{worst} (worst)", COMPANY_COLOR)])
    placed = None
    for value, name, color in ends:
        y = value if placed is None else max(value, placed * 1.22)
        placed = y
        ax.plot([last_date, label_x], [value, y], color=color, linewidth=1)
        ax.text(label_x, y, f" {name}: ${value:,.2f}", va="center", ha="left", fontsize=9, color=INK,
                clip_on=False)

    ax.set_title("Malaysian agriculture stocks: value of $1 held the whole time")
    ax.set_ylabel("Value of $1 (log scale)")
    ax.set_xlabel("Date")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(True, alpha=0.3)

    start_label = START.strftime("%b %Y")
    # "\\$" keeps matplotlib from reading the text between two dollar signs as a maths formula.
    caption = (
        f"How to read: each grey line is what \\$1 in one company's shares grew to since {start_label}. "
        "The blue line holds all of them in equal amounts.\n"
        "Companies that listed later start at \\$1 in their first month, so their lines begin part-way across.\n"
        "Log scale: each step up doubles your money. Prices include dividends; trading fees are ignored. "
        "Delisted companies are missing, which flatters the result."
    )
    fig.text(0.5, 0.01, caption, ha="center", va="bottom", fontsize=8.5, color="dimgray")
    fig.tight_layout(rect=(0, 0.09, 1, 1))
    CHART_FILE.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(CHART_FILE, dpi=150, bbox_inches="tight")
    plt.close(fig)

    print(f"Stocks-only backtest: {len(growth)} companies held from {start_label} "
          f"to {last_date.strftime('%b %Y')}.")
    print(f"$1 spread equally across all of them grew to ${average.iloc[-1]:,.2f}. "
          f"Best: {best} (${finals[best]:,.2f}). Worst: {worst} (${finals[worst]:,.2f}).")
    print(f"Chart saved to: {CHART_FILE}")


if __name__ == "__main__":
    main()
