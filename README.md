# PharmaFlow

Pharmaceutical supply-chain analytics on **synthetic data**. It answers one question for an
operations team: *which medicines are about to run out, where, and why?*
It also shows excess stock (too much sitting there and expiring).

## Requirements

- Python 3.10 or newer
- MySQL 8 running locally (the loader creates the `pharmaflow` database for you)
- The MySQL login is read from environment variables, so no password is stored in the code

## Run it

**1. Get the code and install packages**

```
git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git
cd YOUR_REPO
python -m venv venv
venv\Scripts\activate            # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
```

**2. Tell the project your MySQL password** (set it in the same terminal you run Python from)

| Terminal | Command |
|---|---|
| Windows Command Prompt (cmd) | `set PF_DB_PASSWORD=your_mysql_password` |
| Windows PowerShell | `$env:PF_DB_PASSWORD="your_mysql_password"` |
| macOS / Linux | `export PF_DB_PASSWORD=your_mysql_password` |

Optional settings, with their defaults: `PF_DB_HOST=localhost`, `PF_DB_PORT=3306`,
`PF_DB_USER=root`, `PF_DB_NAME=pharmaflow`. The variable only lasts for that terminal window,
so set it again if you open a new one.

**3. Build everything and open the dashboard**

```
python run_all.py                  # generates data, loads MySQL, builds KPIs, forecast, risk (about 30 seconds)
streamlit run dashboard/app.py     # opens the dashboard in your browser
```

Optional API: `uvicorn api.main:app` then open http://127.0.0.1:8000/docs

`run_all.py` also writes **RESULTS.md** (every number from your own run) and a local
`INTERVIEW_PREP.md`, which is git-ignored. Re-run it if anything changes.

**Troubleshooting**

- `Access denied for user 'root'... (using password: NO)`: the password variable is not set in this
  terminal. Set it again (see step 2). If it still fails, check the password with `mysql -u root -p`.
- `Can't connect to MySQL server`: MySQL is not running. Start the MySQL service and try again.
- `cryptography package is required`: run `pip install -r requirements.txt` again.

## How the data flows

```
generate_data.py  ->  CSV files  ->  load_to_mysql.py  ->  MySQL star schema
                                                              |
   sql/02_kpis.sql (KPI views) <------------------------------+
   forecast.py  (30-day moving average + backtest)  -> tables forecast_daily, forecast_validation
   risk.py      (days until empty, flags, reasons)  -> table stock_risk
                                                              |
                         dashboard/app.py (Streamlit) and api/main.py (FastAPI) read from MySQL
```

## Files

| File | What it does |
|---|---|
| `run_all.py` | Runs every step in order |
| `src/config.py` | DB login (from environment variables) |
| `sql/01_schema.sql` | Star schema: 4 dimension tables, 3 fact tables |
| `src/generate_data.py` | Synthetic data with planted problems |
| `src/load_to_mysql.py` | Creates tables and loads the CSVs |
| `sql/02_kpis.sql` | The 4 business KPIs as SQL views (+ thresholds table) |
| `src/run_kpis.py` | Creates the views and prints them |
| `src/forecast.py` | 14-day moving-average forecast, backtest vs two naive baselines |
| `src/risk.py` | Days until empty = stock / forecast demand; flags + reasons |
| `src/report_numbers.py` | Writes RESULTS.md and INTERVIEW_PREP.md |
| `src/sample_upload.py` | Makes a sample CSV for the dashboard's upload feature |
| `dashboard/app.py` | Streamlit dashboard |
| `api/main.py` | Optional FastAPI: `/kpis` and `/at-risk` |

## Definitions

- **Days of cover** = units on hand / average daily sales over the last 30 days
- **Stockout rate** = product-days that ended with 0 stock / all product-days
- **On-time delivery %** = delivered on or before promised date / shipments already due
  (a due shipment that has not arrived counts as late)
- **Days until empty** = units on hand / forecast daily demand. Under 7 = **At risk**, over 60 = **Excess**
  (both thresholds live in the `kpi_thresholds` table)
- **Forecast error** = WAPE: total absolute error / total actual sales, on a 30-day hold-out

## Planted patterns (so we can check the system finds them)

- `Plant-BDI` is chronically late
- West region has seasonal demand growth for respiratory medicines
- 4 product-region pairs are near stockout (shipments stuck in transit); 4 are over-ordered

## Known limitations

- Data is synthetic. Numbers show the pipeline works, not real-world performance.
- Moving average lags trends and ignores weekday patterns.
- Sales are capped by stock, so stockouts hide true demand and the forecast runs low for those items.
- Backtest uses one 30-day window.
- Scripts are run by hand; no scheduler, no incremental loads, no data-quality framework.

## Try the upload

In the dashboard open **Load new data**, download the sample CSV (next 7 days), upload it and press
the button. The "as of" date moves forward and the forecast, risk flags and KPI views refresh.
