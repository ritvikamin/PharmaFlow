"""
sample_upload.py - makes a small CSV of "new" daily data to try the dashboard's upload feature.

Run:   python src/sample_upload.py        -> writes data/sample_upload.csv
The CSV continues from the last day in the database (7 new days, every product x region).
On day 4 healthy items get a normal restock; items already low do not.
Columns: full_date, product_id, region_id, units_sold, units_on_hand
"""
import os
import numpy as np
import pandas as pd
import config
import forecast

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make_sample(engine, days=7, seed=7):
    wide = forecast.load_sales(engine)
    last_day = wide.index[-1]
    mean_sales = wide.tail(14).mean()
    stock = pd.read_sql("""SELECT i.product_id, i.region_id, i.units_on_hand
                           FROM fact_inventory i
                           WHERE i.date_id = (SELECT MAX(date_id) FROM fact_inventory)""", engine)
    stock = {(int(r.product_id), int(r.region_id)): int(r.units_on_hand) for r in stock.itertuples()}
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(1, days + 1):
        day = (last_day + pd.Timedelta(days=k)).date()
        for (pid, rid), on_hand in stock.items():
            avg = mean_sales[(pid, rid)]
            # on day 4, items with a healthy buffer (7+ days) get their regular 14-day delivery;
            # items already running low get nothing, so the demo does not hide the real problems
            if k == 4 and on_hand >= 7 * avg:
                on_hand += int(round(14 * avg))
            demand = int(rng.poisson(avg))
            sold = min(demand, on_hand)               # cannot sell more than we have
            stock[(pid, rid)] = on_hand - sold
            rows.append((day, pid, rid, sold, stock[(pid, rid)]))
    return pd.DataFrame(rows, columns=["full_date", "product_id", "region_id",
                                       "units_sold", "units_on_hand"])


def main():
    df = make_sample(config.get_engine())
    path = os.path.join(ROOT, "data", "sample_upload.csv")
    df.to_csv(path, index=False)
    print(f"Wrote {path} ({len(df)} rows, {df.full_date.min()} to {df.full_date.max()})")


if __name__ == "__main__":
    main()
