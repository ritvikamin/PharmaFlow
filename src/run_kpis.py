"""
run_kpis.py - creates the KPI views from sql/02_kpis.sql and prints each result.

Run:   python src/run_kpis.py      (after load_to_mysql.py)
"""
import os
import pandas as pd
import config
from load_to_mysql import run_sql_file, ROOT

VIEWS = ["v_as_of", "v_stockout_rate_region", "v_stockout_rate_category",
         "v_on_time_delivery_site", "v_region_stock_status"]


def main():
    engine = config.get_engine()
    run_sql_file(engine, os.path.join(ROOT, "sql", "02_kpis.sql"))
    print("KPI views created.\n")
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    for v in VIEWS:
        print(f"--- {v} ---")
        print(pd.read_sql(f"SELECT * FROM {v}", engine).to_string(index=False), "\n")
    print("--- lowest days of cover (v_stock_status, 8 rows) ---")
    q = """SELECT p.product_name, r.region_name, s.units_on_hand, s.avg_daily_sales_30d,
                  s.days_of_cover, s.status
           FROM v_stock_status s
           JOIN dim_product p ON p.product_id = s.product_id
           JOIN dim_region r  ON r.region_id  = s.region_id
           ORDER BY s.days_of_cover LIMIT 8"""
    print(pd.read_sql(q, engine).to_string(index=False))


if __name__ == "__main__":
    main()
