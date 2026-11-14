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
docker compose run --rm soil                     # uses images/soil.jpg
docker compose run --rm soil images/mysoil.jpg   # your own image
docker compose run --rm soil prices              # live prices for every company
```

To analyze your own image, put it inside the project folder first (for example in `images/`). The container can only see files in this folder.

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

## Changing the code

The project folder is shared with the container, so most edits take effect on the next run:

- `ai/soil_analyzer.py` and the CSV files in `trading/`: no rebuild needed.
- `trading/trader.cpp`, `run.sh`, `ai/requirements.txt` or `Dockerfile`: rebuild first with
  ```
  docker compose build
  ```
