# hackumass-soil-trader

Soil image -> AI soil analysis (Python, `ai/`) -> companies whose products fit that soil (C++, `trading/`).

## Setup (Linux)
```
cd ai
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt     # google-genai python-dotenv
echo "GEMINI_API_KEY=your-key" > .env
```
The trader needs g++ and libcurl (`sudo apt install g++ libcurl4-openssl-dev`).

## Run
```
bash run.sh                  # uses images/soil.jpg
bash run.sh path/to/soil.jpg
```
1. `ai/soil_analyzer.py` sends the image to Gemini and writes `trading/soil_report.txt`
   (`moisture=dry`, `texture=sandy`, `health=4`, ...).
2. `trading/trader --soil soil_report.txt` turns the report into conditions (dry, acidic, ...)
   and prints the companies whose products match, using `trading/soil_rules.csv`.

Edit `trading/soil_rules.csv` to change which product keywords go with each soil condition.

`cd trading && ./trader` (no arguments) fetches live prices for every company into
`malaysia_agriculture_live.csv`. The soil match reads `malaysia_agriculture_companies.csv`
and fetches live prices only for the companies it matches.
