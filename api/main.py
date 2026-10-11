"""
main.py - a tiny FastAPI service exposing two read-only endpoints on top of the same MySQL data.

Run:   uvicorn api.main:app --reload        (from the PharmaFlow folder)
Then open http://127.0.0.1:8000/docs  for an automatic interactive page.

  GET /kpis                    -> the KPI views as JSON
  GET /at-risk?region=West     -> medicines flagged "At risk" (region is optional)
"""
import os
import sys
from typing import Optional

import pandas as pd
from fastapi import FastAPI
from sqlalchemy import text

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import config  # noqa: E402

app = FastAPI(title="PharmaFlow API", description="Synthetic pharma supply-chain KPIs")
engine = config.get_engine()


def rows(sql, params=None):
    """Run a query and return a list of dicts (JSON-friendly; NaN becomes null)."""
    df = pd.read_sql(text(sql), engine, params=params or {})
    return df.astype(object).where(df.notna(), None).to_dict("records")


@app.get("/kpis")
def kpis():
    return {
        "as_of": str(pd.read_sql("SELECT as_of_date FROM v_as_of", engine).iloc[0, 0]),
        "stockout_rate_by_region": rows("SELECT * FROM v_stockout_rate_region"),
        "on_time_delivery_by_site": rows("SELECT * FROM v_on_time_delivery_site"),
        "stock_status_by_region": rows("SELECT * FROM v_region_stock_status"),
    }


@app.get("/at-risk")
def at_risk(region: Optional[str] = None):
    sql = """SELECT product_name, region_name, site_name, units_on_hand,
                    forecast_daily_demand, days_until_empty, reason
             FROM stock_risk WHERE status = 'At risk'"""
    params = {}
    if region:
        sql += " AND region_name = :region"       # :region is a bound parameter (safe from SQL injection)
        params["region"] = region
    sql += " ORDER BY days_until_empty"
    return rows(sql, params)
