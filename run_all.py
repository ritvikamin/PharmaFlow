"""
run_all.py - runs the whole PharmaFlow pipeline, start to finish, with one command:

    python run_all.py

Order: generate data -> load into MySQL -> SQL KPI views -> forecast -> risk -> write results.
Afterwards start the dashboard with:   streamlit run dashboard/app.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

import generate_data
import load_to_mysql
import run_kpis
import forecast
import risk
import report_numbers

STEPS = [
    ("1/6 Generate synthetic data (CSV files)", generate_data.main),
    ("2/6 Create schema and load into MySQL", load_to_mysql.main),
    ("3/6 Create SQL KPI views", run_kpis.main),
    ("4/6 Forecast next 30 days + backtest", forecast.main),
    ("5/6 Stockout risk flags", risk.main),
    ("6/6 Write RESULTS.md and INTERVIEW_PREP.md", report_numbers.main),
]

if __name__ == "__main__":
    for title, fn in STEPS:
        print("\n" + "=" * 70 + "\n" + title + "\n" + "=" * 70)
        fn()
    print("\nDone. Start the dashboard with:  streamlit run dashboard/app.py")
