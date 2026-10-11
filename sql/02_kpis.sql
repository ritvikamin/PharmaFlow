-- 02_kpis.sql : business KPIs written as SQL VIEWS.
-- A view is a saved SELECT query. The dashboard just reads from the views,
-- so the KPI logic lives in ONE place (here), not scattered across Python.

-- Drop old objects first (views that depend on other views go first).
DROP VIEW IF EXISTS v_region_stock_status;
DROP VIEW IF EXISTS v_stock_status;
DROP VIEW IF EXISTS v_days_of_cover;
DROP VIEW IF EXISTS v_on_time_delivery_site_region;
DROP VIEW IF EXISTS v_on_time_delivery_site;
DROP VIEW IF EXISTS v_stockout_rate_category;
DROP VIEW IF EXISTS v_stockout_rate_region;
DROP VIEW IF EXISTS v_as_of;
DROP TABLE IF EXISTS kpi_thresholds;

-- ---------------------------------------------------------------------------
-- Business thresholds live in a one-row table, so SQL and Python share them
-- and the business can change them without editing any query.
-- ---------------------------------------------------------------------------
CREATE TABLE kpi_thresholds (
    risk_days   INT NOT NULL,   -- fewer days of cover than this = insufficient stock
    excess_days INT NOT NULL    -- more days of cover than this  = excess stock
);
INSERT INTO kpi_thresholds (risk_days, excess_days) VALUES (7, 60);

-- ---------------------------------------------------------------------------
-- v_as_of : "today" = the latest day that has inventory data (one row).
-- ---------------------------------------------------------------------------
CREATE VIEW v_as_of AS
SELECT d.date_id AS as_of_id, d.full_date AS as_of_date
FROM dim_date d
WHERE d.date_id = (SELECT MAX(date_id) FROM fact_inventory);

-- ---------------------------------------------------------------------------
-- KPI 1: DAYS OF INVENTORY COVER (per product and region)
--   days of cover = units on hand today / average daily sales of the last 30 days
--   "If nothing is restocked, how many days until we run out at the recent selling rate?"
-- ---------------------------------------------------------------------------
CREATE VIEW v_days_of_cover AS
SELECT i.product_id,
       i.region_id,
       i.units_on_hand,
       ROUND(a.avg_daily_sales, 1) AS avg_daily_sales_30d,
       -- NULLIF turns a 0 into NULL so we never divide by zero
       ROUND(i.units_on_hand / NULLIF(a.avg_daily_sales, 0), 1) AS days_of_cover
FROM fact_inventory i
JOIN v_as_of o ON i.date_id = o.as_of_id              -- keep only today's stock rows
JOIN (
    -- average daily sales over the last 30 days, per product and region
    SELECT s.product_id, s.region_id, AVG(s.units_sold) AS avg_daily_sales
    FROM fact_sales s
    JOIN dim_date d ON d.date_id = s.date_id
    JOIN v_as_of o2 ON d.full_date > DATE_SUB(o2.as_of_date, INTERVAL 30 DAY)
    GROUP BY s.product_id, s.region_id
) a ON a.product_id = i.product_id AND a.region_id = i.region_id;

-- ---------------------------------------------------------------------------
-- KPI 2: STOCKOUT RATE
--   stockout rate = days where stock ended at 0 / all product-days, as a percent
-- ---------------------------------------------------------------------------
CREATE VIEW v_stockout_rate_region AS
SELECT r.region_name,
       COUNT(*) AS product_days,
       SUM(CASE WHEN i.units_on_hand = 0 THEN 1 ELSE 0 END) AS stockout_days,
       ROUND(100 * SUM(CASE WHEN i.units_on_hand = 0 THEN 1 ELSE 0 END) / COUNT(*), 2) AS stockout_rate_pct
FROM fact_inventory i
JOIN dim_region r ON r.region_id = i.region_id
GROUP BY r.region_name;

-- Same KPI, sliced by medicine category instead of region.
CREATE VIEW v_stockout_rate_category AS
SELECT p.category,
       COUNT(*) AS product_days,
       SUM(CASE WHEN i.units_on_hand = 0 THEN 1 ELSE 0 END) AS stockout_days,
       ROUND(100 * SUM(CASE WHEN i.units_on_hand = 0 THEN 1 ELSE 0 END) / COUNT(*), 2) AS stockout_rate_pct
FROM fact_inventory i
JOIN dim_product p ON p.product_id = i.product_id
GROUP BY p.category;

-- ---------------------------------------------------------------------------
-- KPI 3: ON-TIME DELIVERY % PER FACTORY (site)
--   Only shipments whose promised date has already passed are judged.
--   ON TIME = delivered on or before the promised date.
--   LATE    = delivered after it, OR still not delivered although it is due.
-- ---------------------------------------------------------------------------
CREATE VIEW v_on_time_delivery_site AS
SELECT st.site_name,
       COUNT(*) AS shipments_due,
       SUM(CASE WHEN f.delivered_date_id IS NOT NULL
                 AND f.delivered_date_id <= f.promised_date_id THEN 1 ELSE 0 END) AS on_time,
       SUM(CASE WHEN f.delivered_date_id IS NULL THEN 1 ELSE 0 END) AS still_in_transit,
       ROUND(100 * SUM(CASE WHEN f.delivered_date_id IS NOT NULL
                             AND f.delivered_date_id <= f.promised_date_id THEN 1 ELSE 0 END)
                 / COUNT(*), 1) AS on_time_pct,
       -- average days between promised and actual delivery (positive = late), delivered ones only
       ROUND(AVG(CASE WHEN f.delivered_date_id IS NOT NULL
                      THEN DATEDIFF(dd.full_date, dp.full_date) END), 1) AS avg_days_vs_promise
FROM fact_shipments f
JOIN dim_site st  ON st.site_id = f.site_id
JOIN dim_date dp  ON dp.date_id = f.promised_date_id
LEFT JOIN dim_date dd ON dd.date_id = f.delivered_date_id   -- LEFT JOIN: keeps undelivered rows
JOIN v_as_of o    ON f.promised_date_id <= o.as_of_id        -- only shipments already due
GROUP BY st.site_name;

-- Same KPI, one row per factory AND region, so the dashboard's region filter works.
-- (The dashboard adds these rows up again to get a percentage for the chosen region.)
CREATE VIEW v_on_time_delivery_site_region AS
SELECT st.site_name,
       r.region_name,
       COUNT(*) AS shipments_due,
       SUM(CASE WHEN f.delivered_date_id IS NOT NULL
                 AND f.delivered_date_id <= f.promised_date_id THEN 1 ELSE 0 END) AS on_time,
       SUM(CASE WHEN f.delivered_date_id IS NULL THEN 1 ELSE 0 END) AS still_in_transit
FROM fact_shipments f
JOIN dim_site st   ON st.site_id = f.site_id
JOIN dim_region r  ON r.region_id = f.region_id
JOIN v_as_of o     ON f.promised_date_id <= o.as_of_id
GROUP BY st.site_name, r.region_name;

-- ---------------------------------------------------------------------------
-- KPI 4: STOCK STATUS per product and region (uses the thresholds table)
--   Insufficient = cover < risk_days,  Excess = cover > excess_days,  else Healthy
--   shortage_units = units missing to reach risk_days of cover
--   excess_units   = units above excess_days of cover
-- ---------------------------------------------------------------------------
CREATE VIEW v_stock_status AS
SELECT c.product_id, c.region_id, c.units_on_hand, c.avg_daily_sales_30d, c.days_of_cover,
       CASE WHEN c.days_of_cover IS NULL            THEN 'No demand'
            WHEN c.days_of_cover < t.risk_days      THEN 'Insufficient'
            WHEN c.days_of_cover > t.excess_days    THEN 'Excess'
            ELSE 'Healthy' END AS status,
       GREATEST(ROUND(t.risk_days * c.avg_daily_sales_30d - c.units_on_hand), 0)   AS shortage_units,
       GREATEST(ROUND(c.units_on_hand - t.excess_days * c.avg_daily_sales_30d), 0) AS excess_units
FROM v_days_of_cover c
CROSS JOIN kpi_thresholds t;      -- one-row table, so every row gets the two thresholds

-- Roll the status up to one row per region.
CREATE VIEW v_region_stock_status AS
SELECT r.region_name,
       SUM(CASE WHEN s.status = 'Insufficient' THEN 1 ELSE 0 END) AS insufficient_items,
       SUM(CASE WHEN s.status = 'Healthy'      THEN 1 ELSE 0 END) AS healthy_items,
       SUM(CASE WHEN s.status = 'Excess'       THEN 1 ELSE 0 END) AS excess_items,
       SUM(s.shortage_units) AS shortage_units,
       SUM(s.excess_units)   AS excess_units
FROM v_stock_status s
JOIN dim_region r ON r.region_id = s.region_id
GROUP BY r.region_name;
