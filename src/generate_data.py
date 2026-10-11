"""
generate_data.py - builds SYNTHETIC pharma supply-chain data and saves CSV files.

Run:   python src/generate_data.py
Output: CSV files in the data/ folder.   Nothing here is real company data.

How the data is made (the order matters):
  1. Fix the small "dimension" lists (products, sites, regions, dates).
  2. For every product x region pair, create DAILY DEMAND (random, but with patterns).
  3. Create SHIPMENTS that restock that pair every 14 days (some arrive late).
  4. Replay the 180 days: stock = yesterday's stock + deliveries - sales.
     So inventory is NOT random: it is computed from sales and shipments.
"""
import os
import numpy as np
import pandas as pd

SEED = 42                      # same seed -> same "random" data every run
rng = np.random.default_rng(SEED)

N_DAYS = 180
END_DATE = pd.Timestamp("2026-10-09")                 # last day of data ("today")
START_DATE = END_DATE - pd.Timedelta(days=N_DAYS - 1)
ORDER_EVERY = 14                                      # restock every 14 days
START_COVER_DAYS = 18                                 # opening stock = 18 days of demand

# ---------------------------------------------------------------- dimensions
# (site_id, name, planned lead time in days, chance a shipment is late, (min, max) delay)
SITES = [
    (1, "Plant-HYD", 7, 0.08, (1, 3)),
    (2, "Plant-BDI", 9, 0.65, (3, 10)),    # PLANTED: the chronically late factory
    (3, "Plant-GOA", 8, 0.10, (1, 3)),
    (4, "Plant-ANK", 8, 0.12, (1, 4)),
]

REGIONS = [  # (region_id, name, demand multiplier)
    (1, "North", 1.0), (2, "South", 1.2), (3, "East", 0.8),
    (4, "West", 1.1), (5, "Central", 0.7),
]

PRODUCTS = [  # (id, name, category, shelf_life_days, unit_cost, base units/day, site_id)
    (1, "Paracetamol 500mg", "Pain", 1095, 0.8, 120, 1),
    (2, "Ibuprofen 400mg", "Pain", 1095, 1.1, 80, 3),
    (3, "Diclofenac 50mg", "Pain", 730, 1.4, 60, 1),
    (4, "Amoxicillin 500mg", "Antibiotic", 730, 3.2, 70, 2),
    (5, "Azithromycin 250mg", "Antibiotic", 730, 6.5, 55, 2),
    (6, "Ciprofloxacin 500mg", "Antibiotic", 730, 4.1, 45, 2),
    (7, "Cefixime 200mg", "Antibiotic", 540, 7.0, 40, 4),
    (8, "Amlodipine 5mg", "Cardio", 1095, 1.5, 90, 1),
    (9, "Atorvastatin 10mg", "Cardio", 1095, 2.8, 85, 3),
    (10, "Losartan 50mg", "Cardio", 1095, 2.2, 65, 4),
    (11, "Metformin 500mg", "Diabetes", 1095, 1.0, 110, 3),
    (12, "Glimepiride 2mg", "Diabetes", 1095, 2.4, 50, 4),
    (13, "Insulin Glargine 100IU", "Diabetes", 365, 420.0, 15, 3),
    (14, "Salbutamol Inhaler", "Respiratory", 730, 95.0, 25, 2),
    (15, "Montelukast 10mg", "Respiratory", 1095, 3.5, 45, 4),
    (16, "Cetirizine 10mg", "Respiratory", 1095, 0.7, 100, 1),
    (17, "Budesonide Inhaler", "Respiratory", 730, 210.0, 14, 2),
    (18, "Influenza Vaccine", "Vaccine", 270, 310.0, 18, 3),
    (19, "Hepatitis B Vaccine", "Vaccine", 540, 280.0, 10, 4),
    (20, "Pantoprazole 40mg", "Gastro", 730, 1.9, 75, 1),
]

# PLANTED patterns (product_id, region_id):
NEAR_STOCKOUT = {(5, 3): 2.5, (11, 1): 4.0, (8, 5): 5.5, (18, 2): 6.5}  # -> target days of cover today
EXCESS = [(2, 1), (9, 3), (12, 5), (19, 4)]                              # over-ordered
SEASONAL_REGION = 4            # West: Respiratory demand ramps up to 2.2x
SEASONAL_CATEGORY = "Respiratory"

WEEKDAY_FACTOR = [1.05, 1.05, 1.05, 1.05, 1.0, 0.9, 0.9]   # Mon..Sun, averages to 1.0


def date_id(day_index):
    """Turn day number (0 = first day) into an ID like 20261009."""
    d = START_DATE + pd.Timedelta(days=int(day_index))
    return int(d.strftime("%Y%m%d"))


def make_demand(base_per_day, region_mult, is_seasonal):
    """Return an array of N_DAYS random daily demands for one product-region."""
    demand = np.zeros(N_DAYS, dtype=int)
    for t in range(N_DAYS):
        weekday = (START_DATE + pd.Timedelta(days=t)).dayofweek
        season = 1.0
        if is_seasonal:
            # ramp from 1.0 (day 100) to 2.2 (day 160), then stay there
            season = 1.0 + 1.2 * min(max((t - 100) / 60.0, 0.0), 1.0)
        mean = base_per_day * region_mult * WEEKDAY_FACTOR[weekday] * season
        demand[t] = rng.poisson(mean)     # Poisson = random counts around the mean
    return demand


def make_orders(site, base_per_day, region_mult, extra_qty_after=None):
    """Create the restock shipments for one product-region. Returns a list of dicts."""
    _, _, lead, p_late, (dmin, dmax) = site
    orders = []
    start = int(rng.integers(0, 6))                 # first order on day 0..5
    for ship_day in range(start, N_DAYS, ORDER_EVERY):
        qty_mult = 1.0
        if extra_qty_after is not None and ship_day >= extra_qty_after:
            qty_mult = 2.0                           # over-ordering (excess stock)
        units = int(round(base_per_day * region_mult * ORDER_EVERY * qty_mult))
        promised = ship_day + lead
        if rng.random() < p_late:
            delay = int(rng.integers(dmin, dmax + 1))
        else:
            delay = int(rng.integers(-1, 1))         # 0 (on time) or -1 (a day early)
        orders.append({"ship": ship_day, "promised": promised,
                       "delivered": promised + delay, "units": units})
    return orders


def replay(demand, orders, start_stock):
    """Walk through the days: add deliveries, subtract sales. Returns (sales, stock_at_end_of_day)."""
    arrivals = np.zeros(N_DAYS, dtype=int)
    for o in orders:
        if o["delivered"] is not None and o["delivered"] < N_DAYS:
            arrivals[max(o["delivered"], 0)] += o["units"]
    sales = np.zeros(N_DAYS, dtype=int)
    stock_end = np.zeros(N_DAYS, dtype=int)
    stock = start_stock
    for t in range(N_DAYS):
        stock += arrivals[t]
        sold = min(demand[t], stock)    # cannot sell what we do not have
        stock -= sold
        sales[t], stock_end[t] = sold, stock
    return sales, stock_end


def main():
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    os.makedirs(out, exist_ok=True)
    site_by_id = {s[0]: s for s in SITES}

    # ---- dimension tables ----
    # the date table runs 45 days past "today" so promised dates of in-transit shipments exist
    all_days = pd.date_range(START_DATE, END_DATE + pd.Timedelta(days=45))
    dim_date = pd.DataFrame({
        "date_id": [int(d.strftime("%Y%m%d")) for d in all_days],
        "full_date": all_days.date, "year": all_days.year, "month": all_days.month,
        "day_of_week": all_days.day_name()})
    dim_product = pd.DataFrame([p[:5] for p in PRODUCTS],
        columns=["product_id", "product_name", "category", "shelf_life_days", "unit_cost"])
    dim_site = pd.DataFrame([(s[0], s[1], "India") for s in SITES],
        columns=["site_id", "site_name", "country"])
    dim_region = pd.DataFrame([(r[0], r[1]) for r in REGIONS], columns=["region_id", "region_name"])

    # ---- fact tables: loop over every product x region pair ----
    sales_rows, inv_rows, ship_rows = [], [], []
    shipment_id = 1
    for (pid, pname, cat, shelf, cost, base, site_id) in PRODUCTS:
        site = site_by_id[site_id]
        for (rid, rname, rmult) in REGIONS:
            seasonal = (rid == SEASONAL_REGION and cat == SEASONAL_CATEGORY)
            demand = make_demand(base, rmult, seasonal)
            excess_from = 100 if (pid, rid) in EXCESS else None
            orders = make_orders(site, base, rmult, excess_from)
            start_stock = int(base * rmult * (START_COVER_DAYS + rng.integers(0, 4)))

            if (pid, rid) in NEAR_STOCKOUT:
                # The last 2 shipments get stuck on the road (never arrive before "today").
                for o in orders[-2:]:
                    o["delivered"] = N_DAYS + 40
                # Then resize the last order that DID arrive until today's cover hits the target.
                real = [o for o in orders if o["delivered"] < N_DAYS]
                last = real[-1]
                original = last["units"]
                target = NEAR_STOCKOUT[(pid, rid)]
                best_units, best_gap = original, 1e18
                for scale in np.linspace(0.05, 4.0, 80):
                    last["units"] = int(original * scale)
                    s, st = replay(demand, orders, start_stock)
                    cover = st[-1] / max(s[-7:].mean(), 1)
                    if abs(cover - target) < best_gap:
                        best_gap, best_units = abs(cover - target), last["units"]
                last["units"] = best_units

            sales, stock_end = replay(demand, orders, start_stock)
            for t in range(N_DAYS):
                sales_rows.append((date_id(t), pid, rid, int(sales[t])))
                inv_rows.append((date_id(t), pid, rid, int(stock_end[t])))
            for o in orders:
                delivered_id = date_id(o["delivered"]) if o["delivered"] < N_DAYS else None
                ship_rows.append((shipment_id, pid, site_id, rid, date_id(o["ship"]),
                                  date_id(o["promised"]), delivered_id, o["units"]))
                shipment_id += 1

    fact_sales = pd.DataFrame(sales_rows, columns=["date_id", "product_id", "region_id", "units_sold"])
    fact_inv = pd.DataFrame(inv_rows, columns=["date_id", "product_id", "region_id", "units_on_hand"])
    fact_ship = pd.DataFrame(ship_rows, columns=["shipment_id", "product_id", "site_id", "region_id",
        "ship_date_id", "promised_date_id", "delivered_date_id", "units"])
    fact_ship["delivered_date_id"] = fact_ship["delivered_date_id"].astype("Int64")

    tables = {"dim_date": dim_date, "dim_product": dim_product, "dim_site": dim_site,
              "dim_region": dim_region, "fact_sales": fact_sales,
              "fact_inventory": fact_inv, "fact_shipments": fact_ship}
    for name, df in tables.items():
        df.to_csv(os.path.join(out, name + ".csv"), index=False)
        print(f"{name:16s} {len(df):7d} rows")
    print(f"\nDate range of sales/inventory: {START_DATE.date()} to {END_DATE.date()}")
    print(f"Stockout product-region-days: {(fact_inv.units_on_hand == 0).sum()} "
          f"of {len(fact_inv)} ({100 * (fact_inv.units_on_hand == 0).mean():.2f}%)")


if __name__ == "__main__":
    main()
