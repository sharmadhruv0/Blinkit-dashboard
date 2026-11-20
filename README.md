# Blinkit Sales Analysis Dashboard

An end-to-end **Data Science & DBMS Engineering** mini-project featuring a 3-layer analytics pipeline built with **Python, Pandas, SQLite, Streamlit, and Plotly**.

## Architecture Overview

```text
data/raw/*.csv (or auto-generated 8,523-row fallback)
        │
        ▼
┌───────────────────────────────────────────┐
│ Layer 1: ETL & Preprocessing              │  scripts/etl_pipeline.py
│  • Clean labels, impute nulls & zeros     │
│  • Feature engineering (Outlet_Age, Tier) │
└───────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────┐
│ Layer 2: Relational SQLite Database       │  scripts/schema.sql
│  • 3NF Star Schema: outlets, products,    │  data/processed/blinkit.db
│    sales_transactions (with FK & indexes) │
│  • Pre-built Views: vw_kpi_summary,       │
│    vw_category_sales, vw_outlet_performance
└───────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────┐
│ Layer 3: Interactive Executive Dashboard  │  app_streamlit/app.py
│  • Blinkit dark-mode UI (Neon Green/Gold) │
│  • Real-time SQL queries & Plotly charts  │
│  • CSV Export & Live SQL Query Inspector  │
└───────────────────────────────────────────┘
```

## Project Structure

```text
blinkit sales analysis dashboard/
├── data/
│   ├── raw/                        # Place Kaggle Blinkit CSV here (auto-generated if empty)
│   └── processed/                  # Cleaned CSVs + normalized SQLite DB (blinkit.db)
├── scripts/
│   ├── etl_pipeline.py             # Extract, clean, engineer features, load SQLite
│   └── schema.sql                  # Normalized tables, indexes, and analytical SQL views
├── app_streamlit/
│   └── app.py                      # Streamlit + Plotly dark-mode analytics dashboard
├── requirements.txt
└── README.md
```

## Key Features

### 1. ETL & Data Preprocessing (`scripts/etl_pipeline.py`)
- **Kaggle Schema Compatible:** Accepts standard Blinkit Grocery Sales CSV files (both underscore and space-separated headers).
- **Self-Contained Fallback:** Automatically generates **8,523 realistic Blinkit records** (including dirty data edge cases such as `"LF"`, `"low fat"`, `"reg"`, ~17% null `Item_Weight`, and ~6% zero `Item_Visibility`) if `data/raw/` is empty.
- **Data Cleaning:**
  - Standardizes `Item_Fat_Content` (`"LF"`, `"low fat"` → `"Low Fat"`; `"reg"` → `"Regular"`).
  - Imputes missing `Item_Weight` using the mean weight grouped by `Item_Type`.
  - Replaces zero `Item_Visibility` values with the item category's mean non-zero visibility.
- **Feature Engineering:**
  - `Outlet_Age` = `Current Year - Outlet_Establishment_Year`
  - `Sales_Tier` = `Low` (`< ₹100`), `Medium` (`₹100–₹179.99`), `High` (`≥ ₹180`)

### 2. Relational Database & SQL Views (`scripts/schema.sql`)
- **Normalized Tables:** `outlets`, `products`, and `sales_transactions` with enforced `FOREIGN KEY` constraints and analytical indexes.
- **Analytical SQL Views:**
  - `vw_kpi_summary`
  - `vw_category_sales`
  - `vw_outlet_performance`
  - `vw_sales_master`

### 3. Executive Web Dashboard (`app_streamlit/app.py`)
- **Official Blinkit Design:** Clean light storefront layout (`#F6F7F9` / `#FFFFFF`) with Blinkit Yellow (`#F8CB46`), Blinkit Green (`#0C831F`), and crisp dark typography built for clarity during live presentations.
- **Interactive Sidebar Slicers:** Outlet Location Type, Outlet Type, Item Category, Fat Content, Establishment Year range slider, and one-click **Download Filtered Report (CSV)**.
- **4 Executive KPI Cards:** Total Sales (₹), Total Items Sold, Average Sales per Item, and Average Customer Rating (`/ 5.0`).
- **4 Interactive Plotly Charts:**
  1. Horizontal sorted **Sales by Product Category** bar chart.
  2. Interactive **Outlet Tier & Size Breakdown** (Sunburst & Donut toggle).
  3. **Outlet Establishment Trend** (dual-axis Sales area + Cumulative Outlets expansion).
  4. **Outlet Type Matrix** (grouped dual-axis Total Sales vs. Average Rating).
- **Data Explorer & SQL Inspector:** Top 100 filtered records table, live parameterized SQL query viewer, and live preview of SQLite schema & pre-built views.

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **(Optional) Add Kaggle Dataset:**
   Place your Blinkit Grocery Sales `.csv` inside `data/raw/`. If omitted, the ETL script automatically generates a realistic 8,523-record dataset.

3. **Run the ETL Pipeline:**
   ```bash
   python scripts/etl_pipeline.py
   ```

4. **Launch the Dashboard:**
   ```bash
   streamlit run app_streamlit/app.py
   ```
