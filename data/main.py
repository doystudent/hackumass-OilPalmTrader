import sys
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, FixedLocator, NullFormatter

DATA_PATH = "data/climatestatistics.csv"
TRAIN_END_YEAR = 2020
TEST_START = pd.Timestamp("2021-01-01")
LAG = 6
NEUTRAL_Z = 0.5


def load_data(path):
    df = pd.read_csv(path, thousands=",")

    # Rain table (daily)
    rain = df[["Date", "UCSB CHIRPS Rainfall: avg"]].copy()
    rain.columns = ["date", "rain"]
    rain = rain.dropna()
    rain["date"] = pd.to_datetime(rain["date"])

    # Price table (monthly)
    prices = df[["Date.1", "Price"]].copy()
    prices.columns = ["date", "price"]
    prices = prices.dropna().reset_index(drop=True)
    prices["date"] = pd.to_datetime(prices["date"])

    return rain, prices


def build_monthly(rain, prices):
    # Sum rain by month to match prices format in months
    monthly_rain = rain.set_index("date").resample("MS")["rain"].sum().reset_index().rename(columns={"rain": "rain_mm"})

    # Merge the monthly_rain and prices data set into one dataset
    df = pd.merge(monthly_rain, prices, on="date", how="left")
    df = df.sort_values("date").reset_index(drop=True)
    return df


def add_features(df):
    # Get the next month's return as a decimal representing the percentage change, which is why we subtract 1 from the result.
    df["next_month_return"] = df["price"].shift(-1) / df["price"] - 1

    # Creates new columns with the monthly rain from 6 and 12 months ago
    df["rain_6mo_ago"] = df["rain_mm"].shift(LAG)
    df["rain_12mo_ago"] = df["rain_mm"].shift(12)

    # Creates a new column with just the month of each date
    df["month"] = df["date"].dt.month

    # Average rain per calendar month using 2020 and earlier only, since that is the data timeframe we are training on.
    # Comparing to the monthly average removes the normal monsoon-season swings, so only unusual rain is left.
    averages = df[df["date"].dt.year <= TRAIN_END_YEAR].groupby("month")["rain_mm"].mean()

    # .map(averages) looks up each row's month number (1-12) in the averages table and swaps it for that month's normal rain,
    # giving a full-length column so we can subtract it from rain_mm row by row (like VLOOKUP in Sheets).
    df["rain_anomaly"] = df["rain_mm"] - df["month"].map(averages)

    # Creates a new column with the monthly rain anomaly from 6 months ago
    df["anomaly_6mo_ago"] = df["rain_anomaly"].shift(LAG)

    # Z-score = anomaly divided by how much the anomaly normally swings (its standard deviation, from 2020 and earlier only),
    # so -1 means "one normal swing drier than usual". This lets the neutral zone be set in standard units instead of mm.
    train_std = df.loc[df["date"].dt.year <= TRAIN_END_YEAR, "rain_anomaly"].std()
    df["anomaly_z_6mo_ago"] = df["anomaly_6mo_ago"] / train_std
    return df


def add_signal(df, neutral_z=NEUTRAL_Z):
    # Neutral zone: only trade when the rain anomaly from 6 months ago was clearly unusual.
    #   z below -NEUTRAL_Z (clearly drier than normal)  -> signal 1 = buy
    #   z above +NEUTRAL_Z (clearly wetter than normal) -> signal -1 = sell
    #   anything in between (close to normal)            -> signal 0 = stay out, bot_return is 0 that month
    # Setting NEUTRAL_Z = 0 gives back the original always-in-the-market rule.
    # Rows with no anomaly yet (first 6 months) are left as NaN = no trade.
    z = df["anomaly_z_6mo_ago"]
    df["signal"] = np.select([z < -neutral_z, z > neutral_z], [1, -1], default=0).astype(float)
    df["signal"] = df["signal"].where(z.notna())

    # Bot's return each month: signal (1 buy / -1 sell) times next month's price change, so a correct sell call earns money when the price falls
    df["bot_return"] = df["signal"] * df["next_month_return"]
    return df


def correlations(data):
    # Correlation between each rain column and next month's return (-1 to 1); .corr() skips NaN rows automatically
    return {
        "Rain 12mo ago": data["rain_12mo_ago"].corr(data["next_month_return"]),
        "Anomaly 6mo ago": data["anomaly_6mo_ago"].corr(data["next_month_return"]),
        "Rain 6mo ago": data["rain_6mo_ago"].corr(data["next_month_return"]),
    }


def print_correlations(train_corr, all_corr):
    # Prints a table of each rain column's correlation with next month's return, in two columns:
    #   Train = 2020 and earlier only (what we would have known before the test period), All years = every month in the data.
    # Then checks which signal is strongest (most negative) on training data alone:
    #   if it is still Anomaly 6mo ago, the rule was picked without peeking at the test period, so the 2021+ result is a fair test;
    #   if a different column wins, it prints a warning that the rule was partly chosen using test-period data.
    print("-----------------------------------------------------")
    print(f"Correlation with next month's return   Train (<= {TRAIN_END_YEAR})   All years")
    for name in all_corr:
        print(f"  {name:<36} {train_corr[name]:>8.4f}   {all_corr[name]:>9.4f}")

    best_train = min(train_corr, key=train_corr.get)
    if best_train == "Anomaly 6mo ago":
        print(f"  Anomaly 6mo ago is the strongest signal on training data too, so the {TEST_START.year}+ test is fair.")
    else:
        print(f"  Warning: on training data alone, '{best_train}' is the strongest, so the rule was partly picked using test data.")


def total_return(returns):
    # Compound monthly returns: multiply (1 + return) for every month, then subtract 1 to get total % gain
    return np.prod(1 + returns) - 1


def stats(returns):
    # Hit rate = share of traded months with a positive return (neutral months with 0 return are skipped); volatility = yearly swing size;
    # max drawdown = worst fall from a previous high point of the $1 growth line
    growth = (1 + returns).cumprod()
    drawdown = growth / growth.cummax() - 1
    return {
        "hit_rate": (returns[returns != 0] > 0).mean(),
        "volatility": returns.std() * np.sqrt(12),
        "max_drawdown": drawdown.min(),
    }


def print_period(name, data):
    # Prints a side-by-side table (Bot vs Buy & hold) for one period:
    #   Total return        = how much $1 grew overall (compounded monthly returns)
    #   Hit rate            = % of traded months that made money; above 50% means it was right more often than wrong
    #   Volatility (yearly) = how big the monthly ups and downs are, scaled to a year; higher = bumpier ride, more risk
    #   Max drawdown        = the worst drop from a previous high, e.g. -40% means at some point you were 40% below your best value
    # Then the $100 line turns the total return into dollars from the period's first month to its last.
    # The :<22 and :>10 in the f-strings pad the text left/right so the columns line up.
    start = data["date"].min().strftime("%b %Y")
    end = data["date"].max().strftime("%b %Y")
    bot_total = total_return(data["bot_return"])
    hold_total = total_return(data["next_month_return"])
    bot_stats = stats(data["bot_return"])
    hold_stats = stats(data["next_month_return"])

    print("-----------------------------------------------------")
    print(f"{name} ({start} - {end}, {len(data)} months)")
    print(f"  {'':<22}{'Bot':>10}{'Buy & hold':>14}")
    print(f"  {'Total return':<22}{bot_total:>10.2%}{hold_total:>14.2%}")
    print(f"  {'Hit rate':<22}{bot_stats['hit_rate']:>10.2%}{hold_stats['hit_rate']:>14.2%}")
    print(f"  {'Volatility (yearly)':<22}{bot_stats['volatility']:>10.2%}{hold_stats['volatility']:>14.2%}")
    print(f"  {'Max drawdown':<22}{bot_stats['max_drawdown']:>10.2%}{hold_stats['max_drawdown']:>14.2%}")
    # How often the bot was buying, selling, or sitting out in the neutral zone
    n_buy = (data["signal"] == 1).sum()
    n_sell = (data["signal"] == -1).sum()
    n_out = (data["signal"] == 0).sum()
    print(f"  Bot months: {n_buy} buy, {n_sell} sell, {n_out} neutral (|z| <= {NEUTRAL_Z})")
    print(f"  $100 invested in {start} would be ${100*(1+bot_total):,.2f} in {end} using our signals! Or ${100*(1+hold_total):,.2f} if you bought and held :P")


def print_best_worst(name, data, n=5):
    # Checks whether the profit comes from a few lucky months or is spread out:
    #   lists the bot's n best and n worst months (date, what it did, the return),
    #   then recalculates the total return with the best 1 and best 3 months removed.
    #   If the total collapses without them, a handful of trades carried the whole result.
    traded = data[data["signal"] != 0].copy()
    traded["action"] = traded["signal"].map({1: "BUY", -1: "SELL"})
    best = traded.nlargest(n, "bot_return")
    worst = traded.nsmallest(n, "bot_return")

    print("-----------------------------------------------------")
    print(f"{name}: best and worst bot months ({len(traded)} traded months)")
    print(f"  {'Best':<26}{'Worst':<26}")
    for (_, b), (_, w) in zip(best.iterrows(), worst.iterrows()):
        best_text = f"{b['date'].strftime('%b %Y')} {b['action']:<4} {b['bot_return']:+.2%}"
        worst_text = f"{w['date'].strftime('%b %Y')} {w['action']:<4} {w['bot_return']:+.2%}"
        print(f"  {best_text:<26}{worst_text:<26}")

    sorted_returns = traded["bot_return"].sort_values(ascending=False)
    print(f"  Total return:                  {total_return(traded['bot_return']):.2%}")
    print(f"  Without best month:            {total_return(sorted_returns.iloc[1:]):.2%}")
    print(f"  Without best 3 months:         {total_return(sorted_returns.iloc[3:]):.2%}")


def print_yearly(data):
    # Return for each calendar year, bot vs buy and hold, to show whether the profit is steady or mostly from one year
    yearly = data.groupby(data["date"].dt.year).agg(
        bot=("bot_return", total_return),
        hold=("next_month_return", total_return),
    )
    print("-----------------------------------------------------")
    print("Return by year")
    print(f"  {'Year':<8}{'Bot':>10}{'Buy & hold':>14}  Bot beat it?")
    for year, row in yearly.iterrows():
        beat = "yes" if row["bot"] > row["hold"] else "no"
        print(f"  {year:<8}{row['bot']:>10.2%}{row['hold']:>14.2%}  {beat}")
    print(f"  Bot beat buy and hold in {(yearly['bot'] > yearly['hold']).sum()} of {len(yearly)} years")


def print_threshold_check(df, thresholds=(0, 0.25, 0.5, 0.75, 1.0)):
    # Threshold robustness: reruns the bot with different neutral-zone sizes on TRAINING data only (2020 and earlier),
    # so the test period is never used to pick the setting.
    # Good sign: results change smoothly and most thresholds beat buy and hold, meaning NEUTRAL_Z isn't a lucky number.
    # Bad sign: only one threshold works and its neighbours do badly, meaning the result is probably a fluke.
    print("-----------------------------------------------------")
    print(f"Threshold check (training data only, <= {TRAIN_END_YEAR})")
    print(f"  {'NEUTRAL_Z':<12}{'Return':>10}{'Hit rate':>10}{'Drawdown':>11}{'Traded':>8}")

    beats = 0
    for t in thresholds:
        run = add_signal(df.copy(), neutral_z=t)
        train = run[run["date"].dt.year <= TRAIN_END_YEAR].dropna(subset=["signal", "next_month_return"])
        result = stats(train["bot_return"])
        bot = total_return(train["bot_return"])
        hold = total_return(train["next_month_return"])
        beats += bot > hold
        marker = "  <- current" if t == NEUTRAL_Z else ""
        print(f"  {t:<12}{bot:>10.2%}{result['hit_rate']:>10.2%}{result['max_drawdown']:>11.2%}"
              f"{(train['signal'] != 0).sum():>8}{marker}")

    print(f"  Buy and hold over the same months: {hold:.2%}")
    print(f"  {beats} of {len(thresholds)} thresholds beat buy and hold on training data")


def print_notes():
    # Limitations of the backtest, printed so anyone reading the results knows what they don't account for:
    # no trading fees, short-selling assumed always possible, the full period overstates results because the rule was
    # chosen from that data, and the test period (2021 on) is the honest out-of-sample check.
    print("-----------------------------------------------------")
    print("Notes:")
    print("  - Returns ignore trading fees and assume the bot can short-sell every month, so real results would be lower.")
    print("  - The full-period result includes the data the rule was chosen from, so it looks better than it really is.")
    print(f"  - The test period ({TEST_START.strftime('%b %Y')} on) is the fair check, since the bot never used that data to set its monthly averages.")
    print("  - Past performance does not guarantee future returns.")
    print("-----------------------------------------------------")


# Charts go in images/results/ at the top of the project, next to the backtest chart.
RESULTS_DIR = Path(__file__).resolve().parent.parent / "images" / "results"


def plot_growth(trades, save_path=RESULTS_DIR / "futures.png"):
    # Value of $1 over time for each strategy; log scale so 12x and 2x are both readable on one chart
    bot_growth = (1 + trades["bot_return"]).cumprod()
    hold_growth = (1 + trades["next_month_return"]).cumprod()

    plt.figure(figsize=(10, 6))
    plt.plot(trades["date"], bot_growth, label="Bot (rain signal)")
    plt.plot(trades["date"], hold_growth, label="Buy and hold")
    # Dashed line marks where the test period starts: everything to the right is data the bot never used to build its averages
    test_label = TEST_START.strftime("%b %Y")
    plt.axvline(TEST_START, color="gray", linestyle="--",
                label=f"Test period starts ({test_label}): unseen data, the fair check")
    plt.yscale("log")
    plt.gca().yaxis.set_major_locator(FixedLocator([0.25, 0.5, 1, 2, 5, 10, 20, 50, 100]))
    plt.gca().yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"${y:g}"))
    plt.gca().yaxis.set_minor_formatter(NullFormatter())
    plt.text(TEST_START, 0.98, f"  Training data (<= {TRAIN_END_YEAR})  ", transform=plt.gca().get_xaxis_transform(),
             ha="right", va="top", fontsize=9, color="gray")
    plt.text(TEST_START, 0.98, f"  Test data ({test_label} on)", transform=plt.gca().get_xaxis_transform(),
             ha="left", va="top", fontsize=9, color="gray")
    plt.title("Palm oil: rain-signal bot vs buy and hold")
    plt.ylabel("Value of $1 (log scale)")
    plt.xlabel("Date")
    plt.legend()
    plt.grid(True, alpha=0.3)

    # Caption under the chart explaining how to read it, with each line's final value filled in from the data
    caption = (
        f"How to read: each line is what $1 invested in {trades['date'].min().strftime('%b %Y')} grew to, month by month "
        f"(Bot ends at ${bot_growth.iloc[-1]:,.2f}, Buy and hold at ${hold_growth.iloc[-1]:,.2f}).\n"
        "Log scale: each step up doubles your money, so equal slopes mean equal % growth and a widening gap means the bot is pulling ahead.\n"
        f"Left of the dashed line the rule was built and chosen (looks best there); right of it ({test_label} on) is unseen data, the fair test."
    )
    plt.figtext(0.5, 0.01, caption, ha="center", va="bottom", fontsize=8.5, color="dimgray")
    plt.tight_layout(rect=(0, 0.08, 1, 1))
    # Save in images/results/ (not wherever the terminal happens to be), keeping the caption inside the image
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(save_path, dpi=150, bbox_inches="tight")
    print(f"Chart saved to: {save_path}")
    plt.show()


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DATA_PATH
    rain, prices = load_data(path)
    df = build_monthly(rain, prices)
    df = add_features(df)
    df = add_signal(df)

    train = df[df["date"].dt.year <= TRAIN_END_YEAR]
    print_correlations(correlations(train), correlations(df))

    # Keep only months where the bot actually traded, so the bot and buy-and-hold are compared over the same months
    trades = df.dropna(subset=["signal", "next_month_return"]).copy()
    test = trades[trades["date"] >= TEST_START].copy()

    print_period("Full period", trades)
    print_period("Test period", test)
    print_best_worst("Test period", test)
    print_yearly(trades)
    print_threshold_check(df)
    print_notes()

    plot_growth(trades)


if __name__ == "__main__":
    main()
