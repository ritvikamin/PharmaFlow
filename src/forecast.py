"""
forecast.py - forecasts the next 30 days of demand per product and region, and
CHECKS how good that forecast is by testing it on data it has not seen.

Run:   python src/forecast.py

The model is a 14-day MOVING AVERAGE: forecast for every future day =
the average daily sales of the last 14 days. Simple on purpose, easy to explain.

How we validate it (a "backtest"):
  1. Hide the last 30 days of real sales.
  2. Forecast those 30 days using only the earlier days.
  3. Compare to what really sold. Do the same with two dumb baselines.
  A forecast is only useful if it beats the dumb baselines.
"""
import numpy as np
import pandas as pd
import config

MA_WINDOW = 14     # days averaged by the moving average
HORIZON = 30       # days forecast ahead (also the size of the backtest hold-out)


def load_sales(engine):
    """Return a table with one ROW per day and one COLUMN per (product, region) pair."""
    q = """SELECT d.full_date, s.product_id, s.region_id, s.units_sold
           FROM fact_sales s JOIN dim_date d ON d.date_id = s.date_id"""
    df = pd.read_sql(q, engine, parse_dates=["full_date"])
    wide = df.pivot_table(index="full_date", columns=["product_id", "region_id"],
                          values="units_sold", aggfunc="sum").sort_index().fillna(0)
    return wide


def score(test, pred, col_mask):
    """Error numbers for the chosen columns. test and pred are day x pair tables."""
    t = test.loc[:, col_mask]
    p = pred.loc[:, col_mask]
    abs_err = (t - p).abs()
    actual_total = t.values.sum()
    return {
        # WAPE = total absolute error / total actual sales (lower is better, 0% = perfect)
        "daily_wape_pct": 100 * abs_err.values.sum() / actual_total,
        "mae_units": abs_err.values.mean(),            # average miss per day, in units
        # error on the 30-day TOTAL per pair (what matters for "will we run out?")
        "total30_wape_pct": 100 * (t.sum() - p.sum()).abs().sum() / actual_total,
        # bias: negative = we forecast too LOW, positive = too HIGH
        "bias_pct": 100 * (p.values.sum() - actual_total) / actual_total,
    }


def make_predictions(train, horizon):
    """Three forecasts for the hold-out period, each a day x pair table."""
    days = train.shape[0]
    idx = pd.date_range(train.index[-1] + pd.Timedelta(days=1), periods=horizon)
    preds = {}
    # 1) the model: average of the last MA_WINDOW days, repeated for every future day
    ma = train.tail(MA_WINDOW).mean()
    preds["moving_average_14d"] = pd.DataFrame([ma.values] * horizon, index=idx, columns=train.columns)
    # 2) naive baseline: "tomorrow looks like today" (just repeat the last day)
    last = train.iloc[-1]
    preds["naive_last_day"] = pd.DataFrame([last.values] * horizon, index=idx, columns=train.columns)
    # 3) seasonal naive: "each future day looks like the same weekday last week"
    rows = [train.iloc[days - 7 + (i % 7)].values for i in range(horizon)]
    preds["seasonal_naive_7d"] = pd.DataFrame(rows, index=idx, columns=train.columns)
    return preds


def run_forecast(engine):
    """Backtest, then forecast the real future. Saves two tables to MySQL. Returns the numbers."""
    wide = load_sales(engine)
    regions = pd.read_sql("SELECT region_id, region_name FROM dim_region", engine)

    # ---------- backtest ----------
    train, test = wide.iloc[:-HORIZON], wide.iloc[-HORIZON:]
    preds = make_predictions(train, HORIZON)
    region_of_col = np.array(wide.columns.get_level_values("region_id"))
    scopes = [("All regions", np.ones(len(wide.columns), dtype=bool))]
    for _, r in regions.iterrows():
        scopes.append((r["region_name"], region_of_col == r["region_id"]))

    rows = []
    for model, pred in preds.items():
        for scope_name, mask in scopes:
            m = score(test, pred, mask)
            rows.append({"model": model, "scope": scope_name, **m})
    validation = pd.DataFrame(rows).round(2)
    validation.to_sql("forecast_validation", engine, if_exists="replace", index=False)

    # ---------- real forecast: next 30 days after the last day we have ----------
    ma_now = wide.tail(MA_WINDOW).mean()
    future = pd.date_range(wide.index[-1] + pd.Timedelta(days=1), periods=HORIZON)
    out = []
    for (pid, rid), value in ma_now.items():
        for d in future:
            out.append((int(pid), int(rid), d.date(), round(float(value), 2)))
    fc = pd.DataFrame(out, columns=["product_id", "region_id", "forecast_date", "forecast_units"])
    fc.to_sql("forecast_daily", engine, if_exists="replace", index=False,
              chunksize=2000, method="multi")
    return {"validation": validation, "forecast_rows": len(fc),
            "backtest_days": HORIZON, "train_days": len(train)}


def main():
    engine = config.get_engine()
    res = run_forecast(engine)
    print(f"Backtest: trained on first {res['train_days']} days, tested on last {res['backtest_days']} days.")
    v = res["validation"]
    print(v[v.scope == "All regions"].drop(columns="scope").to_string(index=False))
    print(f"\nSaved forecast_daily ({res['forecast_rows']} rows) and forecast_validation ({len(v)} rows).")


if __name__ == "__main__":
    main()
