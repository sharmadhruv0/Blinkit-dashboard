"""
Blinkit Sales Analysis Dashboard — ETL & Data Preprocessing Pipeline
====================================================================
Layer 1 of the 3-Layer Data Science & DBMS Architecture:
  1. Extract : Load raw Blinkit Grocery Sales CSV from data/raw/ (or generate a
               realistic 8,523-record synthetic fallback dataset containing
               authentic dirty-data edge cases).
  2. Transform: Standardize categorical labels, impute null weights and zero
               visibilities by item category, and engineer derived analytics
               features (Outlet_Age, Sales_Tier).
  3. Load    : Save cleaned CSVs to data/processed/, execute scripts/schema.sql,
               normalize into relational tables (outlets, products,
               sales_transactions) inside data/processed/blinkit.db, and
               verify pre-built SQL analytical views.

Usage:
    python scripts/etl_pipeline.py
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# -----------------------------------------------------------------------------
# Configuration & Paths
# -----------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
SCHEMA_PATH = PROJECT_ROOT / "scripts" / "schema.sql"
DB_PATH = PROCESSED_DIR / "blinkit.db"
FALLBACK_RAW_CSV = RAW_DIR / "blinkit_sales_raw.csv"

EXPECTED_COLUMNS = [
    "Item_Identifier",
    "Item_Fat_Content",
    "Item_Type",
    "Outlet_Identifier",
    "Outlet_Establishment_Year",
    "Outlet_Size",
    "Outlet_Location_Type",
    "Outlet_Type",
    "Item_Visibility",
    "Item_Weight",
    "Sales",
    "Rating",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("blinkit_etl")


# -----------------------------------------------------------------------------
# 1. Synthetic Fallback Dataset Generator (8,523 Realistic Dirty Records)
# -----------------------------------------------------------------------------
def generate_synthetic_blinkit_data(n_rows: int = 8523, seed: int = 42) -> pd.DataFrame:
    """
    Generate a realistic Blinkit Grocery Sales dataset matching the standard
    Kaggle schema, including authentic dirty-data edge cases:
      - Inconsistent Item_Fat_Content labels ('LF', 'low fat', 'reg')
      - ~17% missing Item_Weight values (NaN)
      - ~6% zero Item_Visibility entries (0.0)
    """
    rng = np.random.default_rng(seed)

    # 16 authentic Blinkit / Kaggle grocery categories: (name, weight_prob, avg_wt, avg_price)
    categories = [
        ("Fruits and Vegetables", 0.145, 13.2, 149.5),
        ("Snack Foods",           0.141, 13.0, 148.0),
        ("Household",             0.107, 13.4, 151.0),
        ("Frozen Foods",          0.100, 12.8, 140.0),
        ("Dairy",                 0.080, 13.4, 149.0),
        ("Canned",                0.076, 12.3, 140.5),
        ("Baking Goods",          0.076, 12.2, 128.0),
        ("Health and Hygiene",    0.061, 13.1, 132.5),
        ("Soft Drinks",           0.052, 11.8, 133.0),
        ("Meat",                  0.050, 12.8, 142.0),
        ("Breads",                0.029, 11.3, 141.5),
        ("Hard Drinks",           0.025, 11.4, 138.0),
        ("Others",                0.020, 13.8, 134.0),
        ("Starchy Foods",         0.017, 13.7, 148.0),
        ("Breakfast",             0.013, 12.8, 142.5),
        ("Seafood",               0.008, 12.5, 144.0),
    ]
    cat_names = [c[0] for c in categories]
    cat_probs = np.array([c[1] for c in categories], dtype=float)
    cat_probs /= cat_probs.sum()
    cat_avg_wt = {c[0]: c[2] for c in categories}
    cat_avg_price = {c[0]: c[3] for c in categories}

    # Build a realistic catalog of ~1,559 unique product SKUs
    n_products = 1559
    prefixes = {"Fruits and Vegetables": "FD", "Snack Foods": "FD", "Frozen Foods": "FD",
                "Dairy": "FD", "Canned": "FD", "Baking Goods": "FD", "Meat": "FD",
                "Breads": "FD", "Starchy Foods": "FD", "Breakfast": "FD", "Seafood": "FD",
                "Soft Drinks": "DR", "Hard Drinks": "DR",
                "Household": "NC", "Health and Hygiene": "NC", "Others": "NC"}

    letters = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    used_ids: set[str] = set()
    product_catalog = []

    sampled_cat_indices = rng.choice(len(cat_names), size=n_products, p=cat_probs)
    for idx in sampled_cat_indices:
        cat = cat_names[idx]
        prefix = prefixes[cat]
        while True:
            item_id = f"{prefix}{letters[rng.integers(0, 26)]}{rng.integers(10, 99)}"
            if item_id not in used_ids:
                used_ids.add(item_id)
                break

        # Non-consumables lean strongly Low Fat; food items ~60/40 Low Fat / Regular
        if prefix == "NC":
            true_fat = "Low Fat"
        else:
            true_fat = "Low Fat" if rng.random() < 0.60 else "Regular"

        true_weight = round(float(np.clip(rng.normal(cat_avg_wt[cat], 3.8), 4.5, 21.5)), 2)
        base_price = float(np.clip(rng.normal(cat_avg_price[cat], 54.0), 32.0, 266.0))

        product_catalog.append(
            {
                "Item_Identifier": item_id,
                "Item_Type": cat,
                "True_Fat": true_fat,
                "True_Weight": true_weight,
                "Base_Price": base_price,
            }
        )

    # 10 realistic Blinkit dark-store & supermarket outlets spanning Tier 1/2/3 & 2011–2022
    outlets = [
        # (id, year, size, location_type, outlet_type, share_weight, sales_mult, base_rating)
        ("OUT027", 2012, "Medium", "Tier 3", "Supermarket Type3", 0.115, 1.14, 4.18),
        ("OUT013", 2011, "High",   "Tier 3", "Supermarket Type1", 0.112, 1.04, 4.02),
        ("OUT049", 2015, "Medium", "Tier 1", "Supermarket Type1", 0.110, 1.07, 4.08),
        ("OUT046", 2017, "Small",  "Tier 1", "Supermarket Type1", 0.109, 1.02, 3.96),
        ("OUT035", 2018, "Small",  "Tier 2", "Supermarket Type1", 0.108, 1.06, 4.10),
        ("OUT045", 2016, "Medium", "Tier 2", "Supermarket Type1", 0.106, 0.99, 3.94),
        ("OUT018", 2020, "Medium", "Tier 3", "Supermarket Type2", 0.108, 0.97, 3.91),
        ("OUT017", 2022, "High",   "Tier 2", "Supermarket Type1", 0.104, 1.05, 4.12),
        ("OUT010", 2014, "Small",  "Tier 3", "Grocery Store",     0.066, 0.84, 3.68),
        ("OUT019", 2019, "Small",  "Tier 1", "Grocery Store",     0.062, 0.88, 3.74),
    ]
    outlet_probs = np.array([o[5] for o in outlets], dtype=float)
    outlet_probs /= outlet_probs.sum()

    # Sample transactions
    prod_indices = rng.integers(0, len(product_catalog), size=n_rows)
    outlet_indices = rng.choice(len(outlets), size=n_rows, p=outlet_probs)

    records = []
    for p_idx, o_idx in zip(prod_indices, outlet_indices):
        prod = product_catalog[p_idx]
        out = outlets[o_idx]

        # Inject dirty Item_Fat_Content labels (~12% dirty variants)
        if prod["True_Fat"] == "Low Fat":
            fat_label = rng.choice(["Low Fat", "LF", "low fat"], p=[0.88, 0.07, 0.05])
        else:
            fat_label = rng.choice(["Regular", "reg"], p=[0.90, 0.10])

        # Inject ~17% missing Item_Weight values
        weight = np.nan if rng.random() < 0.17 else prod["True_Weight"]

        # Inject ~6% zero Item_Visibility entries
        if rng.random() < 0.06:
            visibility = 0.0
        else:
            vis_scale = 0.095 if out[4] == "Grocery Store" else 0.062
            visibility = round(float(np.clip(rng.gamma(shape=2.2, scale=vis_scale / 2.2), 0.004, 0.32)), 6)

        # Realistic sales amount & customer rating
        sales_val = prod["Base_Price"] * out[6] + rng.normal(0.0, 14.0)
        sales_val = round(float(np.clip(sales_val, 31.29, 266.89)), 4)

        rating_val = out[7] + rng.normal(0.0, 0.52)
        rating_val = round(float(np.clip(rating_val, 1.0, 5.0)), 1)

        records.append(
            {
                "Item_Identifier": prod["Item_Identifier"],
                "Item_Fat_Content": fat_label,
                "Item_Type": prod["Item_Type"],
                "Outlet_Identifier": out[0],
                "Outlet_Establishment_Year": out[1],
                "Outlet_Size": out[2],
                "Outlet_Location_Type": out[3],
                "Outlet_Type": out[4],
                "Item_Visibility": visibility,
                "Item_Weight": weight,
                "Sales": sales_val,
                "Rating": rating_val,
            }
        )

    return pd.DataFrame(records, columns=EXPECTED_COLUMNS)


# -----------------------------------------------------------------------------
# 2. Extract
# -----------------------------------------------------------------------------
def extract_raw_data() -> tuple[pd.DataFrame, Path]:
    """
    Locate a raw CSV inside data/raw/. If none is found, generate and persist
    the 8,523-record synthetic fallback dataset so the pipeline is self-contained.
    """
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    csv_files = sorted(RAW_DIR.glob("*.csv"))

    if csv_files:
        source_path = csv_files[0]
        logger.info("Found raw dataset: %s", source_path)
        df = pd.read_csv(source_path)
    else:
        logger.info(
            "No CSV found in %s — generating 8,523 synthetic Blinkit records...",
            RAW_DIR,
        )
        df = generate_synthetic_blinkit_data(n_rows=8523, seed=42)
        df.to_csv(FALLBACK_RAW_CSV, index=False)
        source_path = FALLBACK_RAW_CSV
        logger.info("Saved fallback raw dataset to: %s", source_path)

    # Normalize column names to handle space-separated Kaggle variants
    # e.g. 'Item Fat Content' -> 'Item_Fat_Content'
    df.columns = [c.strip().replace(" ", "_") for c in df.columns]

    missing_cols = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(
            f"Raw dataset {source_path.name} is missing required columns: {missing_cols}"
        )

    logger.info("Extracted %s raw rows x %s columns.", f"{len(df):,}", df.shape[1])
    return df[EXPECTED_COLUMNS].copy(), source_path


# -----------------------------------------------------------------------------
# 3. Transform (Cleaning & Feature Engineering)
# -----------------------------------------------------------------------------
def transform_data(raw_df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean inconsistencies, impute nulls/zeros, and engineer derived features:
      - Standardize Item_Fat_Content ('LF', 'low fat' -> 'Low Fat'; 'reg' -> 'Regular')
      - Impute missing Item_Weight with mean weight grouped by Item_Type
      - Replace zero/null Item_Visibility with mean non-zero visibility per Item_Type
      - Impute any missing Outlet_Size with mode grouped by Outlet_Type
      - Engineer Outlet_Age (current year - Outlet_Establishment_Year)
      - Engineer Sales_Tier ('Low', 'Medium', 'High')
    """
    df = raw_df.copy()

    # Audit dirty data before cleaning
    raw_fat_values = sorted(df["Item_Fat_Content"].dropna().astype(str).unique().tolist())
    null_weights_before = int(df["Item_Weight"].isna().sum())
    zero_vis_before = int((df["Item_Visibility"].fillna(0) <= 0).sum())
    logger.info(
        "Pre-cleaning audit | Fat labels=%s | Null Item_Weight=%d | Zero Item_Visibility=%d",
        raw_fat_values,
        null_weights_before,
        zero_vis_before,
    )

    # Trim whitespace on string columns
    str_cols = [
        "Item_Identifier",
        "Item_Fat_Content",
        "Item_Type",
        "Outlet_Identifier",
        "Outlet_Size",
        "Outlet_Location_Type",
        "Outlet_Type",
    ]
    for col in str_cols:
        df[col] = df[col].astype("string").str.strip()

    # 1) Standardize Item_Fat_Content
    fat_map = {
        "lf": "Low Fat",
        "low fat": "Low Fat",
        "low_fat": "Low Fat",
        "lowfat": "Low Fat",
        "reg": "Regular",
        "regular": "Regular",
    }
    df["Item_Fat_Content"] = (
        df["Item_Fat_Content"]
        .str.lower()
        .map(fat_map)
        .fillna("Low Fat")
    )

    # 2) Numeric coercions
    for num_col in ["Item_Weight", "Item_Visibility", "Sales", "Rating", "Outlet_Establishment_Year"]:
        df[num_col] = pd.to_numeric(df[num_col], errors="coerce")

    # 3) Impute missing Item_Weight with mean grouped by Item_Type
    global_mean_weight = float(df["Item_Weight"].mean())
    type_mean_weight = df.groupby("Item_Type")["Item_Weight"].transform("mean")
    df["Item_Weight"] = df["Item_Weight"].fillna(type_mean_weight).fillna(global_mean_weight).round(2)

    # 4) Replace zero (or null) Item_Visibility with mean non-zero visibility per Item_Type
    df.loc[df["Item_Visibility"] <= 0, "Item_Visibility"] = np.nan
    global_mean_vis = float(df["Item_Visibility"].mean())
    type_mean_vis = df.groupby("Item_Type")["Item_Visibility"].transform("mean")
    df["Item_Visibility"] = df["Item_Visibility"].fillna(type_mean_vis).fillna(global_mean_vis).round(6)

    # 5) Defensive imputation for Outlet_Size / Sales / Rating (for external Kaggle CSVs)
    if df["Outlet_Size"].isna().any():
        outlet_type_mode = (
            df.groupby("Outlet_Type")["Outlet_Size"]
            .agg(lambda s: s.mode().iloc[0] if not s.mode().empty else "Medium")
            .to_dict()
        )
        df["Outlet_Size"] = df["Outlet_Size"].fillna(df["Outlet_Type"].map(outlet_type_mode)).fillna("Medium")

    df["Sales"] = df["Sales"].fillna(df["Sales"].median()).clip(lower=0.0).round(2)
    df["Rating"] = df["Rating"].fillna(df["Rating"].median()).clip(lower=0.0, upper=5.0).round(1)
    df["Outlet_Establishment_Year"] = df["Outlet_Establishment_Year"].astype(int)

    # 6) Feature Engineering
    current_year = datetime.now().year
    df["Outlet_Age"] = (current_year - df["Outlet_Establishment_Year"]).clip(lower=0).astype(int)

    df["Sales_Tier"] = pd.cut(
        df["Sales"],
        bins=[-np.inf, 100.0, 180.0, np.inf],
        labels=["Low", "Medium", "High"],
        right=False,
    ).astype(str)

    logger.info(
        "Post-cleaning audit | Fat labels=%s | Null Item_Weight=%d | Zero Item_Visibility=%d",
        sorted(df["Item_Fat_Content"].unique().tolist()),
        int(df["Item_Weight"].isna().sum()),
        int((df["Item_Visibility"] <= 0).sum()),
    )
    logger.info(
        "Engineered features | Outlet_Age range=[%d, %d] | Sales_Tier counts=%s",
        int(df["Outlet_Age"].min()),
        int(df["Outlet_Age"].max()),
        df["Sales_Tier"].value_counts().to_dict(),
    )
    return df


# -----------------------------------------------------------------------------
# 4. Normalize & Load into SQLite + Cleaned CSVs
# -----------------------------------------------------------------------------
def _first_mode(series: pd.Series) -> str:
    modes = series.mode()
    return str(modes.iloc[0]) if not modes.empty else str(series.iloc[0])


def load_to_sqlite_and_csv(clean_df: pd.DataFrame) -> None:
    """
    Persist cleaned flat CSV and normalized dimensional tables to data/processed/,
    execute scripts/schema.sql, load into blinkit.db, and verify SQL Views.
    """
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # Save cleaned master CSV
    cleaned_csv_path = PROCESSED_DIR / "blinkit_sales_cleaned.csv"
    clean_df.to_csv(cleaned_csv_path, index=False)
    logger.info("Saved cleaned CSV: %s", cleaned_csv_path)

    # Build normalized Dimension & Fact DataFrames
    outlets_df = (
        clean_df.groupby("Outlet_Identifier", as_index=False)
        .agg(
            outlet_establishment_year=("Outlet_Establishment_Year", "first"),
            outlet_size=("Outlet_Size", _first_mode),
            outlet_location_type=("Outlet_Location_Type", _first_mode),
            outlet_type=("Outlet_Type", _first_mode),
            outlet_age=("Outlet_Age", "first"),
        )
        .rename(columns={"Outlet_Identifier": "outlet_identifier"})
    )

    products_df = (
        clean_df.groupby("Item_Identifier", as_index=False)
        .agg(
            item_type=("Item_Type", _first_mode),
            item_fat_content=("Item_Fat_Content", _first_mode),
            item_weight=("Item_Weight", "mean"),
        )
        .rename(columns={"Item_Identifier": "item_identifier"})
    )
    products_df["item_weight"] = products_df["item_weight"].round(2)

    transactions_df = clean_df[
        [
            "Item_Identifier",
            "Outlet_Identifier",
            "Item_Visibility",
            "Sales",
            "Rating",
            "Sales_Tier",
        ]
    ].rename(
        columns={
            "Item_Identifier": "item_identifier",
            "Outlet_Identifier": "outlet_identifier",
            "Item_Visibility": "item_visibility",
            "Sales": "sales",
            "Rating": "rating",
            "Sales_Tier": "sales_tier",
        }
    )

    # Export normalized CSVs for inspection/portability
    outlets_df.to_csv(PROCESSED_DIR / "outlets.csv", index=False)
    products_df.to_csv(PROCESSED_DIR / "products.csv", index=False)
    transactions_df.to_csv(PROCESSED_DIR / "sales_transactions.csv", index=False)

    # Execute schema.sql and bulk insert into SQLite
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(schema_sql)

        conn.executemany(
            """
            INSERT INTO outlets (
                outlet_identifier,
                outlet_establishment_year,
                outlet_size,
                outlet_location_type,
                outlet_type,
                outlet_age
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            outlets_df.itertuples(index=False, name=None),
        )

        conn.executemany(
            """
            INSERT INTO products (
                item_identifier,
                item_type,
                item_fat_content,
                item_weight
            ) VALUES (?, ?, ?, ?)
            """,
            products_df.itertuples(index=False, name=None),
        )

        conn.executemany(
            """
            INSERT INTO sales_transactions (
                item_identifier,
                outlet_identifier,
                item_visibility,
                sales,
                rating,
                sales_tier
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            transactions_df.itertuples(index=False, name=None),
        )

        conn.commit()

        # Verify SQL Views
        kpi_row = pd.read_sql_query("SELECT * FROM vw_kpi_summary;", conn)
        cat_rows = pd.read_sql_query("SELECT * FROM vw_category_sales LIMIT 3;", conn)
        out_rows = pd.read_sql_query("SELECT * FROM vw_outlet_performance LIMIT 3;", conn)

    logger.info(
        "Loaded SQLite DB %s | outlets=%d | products=%d | sales_transactions=%d",
        DB_PATH,
        len(outlets_df),
        len(products_df),
        len(transactions_df),
    )
    logger.info("Verified vw_kpi_summary:\n%s", kpi_row.to_string(index=False))
    logger.info("Top 3 Categories (vw_category_sales):\n%s", cat_rows.to_string(index=False))
    logger.info("Top 3 Outlets (vw_outlet_performance):\n%s", out_rows.to_string(index=False))


def run_etl() -> None:
    """Execute the full Extract -> Transform -> Load pipeline."""
    logger.info("=== Starting Blinkit Sales ETL Pipeline ===")
    raw_df, _ = extract_raw_data()
    clean_df = transform_data(raw_df)
    load_to_sqlite_and_csv(clean_df)
    logger.info("=== Blinkit Sales ETL Pipeline Completed Successfully ===")


if __name__ == "__main__":
    run_etl()
