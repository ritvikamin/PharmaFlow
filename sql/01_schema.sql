-- 01_schema.sql : the STAR SCHEMA for PharmaFlow.
-- Idea: small "dimension" tables describe things (which product, where, when).
--       big "fact" tables record events (a sale, a stock count, a shipment)
--       and point at the dimensions through ID columns (foreign keys).

-- Drop old tables first (facts before dimensions, because facts depend on dimensions).
DROP TABLE IF EXISTS fact_shipments;
DROP TABLE IF EXISTS fact_inventory;
DROP TABLE IF EXISTS fact_sales;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_region;
DROP TABLE IF EXISTS dim_site;
DROP TABLE IF EXISTS dim_product;

-- ======================= DIMENSION TABLES =======================

-- One row per calendar day. date_id looks like 20261009 (easy to sort and join).
CREATE TABLE dim_date (
    date_id      INT         PRIMARY KEY,
    full_date    DATE        NOT NULL,
    year         INT         NOT NULL,
    month        INT         NOT NULL,
    day_of_week  VARCHAR(10) NOT NULL
);

-- One row per medicine.
CREATE TABLE dim_product (
    product_id      INT          PRIMARY KEY,
    product_name    VARCHAR(60)  NOT NULL,
    category        VARCHAR(30)  NOT NULL,
    shelf_life_days INT          NOT NULL,
    unit_cost       DECIMAL(10,2) NOT NULL
);

-- One row per manufacturing site (factory).
CREATE TABLE dim_site (
    site_id   INT         PRIMARY KEY,
    site_name VARCHAR(40) NOT NULL,
    country   VARCHAR(30) NOT NULL
);

-- One row per regional warehouse.
CREATE TABLE dim_region (
    region_id   INT         PRIMARY KEY,
    region_name VARCHAR(30) NOT NULL
);

-- ========================= FACT TABLES ==========================

-- GRAIN: one row = one product, in one region, on one day.
CREATE TABLE fact_sales (
    date_id    INT NOT NULL,
    product_id INT NOT NULL,
    region_id  INT NOT NULL,
    units_sold INT NOT NULL,
    PRIMARY KEY (date_id, product_id, region_id),
    FOREIGN KEY (date_id)    REFERENCES dim_date(date_id),
    FOREIGN KEY (product_id) REFERENCES dim_product(product_id),
    FOREIGN KEY (region_id)  REFERENCES dim_region(region_id)
);

-- GRAIN: one row = one product, in one region, at the END of one day.
CREATE TABLE fact_inventory (
    date_id       INT NOT NULL,
    product_id    INT NOT NULL,
    region_id     INT NOT NULL,
    units_on_hand INT NOT NULL,
    PRIMARY KEY (date_id, product_id, region_id),
    FOREIGN KEY (date_id)    REFERENCES dim_date(date_id),
    FOREIGN KEY (product_id) REFERENCES dim_product(product_id),
    FOREIGN KEY (region_id)  REFERENCES dim_region(region_id)
);

-- GRAIN: one row = one shipment (factory -> regional warehouse).
-- delivered_date_id is NULL while the shipment is still on the road.
CREATE TABLE fact_shipments (
    shipment_id        INT PRIMARY KEY,
    product_id         INT NOT NULL,
    site_id            INT NOT NULL,
    region_id          INT NOT NULL,
    ship_date_id       INT NOT NULL,
    promised_date_id   INT NOT NULL,
    delivered_date_id  INT NULL,
    units              INT NOT NULL,
    FOREIGN KEY (product_id)        REFERENCES dim_product(product_id),
    FOREIGN KEY (site_id)           REFERENCES dim_site(site_id),
    FOREIGN KEY (region_id)         REFERENCES dim_region(region_id),
    FOREIGN KEY (ship_date_id)      REFERENCES dim_date(date_id),
    FOREIGN KEY (promised_date_id)  REFERENCES dim_date(date_id),
    FOREIGN KEY (delivered_date_id) REFERENCES dim_date(date_id)
);

-- Indexes make the KPI queries fast (they filter and group by these columns a lot).
CREATE INDEX idx_ship_site   ON fact_shipments (site_id);
CREATE INDEX idx_sales_prod  ON fact_sales (product_id, region_id);
