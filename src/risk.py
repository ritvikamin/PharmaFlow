"""
risk.py - the "which medicines are about to run out, and why?" step.

Run:   python src/risk.py      (after forecast.py)

For every product x region:
    days until empty = units on hand today / forecast daily demand
Fewer days than the risk threshold (7) -> flagged "At risk".
More days than the excess threshold (60) -> flagged "Excess".
Then we attach a plain-English REASON using three simple rules.
Result is saved to the MySQL table stock_risk (the dashboard reads it).
"""
import numpy as np
import pandas as pd
import config
import forecast

# Reason rules (thresholds for the "why" text)
LOW_ON_TIME_PCT = 70      # supplier counted as unreliable below this on-time %
DEMAND_SURGE_RATIO = 1.3  # recent demand 30%+ above the earlier month = surge


def run_risk(engine):
    th = pd.read_sql("SELECT risk_days, excess_days FROM kpi_thresholds", engine).iloc[0]
    risk_days, excess_days = int(th["risk_days"]), int(th["excess_days"])

    # today's stock + names
    stock = pd.read_sql("""
        SELECT c.product_id, c.region_id, p.product_name, p.category, r.region_name, c.units_on_hand
        FROM v_days_of_cover c
        JOIN dim_product p ON p.product_id = c.product_id
        JOIN dim_region r  ON r.region_id  = c.region_id""", engine)

    # forecast demand per day (average of the 30 forecast days)
    fc = pd.read_sql("""SELECT product_id, region_id, AVG(forecast_units) AS forecast_daily_demand
                        FROM forecast_daily GROUP BY product_id, region_id""", engine)
    df = stock.merge(fc, on=["product_id", "region_id"])

    # core formula. Where forecast demand is 0 we leave days_until_empty empty (can't divide by 0).
    demand = df["forecast_daily_demand"].where(df["forecast_daily_demand"] > 0)
    df["days_until_empty"] = (df["units_on_hand"] / demand).round(1)

    df["status"] = "OK"
    df.loc[df["days_until_empty"] < risk_days, "status"] = "At risk"
    df.loc[df["days_until_empty"] > excess_days, "status"] = "Excess"

    # ---------- the "why" ----------
    # supplier of each product + that supplier's on-time %
    supplier = pd.read_sql("""SELECT DISTINCT f.product_id, s.site_name FROM fact_shipments f
                              JOIN dim_site s ON s.site_id = f.site_id""", engine)
    ontime = pd.read_sql("SELECT site_name, on_time_pct FROM v_on_time_delivery_site", engine)
    supplier = supplier.merge(ontime, on="site_name")
    df = df.merge(supplier, on="product_id", how="left")

    # shipments for this product+region that are overdue and still on the road
    overdue = pd.read_sql("""
        SELECT f.product_id, f.region_id, COUNT(*) AS overdue_shipments
        FROM fact_shipments f JOIN v_as_of o ON f.promised_date_id <= o.as_of_id
        WHERE f.delivered_date_id IS NULL GROUP BY f.product_id, f.region_id""", engine)
    df = df.merge(overdue, on=["product_id", "region_id"], how="left")
    df["overdue_shipments"] = df["overdue_shipments"].fillna(0).astype(int)

    # demand trend: last 14 days vs the 30 days before that
    wide = forecast.load_sales(engine)
    recent = wide.tail(14).mean()
    earlier = wide.iloc[-44:-14].mean()
    ratio = (recent / earlier.where(earlier > 0))
    trend = pd.DataFrame({"product_id": [c[0] for c in ratio.index],
                          "region_id": [c[1] for c in ratio.index],
                          "demand_ratio": ratio.values})
    df = df.merge(trend, on=["product_id", "region_id"], how="left")

    def why(row):
        if row["status"] == "At risk":
            reasons = []
            if row["overdue_shipments"] > 0:
                reasons.append(f"{row['overdue_shipments']} shipment(s) overdue in transit")
            if pd.notna(row["on_time_pct"]) and row["on_time_pct"] < LOW_ON_TIME_PCT:
                reasons.append(f"supplier {row['site_name']} on time only {row['on_time_pct']:.0f}%")
            if pd.notna(row["demand_ratio"]) and row["demand_ratio"] > DEMAND_SURGE_RATIO:
                reasons.append(f"demand up {100 * (row['demand_ratio'] - 1):.0f}% vs prior month")
            return "; ".join(reasons) if reasons else "stock low relative to forecast demand"
        if row["status"] == "Excess":
            return f"{row['days_until_empty']:.0f} days of stock: over-ordered, expiry risk"
        return ""

    df["reason"] = df.apply(why, axis=1)
    out = df[["product_id", "region_id", "product_name", "category", "region_name", "site_name",
              "units_on_hand", "forecast_daily_demand", "days_until_empty", "status", "reason"]].copy()
    out["forecast_daily_demand"] = out["forecast_daily_demand"].round(1)
    out = out.sort_values("days_until_empty")
    out.to_sql("stock_risk", engine, if_exists="replace", index=False)
    return out


def main():
    engine = config.get_engine()
    out = run_risk(engine)
    print(out["status"].value_counts().to_string(), "\n")
    pd.set_option("display.width", 220)
    pd.set_option("display.max_colwidth", 70)
    flagged = out[out.status == "At risk"][["product_name", "region_name", "units_on_hand",
                    "forecast_daily_demand", "days_until_empty", "reason"]]
    print(flagged.to_string(index=False))


if __name__ == "__main__":
    main()
