"""
load_to_mysql.py - creates the database + tables, then loads the CSV files into MySQL.

Run:   python src/load_to_mysql.py
Needs: MySQL running, and PF_DB_USER / PF_DB_PASSWORD set (see config.py).
"""
import os
import pandas as pd
from sqlalchemy import text
import config

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Parents first, children second (a fact row needs its dimension rows to exist).
LOAD_ORDER = ["dim_date", "dim_product", "dim_site", "dim_region",
              "fact_sales", "fact_inventory", "fact_shipments"]


def run_sql_file(engine, path):
    """Run every statement in a .sql file (statements are separated by ';')."""
    with open(path, encoding="utf-8") as f:
        lines = [ln for ln in f.read().splitlines() if not ln.strip().startswith("--")]
    statements = [s.strip() for s in "\n".join(lines).split(";") if s.strip()]
    with engine.begin() as conn:                 # engine.begin() = one transaction
        for stmt in statements:
            conn.execute(text(stmt))


def main():
    # 1) make sure the database exists
    server = config.get_engine(with_database=False)
    with server.begin() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{config.DB_NAME}`"))

    # 2) (re)create all tables from 01_schema.sql
    engine = config.get_engine()
    run_sql_file(engine, os.path.join(ROOT, "sql", "01_schema.sql"))
    print("Schema created.")

    # 3) load each CSV
    for name in LOAD_ORDER:
        df = pd.read_csv(os.path.join(ROOT, "data", name + ".csv"))
        if name == "fact_shipments":
            # blank delivered date must become SQL NULL (None in Python)
            col = df["delivered_date_id"].astype("Int64").astype(object)
            df["delivered_date_id"] = col.where(col.notna(), None)
        if name == "dim_date":
            df["full_date"] = pd.to_datetime(df["full_date"]).dt.date
        df.to_sql(name, engine, if_exists="append", index=False,
                  chunksize=2000, method="multi")
        print(f"Loaded {name:16s} {len(df):7d} rows")

    # 4) double-check by counting rows INSIDE MySQL
    print("\nRow counts as MySQL sees them:")
    with engine.connect() as conn:
        for name in LOAD_ORDER:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {name}")).scalar()
            print(f"  {name:16s} {n:7d}")


if __name__ == "__main__":
    main()
