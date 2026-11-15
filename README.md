# hackumass-soil-trader

Soil image -> AI soil analysis (Python, `ai/`) -> companies whose products fit that soil (C++, `trading/`).

## Setup (Linux and Windows)

The project runs inside Docker, so the steps are the same on both systems. You don't need to install Python, a C++ compiler or libcurl yourself.

1. **Install Docker** from https://docs.docker.com/get-started/get-docker/
   - Windows: Docker Desktop. Start it and wait until it says it is running.
   - Linux: Docker Desktop, or Docker Engine with the Compose plugin.
2. **Add your Gemini API key.** Copy `ai/.env.example` to `ai/.env`, open it in a text editor and replace `your-key-here` with your key.
3. **Run it** from the project folder:
   ```
   docker compose run --rm soil
   ```
   The first run builds the image, which takes a few minutes. Later runs start right away.

On Linux, if you get a permission error, either run the command with `sudo` or add your user to the `docker` group.

## Run

```
Soil Analysis
docker compose run --rm soil                                         # soil analysis of images/soil/soil.jpg, then matching companies with live prices
docker compose run --rm soil images/soil/mysoil.jpg                  # the same, for your own image
docker compose run --rm soil prices                                  # live prices for every company

Download History before back testing
docker compose run --rm stock history                                # download monthly price history for every company
docker compose run --rm stocks historicalChart                       # chart of that history, each company simply held (not a backtest); saves images/results/stocks.png

Backtesting
docker compose run --rm stockFutures backtest                        # soil match on images/soil/soil.jpg, then backtest those companies and save the chart
docker compose run --rm stockFutures backtest images/soil/mysoil.jpg # the same, for your own image
docker compose run --rm futures backtest                             # palm oil only (data/main.py), no soil analysis; saves images/results/futures.png

```

`soil`, `stock`, `stockFutures`, `futures` and `stocks` are five names for the same container (see `compose.yaml`),
so each command says what it works on. They share one image, which is built once. `backtest` does something
different for the two names that have it:

- `stockFutures backtest`: soil match, then the matched companies tested against the palm oil signal.
- `futures backtest`: the palm oil signal on its own (`data/main.py`).

`stocks historicalChart` is not a backtest. It charts every company's shares held the whole time
(`data/stocks_growth.py`), with no trading rule, as a baseline for the two backtest charts.

Images are kept in two folders:

- `images/soil/` holds the soil photos to analyze. `soil.jpg` is the default.
- `images/results/` holds the charts the scripts save: `stockFutures.png` from `stockFutures backtest`,
  `futures.png` from `futures backtest`, and `stocks.png` from `stocks historicalChart`.

To analyze your own image, put it inside the project folder first (for example in `images/soil/`). The container can only see files in this folder.

1. `ai/soil_analyzer.py` sends the image to Gemini and writes `trading/soil_report.txt`
   (`moisture=dry`, `texture=sandy`, `health=4`, ...).
2. `trader --soil soil_report.txt` turns the report into conditions (dry, acidic, ...),
   prints the companies whose products match using `trading/soil_rules.csv`, and fetches live
   prices for just those companies.

Edit `trading/soil_rules.csv` to change which product keywords go with each soil condition.

## Live prices for every company

`docker compose run --rm soil prices` fetches live prices for every company into
`trading/malaysia_agriculture_live.csv`. The soil match reads `malaysia_agriculture_companies.csv`,
not that live file.

## Price history for every company

`docker compose run --rm stock history` downloads each company's monthly closing prices from Yahoo Finance
into `data/stock_history/`, one file per company (`SDG.csv`, `IOICORP.csv`, ...) with `date` and `close` columns.
Prices are adjusted for dividends and splits, and the unfinished current month is left out.

Run it once and commit the files, so everyone works from the same data. Run it again to refresh them.

The list of companies comes from `trading/malaysia_agriculture_companies.csv`, the same file the trader uses.
Delisted companies stay in the table with status `N/A`. Yahoo lists Bursa Malaysia stocks under their numeric stock code, so
`data/yahoo_tickers.csv` maps each Bursa ticker to its Yahoo symbol (for example `SDG` to `5285.KL`).
After a run, read the printed summary:

- `CHECK NAME` means Yahoo's company name doesn't match the one we expect, so the symbol is probably wrong.
- `FAILED` means the symbol is wrong or Yahoo refused the request.
- `NO YAHOO SYMBOL` means the company is in the companies file but has no row in `data/yahoo_tickers.csv`.

Fix or add the symbol in `data/yahoo_tickers.csv` and run the command again. When you add a company to the
companies file, add its Yahoo symbol there too.

The data comes from Yahoo Finance through the unofficial `yfinance` package, which is meant for personal
and research use.

## Backtest: soil match + palm oil signal + stock history

`docker compose run --rm stockFutures backtest` (or `backtest images/soil/mysoil.jpg`) strings the pieces together:

1. The soil image is analyzed and the trader lists the companies that fit the soil. It also saves them to
   `trading/soil_matches.csv`. Those companies are the pool to choose from.
2. `data/main.py`'s rain signal says each month whether to buy, sell or stay out of palm oil.
3. `data/stock_backtest.py` measures how strongly each company's share price follows the palm oil price
   (its "palm beta"), using 2020 and earlier only.
4. The rule it tests: on a BUY signal, hold the 3 highest-beta companies for the next month; otherwise hold cash.
5. It prints the companies in the trader's table layout, then compares the rule with holding the whole pool
   and with the palm oil bot, for the training period and for the unseen test period (2021 on).

Run `docker compose run --rm stock history` once first, so the price history exists.

Read the notes at the end of the output. The soil image only chooses the pool; it is not tested, and the
backtest ignores fees. This is a research project, not investment advice.

## Changing the code

The project folder is shared with the container, so most edits take effect on the next run:

- `ai/soil_analyzer.py`, the scripts in `data/` and the CSV files: no rebuild needed.
- `trading/trader.cpp`, `run.sh`, `ai/requirements.txt`, `data/requirements.txt` or `Dockerfile`: rebuild first with
  ```
  docker compose build
  ```
