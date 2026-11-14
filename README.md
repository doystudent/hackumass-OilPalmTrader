# hackumass-soil-trader

Soil image -> AI soil analysis (Python, `ai/`) -> companies whose products fit that soil (C++, `trading/`).

## Setup (Linux)

Install the compiler and libcurl headers:
```
sudo apt install g++ libcurl4-openssl-dev
```

Set up the Python environment and API key:
```
cd ai
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt     # google-genai python-dotenv
echo "GEMINI_API_KEY=your-key" > .env
cd ..
```

## Setup (Windows)

Windows is more involved than Linux. The easiest route is to install WSL (`wsl --install` in PowerShell, then restart) and follow the Linux steps above inside the Ubuntu terminal.

To run natively on Windows you need:

1. **Git for Windows**, which includes Git Bash. `run.sh` only runs from Git Bash, not from PowerShell or cmd.
2. **Python 3.12** from python.org. Tick "Add python.exe to PATH" during install.
3. **MSYS2 with a g++ compiler and libcurl.** Open the MSYS2 UCRT64 shell and run:
   ```
   pacman -S mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-curl
   ```
   Then make sure `g++` is on your PATH inside Git Bash (add `C:\msys64\ucrt64\bin` to the Windows PATH).
4. **A Python virtual environment and API key.** From Git Bash:
   ```
   cd ai
   python -m venv venv
   source venv/Scripts/activate
   pip install -r requirements.txt
   echo "GEMINI_API_KEY=your-key" > .env
   cd ..
   ```
5. **Two edits to `run.sh`.** It was written for Linux:
   - Change `PYTHON="$ROOT/ai/venv/bin/python"` to `PYTHON="$ROOT/ai/venv/Scripts/python.exe"`.
   - Change the fallback `PYTHON=python3` to `PYTHON=python`.

   Without these, `run.sh` can't find the Python you just installed.

Save `.env` as plain UTF-8 without a BOM, or the key won't be read.

## Run
```
bash run.sh                  # uses images/soil.jpg
bash run.sh path/to/soil.jpg
```
On Linux, `run.sh` only rebuilds the trader when the source changes. On Windows, it rebuilds every time, because it checks for a file named `trader` and the compiled file is `trader.exe`.

1. `ai/soil_analyzer.py` sends the image to Gemini and writes `trading/soil_report.txt`
   (`moisture=dry`, `texture=sandy`, `health=4`, ...).
2. `trading/trader --soil soil_report.txt` turns the report into conditions (dry, acidic, ...),
   prints the companies whose products match using `trading/soil_rules.csv`, and fetches live
   prices for just those companies.

Edit `trading/soil_rules.csv` to change which product keywords go with each soil condition.

## Live prices for every company

`cd trading && ./trader` (no arguments) fetches live prices for every company into
`malaysia_agriculture_live.csv`. The soil match reads `malaysia_agriculture_companies.csv`,
not that live file.
