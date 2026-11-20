-- =============================================================================
-- Blinkit Sales Analysis Dashboard — Relational Schema & Analytical Views
-- Database Engine : SQLite 3
-- Architecture    : 3NF / Star Schema (outlets, products, sales_transactions)
-- =============================================================================

PRAGMA foreign_keys = ON;

-- -----------------------------------------------------------------------------
-- 1. Clean Teardown (Idempotent Re-execution)
-- -----------------------------------------------------------------------------
DROP VIEW IF EXISTS vw_outlet_performance;
DROP VIEW IF EXISTS vw_category_sales;
DROP VIEW IF EXISTS vw_kpi_summary;
DROP VIEW IF EXISTS vw_sales_master;

DROP TABLE IF EXISTS sales_transactions;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS outlets;

-- -----------------------------------------------------------------------------
-- 2. Dimension Table: outlets
-- -----------------------------------------------------------------------------
CREATE TABLE outlets (
    outlet_identifier         TEXT    PRIMARY KEY,
    outlet_establishment_year INTEGER NOT NULL,
    outlet_size               TEXT    NOT NULL,
    outlet_location_type      TEXT    NOT NULL,
    outlet_type               TEXT    NOT NULL,
    outlet_age                INTEGER NOT NULL CHECK (outlet_age >= 0)
);

-- -----------------------------------------------------------------------------
-- 3. Dimension Table: products
-- -----------------------------------------------------------------------------
CREATE TABLE products (
    item_identifier  TEXT PRIMARY KEY,
    item_type        TEXT NOT NULL,
    item_fat_content TEXT NOT NULL CHECK (item_fat_content IN ('Low Fat', 'Regular')),
    item_weight      REAL NOT NULL CHECK (item_weight > 0)
);

-- -----------------------------------------------------------------------------
-- 4. Fact Table: sales_transactions
-- -----------------------------------------------------------------------------
CREATE TABLE sales_transactions (
    transaction_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    item_identifier   TEXT    NOT NULL,
    outlet_identifier TEXT    NOT NULL,
    item_visibility   REAL    NOT NULL CHECK (item_visibility > 0),
    sales             REAL    NOT NULL CHECK (sales >= 0),
    rating            REAL    NOT NULL CHECK (rating >= 0.0 AND rating <= 5.0),
    sales_tier        TEXT    NOT NULL CHECK (sales_tier IN ('Low', 'Medium', 'High')),
    FOREIGN KEY (item_identifier)   REFERENCES products(item_identifier)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    FOREIGN KEY (outlet_identifier) REFERENCES outlets(outlet_identifier)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

-- -----------------------------------------------------------------------------
-- 5. Analytical Indexes
-- -----------------------------------------------------------------------------
CREATE INDEX idx_sales_item      ON sales_transactions(item_identifier);
CREATE INDEX idx_sales_outlet    ON sales_transactions(outlet_identifier);
CREATE INDEX idx_sales_tier      ON sales_transactions(sales_tier);
CREATE INDEX idx_products_filter ON products(item_type, item_fat_content);
CREATE INDEX idx_outlets_filter  ON outlets(outlet_location_type, outlet_type, outlet_establishment_year);

-- -----------------------------------------------------------------------------
-- 6. Pre-Built Analytical SQL Views
-- -----------------------------------------------------------------------------

-- Master joined view combining fact and dimension tables
CREATE VIEW vw_sales_master AS
SELECT
    st.transaction_id,
    st.item_identifier,
    p.item_type,
    p.item_fat_content,
    p.item_weight,
    st.outlet_identifier,
    o.outlet_establishment_year,
    o.outlet_age,
    o.outlet_size,
    o.outlet_location_type,
    o.outlet_type,
    st.item_visibility,
    st.sales,
    st.rating,
    st.sales_tier
FROM sales_transactions st
INNER JOIN products p ON st.item_identifier   = p.item_identifier
INNER JOIN outlets  o ON st.outlet_identifier = o.outlet_identifier;

-- Executive KPI Summary View
CREATE VIEW vw_kpi_summary AS
SELECT
    ROUND(SUM(st.sales), 2)                                                  AS total_sales,
    COUNT(st.transaction_id)                                                 AS total_items_sold,
    ROUND(AVG(st.sales), 2)                                                  AS avg_sales_per_item,
    ROUND(AVG(st.rating), 2)                                                 AS avg_rating,
    COUNT(DISTINCT st.outlet_identifier)                                     AS total_outlets,
    COUNT(DISTINCT p.item_type)                                              AS total_categories,
    ROUND(
        100.0 * SUM(CASE WHEN st.sales_tier = 'High' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(st.transaction_id), 0),
        2
    )                                                                        AS high_tier_share_pct
FROM sales_transactions st
INNER JOIN products p ON st.item_identifier = p.item_identifier;

-- Product Category Sales Performance View
CREATE VIEW vw_category_sales AS
SELECT
    p.item_type,
    COUNT(st.transaction_id)                                                 AS total_items_sold,
    ROUND(SUM(st.sales), 2)                                                  AS total_sales,
    ROUND(AVG(st.sales), 2)                                                  AS avg_sales,
    ROUND(AVG(st.rating), 2)                                                 AS avg_rating,
    ROUND(AVG(p.item_weight), 2)                                             AS avg_item_weight,
    ROUND(
        100.0 * SUM(st.sales) / NULLIF((SELECT SUM(sales) FROM sales_transactions), 0),
        2
    )                                                                        AS sales_share_pct
FROM sales_transactions st
INNER JOIN products p ON st.item_identifier = p.item_identifier
GROUP BY p.item_type
ORDER BY total_sales DESC;

-- Outlet Performance View
CREATE VIEW vw_outlet_performance AS
SELECT
    o.outlet_identifier,
    o.outlet_type,
    o.outlet_location_type,
    o.outlet_size,
    o.outlet_establishment_year,
    o.outlet_age,
    COUNT(st.transaction_id)                                                 AS total_items_sold,
    ROUND(SUM(st.sales), 2)                                                  AS total_sales,
    ROUND(AVG(st.sales), 2)                                                  AS avg_sales,
    ROUND(AVG(st.rating), 2)                                                 AS avg_rating,
    ROUND(
        100.0 * SUM(st.sales) / NULLIF((SELECT SUM(sales) FROM sales_transactions), 0),
        2
    )                                                                        AS sales_share_pct
FROM sales_transactions st
INNER JOIN outlets o ON st.outlet_identifier = o.outlet_identifier
GROUP BY
    o.outlet_identifier,
    o.outlet_type,
    o.outlet_location_type,
    o.outlet_size,
    o.outlet_establishment_year,
    o.outlet_age
ORDER BY total_sales DESC;
