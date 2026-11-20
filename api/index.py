"""
Blinkit Sales Analysis Dashboard — Vercel Python (Flask + SQLite + Plotly.js)
=============================================================================
Serverless WSGI entrypoint for Vercel deployment. Queries the exact same
normalized SQLite database (data/processed/blinkit.db) in read-only URI mode
and renders the official Blinkit-themed interactive dashboard.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template_string, request

app = Flask(__name__)

# Resolve project root & bundled files safely across local + Vercel serverless paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_file(rel_path: str) -> Path:
    candidates = [
        PROJECT_ROOT / rel_path,
        Path.cwd() / rel_path,
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


DB_PATH = _resolve_file("data/processed/blinkit.db")
SCHEMA_PATH = _resolve_file("scripts/schema.sql")


def get_connection() -> sqlite3.Connection:
    """Open SQLite in read-only URI mode so it works on Vercel's read-only filesystem."""
    uri = f"{DB_PATH.resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def query_all(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def load_options() -> dict[str, Any]:
    with get_connection() as conn:
        loc_types = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT outlet_location_type FROM outlets ORDER BY outlet_location_type;"
            ).fetchall()
        ]
        outlet_types = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT outlet_type FROM outlets ORDER BY outlet_type;"
            ).fetchall()
        ]
        item_types = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT item_type FROM products ORDER BY item_type;"
            ).fetchall()
        ]
        fat_contents = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT item_fat_content FROM products ORDER BY item_fat_content;"
            ).fetchall()
        ]
        yr = conn.execute(
            "SELECT MIN(outlet_establishment_year), MAX(outlet_establishment_year) FROM outlets;"
        ).fetchone()
        total_rows = conn.execute("SELECT COUNT(*) FROM sales_transactions;").fetchone()[0]

    return {
        "loc_types": loc_types,
        "outlet_types": outlet_types,
        "item_types": item_types,
        "fat_contents": fat_contents,
        "min_year": int(yr[0]),
        "max_year": int(yr[1]),
        "total_rows": int(total_rows),
    }


def parse_filters(opts: dict[str, Any]) -> tuple[str, tuple[Any, ...], dict[str, Any]]:
    """Build a concise parameterized WHERE clause from query parameters."""
    loc_types = request.args.getlist("loc") or opts["loc_types"]
    outlet_types = request.args.getlist("outlet_type") or opts["outlet_types"]
    item_types = request.args.getlist("category") or opts["item_types"]
    fat_contents = request.args.getlist("fat") or opts["fat_contents"]

    try:
        year_min = int(request.args.get("year_min", opts["min_year"]))
    except ValueError:
        year_min = opts["min_year"]
    try:
        year_max = int(request.args.get("year_max", opts["max_year"]))
    except ValueError:
        year_max = opts["max_year"]

    if year_min > year_max:
        year_min, year_max = year_max, year_min

    conditions: list[str] = []
    params: list[Any] = []

    if year_min > opts["min_year"] or year_max < opts["max_year"]:
        conditions.append("o.outlet_establishment_year BETWEEN ? AND ?")
        params.extend([year_min, year_max])

    def _add_if_subset(column: str, selected: list[str], all_vals: list[str]) -> None:
        if set(selected) != set(all_vals):
            placeholders = ", ".join(["?"] * len(selected))
            conditions.append(f"{column} IN ({placeholders})")
            params.extend(selected)

    _add_if_subset("o.outlet_location_type", loc_types, opts["loc_types"])
    _add_if_subset("o.outlet_type", outlet_types, opts["outlet_types"])
    _add_if_subset("p.item_type", item_types, opts["item_types"])
    _add_if_subset("p.item_fat_content", fat_contents, opts["fat_contents"])

    where_clause = ("\nWHERE " + "\n  AND ".join(conditions)) if conditions else ""
    meta = {
        "year_min": year_min,
        "year_max": year_max,
    }
    return where_clause, tuple(params), meta


def format_sql_preview(sql: str, params: tuple[Any, ...]) -> str:
    formatted = "\n".join(line.rstrip() for line in sql.strip().splitlines())
    for p in params:
        val = f"'{p}'" if isinstance(p, str) else str(p)
        formatted = formatted.replace("?", val, 1)
    return formatted


@app.route("/api/options")
def api_options():
    return jsonify(load_options())


@app.route("/api/dashboard")
def api_dashboard():
    opts = load_options()
    where_clause, params, meta = parse_filters(opts)

    sql_kpi = f"""
SELECT
    COALESCE(ROUND(SUM(st.sales), 2), 0)  AS total_sales,
    COUNT(st.transaction_id)              AS total_items_sold,
    COALESCE(ROUND(AVG(st.sales), 2), 0)  AS avg_sales_per_item,
    COALESCE(ROUND(AVG(st.rating), 2), 0) AS avg_rating,
    COUNT(DISTINCT st.outlet_identifier)  AS active_outlets
FROM sales_transactions st
JOIN products p ON st.item_identifier   = p.item_identifier
JOIN outlets  o ON st.outlet_identifier = o.outlet_identifier{where_clause};
"""

    sql_category = f"""
SELECT
    p.item_type,
    COUNT(st.transaction_id) AS total_items_sold,
    ROUND(SUM(st.sales), 2)  AS total_sales,
    ROUND(AVG(st.rating), 2) AS avg_rating
FROM sales_transactions st
JOIN products p ON st.item_identifier   = p.item_identifier
JOIN outlets  o ON st.outlet_identifier = o.outlet_identifier{where_clause}
GROUP BY p.item_type
ORDER BY total_sales DESC;
"""

    sql_tier_size = f"""
SELECT
    o.outlet_location_type,
    o.outlet_size,
    COUNT(st.transaction_id) AS total_items_sold,
    ROUND(SUM(st.sales), 2)  AS total_sales
FROM sales_transactions st
JOIN products p ON st.item_identifier   = p.item_identifier
JOIN outlets  o ON st.outlet_identifier = o.outlet_identifier{where_clause}
GROUP BY o.outlet_location_type, o.outlet_size
ORDER BY o.outlet_location_type, total_sales DESC;
"""

    sql_trend = f"""
SELECT
    o.outlet_establishment_year,
    COUNT(DISTINCT o.outlet_identifier) AS outlet_count,
    COUNT(st.transaction_id)            AS total_items_sold,
    ROUND(SUM(st.sales), 2)             AS total_sales
FROM sales_transactions st
JOIN products p ON st.item_identifier   = p.item_identifier
JOIN outlets  o ON st.outlet_identifier = o.outlet_identifier{where_clause}
GROUP BY o.outlet_establishment_year
ORDER BY o.outlet_establishment_year ASC;
"""

    sql_outlet_type = f"""
SELECT
    o.outlet_type,
    COUNT(DISTINCT o.outlet_identifier) AS outlet_count,
    COUNT(st.transaction_id)            AS total_items_sold,
    ROUND(SUM(st.sales), 2)             AS total_sales,
    ROUND(AVG(st.rating), 2)            AS avg_rating
FROM sales_transactions st
JOIN products p ON st.item_identifier   = p.item_identifier
JOIN outlets  o ON st.outlet_identifier = o.outlet_identifier{where_clause}
GROUP BY o.outlet_type
ORDER BY total_sales DESC;
"""

    sql_top100 = f"""
SELECT
    st.transaction_id           AS Transaction_ID,
    st.item_identifier          AS Item_ID,
    p.item_type                 AS Category,
    p.item_fat_content          AS Fat_Content,
    p.item_weight               AS Weight,
    st.outlet_identifier        AS Outlet_ID,
    o.outlet_type               AS Outlet_Type,
    o.outlet_location_type      AS City_Tier,
    o.outlet_size               AS Outlet_Size,
    o.outlet_establishment_year AS Est_Year,
    st.sales                    AS Sales_INR,
    st.rating                   AS Rating,
    st.sales_tier               AS Sales_Tier
FROM sales_transactions st
JOIN products p ON st.item_identifier   = p.item_identifier
JOIN outlets  o ON st.outlet_identifier = o.outlet_identifier{where_clause}
ORDER BY st.sales DESC, st.transaction_id ASC
LIMIT 100;
"""

    kpi = query_all(sql_kpi, params)[0]
    categories = query_all(sql_category, params)
    tier_size = query_all(sql_tier_size, params)
    trend = query_all(sql_trend, params)
    outlet_types = query_all(sql_outlet_type, params)
    top100 = query_all(sql_top100, params)

    return jsonify(
        {
            "kpi": kpi,
            "categories": categories,
            "tier_size": tier_size,
            "trend": trend,
            "outlet_types": outlet_types,
            "top100": top100,
            "total_rows": opts["total_rows"],
            "year_min": meta["year_min"],
            "year_max": meta["year_max"],
            "sql_queries": {
                "KPI Summary Query": format_sql_preview(sql_kpi, params),
                "Sales by Product Category Query": format_sql_preview(sql_category, params),
                "Sales by City Tier & Size Query": format_sql_preview(sql_tier_size, params),
                "Sales by Establishment Year Query": format_sql_preview(sql_trend, params),
                "Sales & Rating by Outlet Type Query": format_sql_preview(sql_outlet_type, params),
                "Top 100 Records Query": format_sql_preview(sql_top100, params),
            },
        }
    )


@app.route("/api/views")
def api_views():
    with get_connection() as conn:
        objects = conn.execute(
            """
            SELECT type AS Type, name AS Name
            FROM sqlite_master
            WHERE type IN ('table', 'view')
              AND name NOT LIKE 'sqlite_%'
            ORDER BY type DESC, name ASC;
            """
        ).fetchall()
        inventory = []
        for obj in objects:
            name = obj["Name"]
            cnt = conn.execute(f'SELECT COUNT(*) FROM "{name}";').fetchone()[0]
            inventory.append({"Type": obj["Type"], "Name": name, "Rows": cnt})

        views = {
            "vw_kpi_summary": [dict(r) for r in conn.execute("SELECT * FROM vw_kpi_summary;").fetchall()],
            "vw_category_sales": [dict(r) for r in conn.execute("SELECT * FROM vw_category_sales;").fetchall()],
            "vw_outlet_performance": [dict(r) for r in conn.execute("SELECT * FROM vw_outlet_performance;").fetchall()],
        }

    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""
    return jsonify({"inventory": inventory, "views": views, "schema_sql": schema_sql})


@app.route("/api/export")
def api_export():
    opts = load_options()
    where_clause, params, _ = parse_filters(opts)
    sql = f"""
SELECT
    st.transaction_id,
    st.item_identifier,
    p.item_type,
    p.item_fat_content,
    p.item_weight,
    st.outlet_identifier,
    o.outlet_type,
    o.outlet_location_type,
    o.outlet_size,
    o.outlet_establishment_year,
    o.outlet_age,
    st.item_visibility,
    st.sales,
    st.rating,
    st.sales_tier
FROM sales_transactions st
JOIN products p ON st.item_identifier   = p.item_identifier
JOIN outlets  o ON st.outlet_identifier = o.outlet_identifier{where_clause}
ORDER BY st.transaction_id ASC;
"""
    rows = query_all(sql, params)
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=blinkit_filtered_sales_report.csv"},
    )


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


# -----------------------------------------------------------------------------
# Blinkit Official Light-Theme Interactive Frontend (HTML + CSS + Plotly.js)
# -----------------------------------------------------------------------------
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Blinkit Sales Analysis Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    :root {
      --yellow: #F8CB46;
      --yellow-dark: #EBC03D;
      --green: #0C831F;
      --green-light: #2E9E3F;
      --dark: #1A1A1A;
      --muted: #5C6470;
      --bg: #F6F7F9;
      --card: #FFFFFF;
      --border: #E5E7EB;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      background: linear-gradient(180deg, #FFFDF4 0%, var(--bg) 280px, var(--bg) 100%);
      color: var(--dark);
      min-height: 100vh;
      display: flex;
    }

    /* Sidebar */
    .sidebar {
      width: 295px;
      min-width: 295px;
      background: var(--card);
      border-right: 1px solid var(--border);
      padding: 1.25rem 1.15rem 2rem;
      position: sticky;
      top: 0;
      height: 100vh;
      overflow-y: auto;
    }
    .sidebar-brand {
      background: var(--yellow);
      border-bottom: 3px solid var(--green);
      border-radius: 12px;
      padding: 0.9rem 1rem;
      text-align: center;
      margin-bottom: 1.15rem;
    }
    .sidebar-brand-logo {
      font-size: 1.7rem;
      font-weight: 800;
      letter-spacing: -0.04em;
    }
    .logo-blink { color: var(--dark); }
    .logo-it { color: var(--green); }
    .sidebar-brand-sub {
      font-size: 0.75rem;
      font-weight: 600;
      color: #374151;
      margin-top: 2px;
    }
    .sidebar h3 {
      font-size: 1rem;
      font-weight: 700;
      margin-bottom: 0.9rem;
    }
    .filter-group {
      margin-bottom: 1rem;
    }
    .filter-label {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.8rem;
      font-weight: 600;
      color: #374151;
      margin-bottom: 0.4rem;
    }
    .filter-box {
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 0.45rem 0.6rem;
      background: #FAFAFB;
      max-height: 132px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 0.3rem;
    }
    .filter-item {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.82rem;
      cursor: pointer;
      user-select: none;
    }
    .filter-item input { accent-color: var(--green); cursor: pointer; }
    .year-row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.55rem;
    }
    .year-input {
      width: 100%;
      padding: 0.45rem 0.55rem;
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 0.84rem;
      font-family: inherit;
    }
    .btn-row {
      display: flex;
      flex-direction: column;
      gap: 0.55rem;
      margin-top: 1.1rem;
      padding-top: 1rem;
      border-top: 1px solid var(--border);
    }
    .btn-green {
      background: var(--green);
      color: #FFFFFF;
      border: none;
      border-radius: 10px;
      padding: 0.7rem 1rem;
      font-weight: 700;
      font-size: 0.86rem;
      cursor: pointer;
      text-align: center;
      text-decoration: none;
      transition: background 0.15s ease;
    }
    .btn-green:hover { background: #096918; }
    .btn-outline {
      background: #FFFFFF;
      color: var(--dark);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 0.55rem 0.9rem;
      font-weight: 600;
      font-size: 0.82rem;
      cursor: pointer;
    }
    .btn-outline:hover { background: #F3F4F6; }
    .match-caption {
      font-size: 0.78rem;
      color: var(--muted);
      margin-top: 0.65rem;
      text-align: center;
    }

    /* Main Content */
    .main {
      flex: 1;
      padding: 2.6rem 2rem 3rem;
      max-width: 1420px;
      margin: 0 auto;
      width: 100%;
    }

    /* Larger Blinkit Hero Banner positioned comfortably lower */
    .blinkit-hero {
      background: linear-gradient(135deg, var(--yellow) 0%, #FAD96B 100%);
      border: 1px solid var(--yellow-dark);
      border-bottom: 5px solid var(--green);
      border-radius: 18px;
      padding: 2.2rem 2.35rem;
      margin-top: 0.8rem;
      margin-bottom: 1.8rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 1.25rem;
      box-shadow: 0 6px 20px rgba(17, 24, 39, 0.08);
    }
    .blinkit-logo {
      font-size: 2.65rem;
      font-weight: 800;
      letter-spacing: -0.04em;
      line-height: 1.1;
      display: flex;
      align-items: baseline;
      flex-wrap: wrap;
      gap: 0.65rem;
    }
    .logo-title {
      font-size: 1.85rem;
      font-weight: 700;
      color: var(--dark);
      letter-spacing: -0.02em;
    }
    .blinkit-subtitle {
      color: #374151;
      font-size: 0.98rem;
      font-weight: 500;
      margin-top: 0.55rem;
    }
    .hero-badge {
      background: #FFFFFF;
      border: 1px solid rgba(12, 131, 31, 0.24);
      border-radius: 12px;
      padding: 0.72rem 1.2rem;
      text-align: right;
      box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    .hero-badge-main { color: var(--green); font-size: 0.92rem; font-weight: 700; }
    .hero-badge-sub { color: var(--muted); font-size: 0.8rem; margin-top: 2px; }

    /* KPI Grid */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 1rem;
      margin-bottom: 1.5rem;
    }
    .kpi-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 1.2rem 1.3rem;
      box-shadow: 0 2px 10px rgba(17,24,39,0.04);
      transition: transform 0.18s ease, box-shadow 0.18s ease;
    }
    .kpi-card:hover {
      transform: translateY(-2px);
      box-shadow: 0 6px 16px rgba(12,131,31,0.1);
    }
    .kpi-green { border-top: 4px solid var(--green); }
    .kpi-yellow { border-top: 4px solid var(--yellow); }
    .kpi-label {
      font-size: 0.78rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--muted);
      margin-bottom: 0.4rem;
    }
    .kpi-value {
      font-size: 1.92rem;
      font-weight: 800;
      font-variant-numeric: tabular-nums;
      margin-bottom: 0.35rem;
    }
    .kpi-sub { font-size: 0.82rem; color: var(--muted); }
    .kpi-green-text { color: var(--green); font-weight: 600; }
    .kpi-star { color: #D97706; font-weight: 700; }

    /* Chart Grid */
    .chart-row {
      display: grid;
      grid-template-columns: 1.18fr 1fr;
      gap: 1.25rem;
      margin-bottom: 1.35rem;
    }
    .chart-row.equal { grid-template-columns: 1fr 1fr; }
    .panel {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 1.15rem 1.25rem;
      box-shadow: 0 2px 10px rgba(17,24,39,0.04);
    }
    .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 0.6rem;
      margin-bottom: 0.4rem;
    }
    .chart-title { font-size: 1.06rem; font-weight: 700; }
    .chart-desc { font-size: 0.83rem; color: var(--muted); margin-top: 2px; }
    .radio-group {
      display: flex;
      gap: 0.35rem;
      background: #F3F4F6;
      padding: 0.22rem;
      border-radius: 9px;
    }
    .radio-btn {
      border: none;
      background: transparent;
      padding: 0.32rem 0.65rem;
      border-radius: 7px;
      font-size: 0.77rem;
      font-weight: 600;
      color: var(--muted);
      cursor: pointer;
    }
    .radio-btn.active {
      background: #FFFFFF;
      color: var(--green);
      box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    }

    /* Tabs & Tables */
    .tabs {
      display: flex;
      gap: 0.5rem;
      border-bottom: 1px solid var(--border);
      margin-bottom: 1rem;
    }
    .tab-btn {
      border: none;
      background: none;
      padding: 0.65rem 1rem;
      font-weight: 600;
      font-size: 0.88rem;
      color: var(--muted);
      cursor: pointer;
      border-bottom: 3px solid transparent;
    }
    .tab-btn.active {
      color: var(--green);
      border-bottom-color: var(--green);
    }
    .tab-pane { display: none; }
    .tab-pane.active { display: block; }
    .table-wrap {
      overflow: auto;
      max-height: 390px;
      border: 1px solid var(--border);
      border-radius: 10px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.82rem;
    }
    th {
      position: sticky;
      top: 0;
      background: #F9FAFB;
      text-align: left;
      padding: 0.62rem 0.75rem;
      border-bottom: 1px solid var(--border);
      font-weight: 700;
      color: #374151;
      white-space: nowrap;
    }
    td {
      padding: 0.55rem 0.75rem;
      border-bottom: 1px solid #F1F5F9;
      white-space: nowrap;
    }
    tr:hover td { background: #FFFDF4; }
    .sql-select {
      padding: 0.5rem 0.75rem;
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 0.85rem;
      margin-bottom: 0.75rem;
      min-width: 280px;
      font-family: inherit;
    }
    pre.sql-code {
      background: #F8FAFC;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1rem 1.15rem;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.82rem;
      overflow-x: auto;
      line-height: 1.55;
      color: #1E293B;
    }
    .views-grid {
      display: grid;
      grid-template-columns: 1fr 1.45fr;
      gap: 1.15rem;
    }
    .alert-empty {
      background: #FFF8DB;
      border: 1px solid var(--yellow-dark);
      border-radius: 10px;
      padding: 0.9rem 1.1rem;
      font-size: 0.9rem;
      margin-bottom: 1rem;
      display: none;
    }

    @media (max-width: 1080px) {
      body { flex-direction: column; }
      .sidebar { width: 100%; height: auto; position: static; border-right: none; border-bottom: 1px solid var(--border); }
      .kpi-grid { grid-template-columns: repeat(2, 1fr); }
      .chart-row, .chart-row.equal, .views-grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 560px) {
      .kpi-grid { grid-template-columns: 1fr; }
      .main { padding: 1.4rem 1rem 2rem; }
      .blinkit-hero { padding: 1.5rem 1.25rem; }
      .blinkit-logo { font-size: 2rem; }
      .logo-title { font-size: 1.35rem; }
    }
  </style>
</head>
<body>
  <!-- Sidebar Filters -->
  <aside class="sidebar">
    <div class="sidebar-brand">
      <div class="sidebar-brand-logo">
        <span class="logo-blink">blink</span><span class="logo-it">it</span>
      </div>
      <div class="sidebar-brand-sub">Sales Analytics</div>
    </div>

    <h3>Filter Data</h3>

    <div class="filter-group">
      <div class="filter-label">City Tier (Outlet Location)</div>
      <div class="filter-box" id="filter-loc"></div>
    </div>

    <div class="filter-group">
      <div class="filter-label">Outlet Type</div>
      <div class="filter-box" id="filter-outlet-type"></div>
    </div>

    <div class="filter-group">
      <div class="filter-label">Product Category</div>
      <div class="filter-box" id="filter-category"></div>
    </div>

    <div class="filter-group">
      <div class="filter-label">Fat Content</div>
      <div class="filter-box" id="filter-fat"></div>
    </div>

    <div class="filter-group">
      <div class="filter-label">Outlet Establishment Year</div>
      <div class="year-row">
        <input type="number" id="year-min" class="year-input" aria-label="Min Year" />
        <input type="number" id="year-max" class="year-input" aria-label="Max Year" />
      </div>
    </div>

    <div class="btn-row">
      <a id="download-csv-btn" class="btn-green" href="/api/export">Download Filtered Report (CSV)</a>
      <button id="reset-filters-btn" class="btn-outline" type="button">Reset All Filters</button>
    </div>
    <div class="match-caption" id="match-caption">Loading records...</div>
  </aside>

  <!-- Main Dashboard -->
  <main class="main">
    <section class="blinkit-hero">
      <div>
        <div class="blinkit-logo">
          <span><span class="logo-blink">blink</span><span class="logo-it">it</span></span>
          <span class="logo-title">Sales Analysis Dashboard</span>
        </div>
        <div class="blinkit-subtitle">
          Interactive grocery sales report powered by Python, SQLite, and Plotly
        </div>
      </div>
      <div class="hero-badge">
        <div class="hero-badge-main" id="hero-summary">Loading...</div>
        <div class="hero-badge-sub" id="hero-sub">Database: blinkit.db</div>
      </div>
    </section>

    <div class="alert-empty" id="empty-alert">
      No records match the current filters. Please select at least one option in each filter or widen the year range.
    </div>

    <!-- Row 1: 4 KPI Cards -->
    <section class="kpi-grid">
      <div class="kpi-card kpi-green">
        <div class="kpi-label">Total Sales</div>
        <div class="kpi-value" id="kpi-sales">—</div>
        <div class="kpi-sub">Exact: <span class="kpi-green-text" id="kpi-sales-exact">—</span></div>
      </div>
      <div class="kpi-card kpi-yellow">
        <div class="kpi-label">Total Items Sold</div>
        <div class="kpi-value" id="kpi-items">—</div>
        <div class="kpi-sub">Across <span class="kpi-green-text" id="kpi-outlets">—</span> Blinkit outlets</div>
      </div>
      <div class="kpi-card kpi-green">
        <div class="kpi-label">Avg Sales per Item</div>
        <div class="kpi-value" id="kpi-avg-sales">—</div>
        <div class="kpi-sub">Average revenue per item</div>
      </div>
      <div class="kpi-card kpi-yellow">
        <div class="kpi-label">Average Rating</div>
        <div class="kpi-value"><span id="kpi-rating">—</span> <span style="font-size:1rem;color:#5C6470;font-weight:600;">/ 5.0</span></div>
        <div class="kpi-sub"><span class="kpi-star" id="kpi-stars">★★★★☆</span> Customer feedback</div>
      </div>
    </section>

    <!-- Row 2: Category Sales & City Tier Breakdown -->
    <section class="chart-row">
      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="chart-title">Sales by Product Category</div>
            <div class="chart-desc">Total sales for each product category, sorted from highest to lowest.</div>
          </div>
        </div>
        <div id="chart-category" style="height:455px;"></div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="chart-title">Sales by City Tier &amp; Outlet Size</div>
            <div class="chart-desc">Percentage share of total sales across city tiers and store sizes.</div>
          </div>
          <div class="radio-group" id="tier-mode-group">
            <button class="radio-btn active" data-mode="tier" type="button">By City Tier</button>
            <button class="radio-btn" data-mode="size" type="button">By Outlet Size</button>
            <button class="radio-btn" data-mode="sunburst" type="button">Sunburst</button>
          </div>
        </div>
        <div id="chart-tier" style="height:430px;"></div>
      </div>
    </section>

    <!-- Row 3: Establishment Year & Outlet Type -->
    <section class="chart-row equal">
      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="chart-title">Sales by Outlet Establishment Year</div>
            <div class="chart-desc">Total sales generated by outlets grouped by the year they opened.</div>
          </div>
        </div>
        <div id="chart-trend" style="height:385px;"></div>
      </div>

      <div class="panel">
        <div class="panel-header">
          <div>
            <div class="chart-title">Sales &amp; Rating by Outlet Type</div>
            <div class="chart-desc">Total sales and average customer rating (★) for each store format.</div>
          </div>
        </div>
        <div id="chart-outlet-type" style="height:385px;"></div>
      </div>
    </section>

    <!-- Row 4: Data Explorer & SQL Reference -->
    <section class="panel">
      <div class="chart-title">Data Explorer &amp; SQL Reference</div>
      <div class="chart-desc" style="margin-bottom:0.8rem;">Browse filtered sales records and view the SQL queries powering this dashboard.</div>

      <div class="tabs">
        <button class="tab-btn active" data-tab="tab-records" type="button">Top 100 Sales Records</button>
        <button class="tab-btn" data-tab="tab-sql" type="button">SQL Queries Used</button>
        <button class="tab-btn" data-tab="tab-views" type="button">Database Tables &amp; Views</button>
      </div>

      <div id="tab-records" class="tab-pane active">
        <div class="table-wrap" id="top100-table"></div>
      </div>

      <div id="tab-sql" class="tab-pane">
        <select id="sql-selector" class="sql-select"></select>
        <pre id="sql-preview" class="sql-code"></pre>
      </div>

      <div id="tab-views" class="tab-pane">
        <div class="views-grid">
          <div>
            <h4 style="margin-bottom:0.55rem;font-size:0.9rem;">SQLite Tables &amp; Views</h4>
            <div class="table-wrap" id="inventory-table"></div>
          </div>
          <div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.55rem;flex-wrap:wrap;gap:0.5rem;">
              <h4 style="font-size:0.9rem;">Preview SQL View</h4>
              <div class="radio-group" id="view-selector-group">
                <button class="radio-btn active" data-view="vw_kpi_summary" type="button">vw_kpi_summary</button>
                <button class="radio-btn" data-view="vw_category_sales" type="button">vw_category_sales</button>
                <button class="radio-btn" data-view="vw_outlet_performance" type="button">vw_outlet_performance</button>
              </div>
            </div>
            <div class="table-wrap" id="view-preview-table"></div>
          </div>
        </div>
        <details style="margin-top:1rem;">
          <summary style="cursor:pointer;font-weight:600;font-size:0.86rem;color:#0C831F;">View scripts/schema.sql</summary>
          <pre id="schema-code" class="sql-code" style="margin-top:0.55rem;max-height:320px;"></pre>
        </details>
      </div>
    </section>
  </main>

  <script>
    const GREEN = '#0C831F';
    const GREEN_LIGHT = '#2E9E3F';
    const YELLOW = '#F8CB46';
    const DARK = '#1A1A1A';
    const MUTED = '#5C6470';
    const GRID = '#E5E7EB';

    let OPTIONS = null;
    let LAST_DATA = null;
    let VIEWS_DATA = null;
    let TIER_MODE = 'tier';
    let ACTIVE_VIEW = 'vw_kpi_summary';

    function formatINR(val) {
      if (val >= 1000000) return `₹${(val / 1000000).toFixed(2)}M`;
      if (val >= 1000) return `₹${(val / 1000).toFixed(1)}K`;
      return `₹${Number(val).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
    }

    function renderStars(r) {
      const full = Math.round(r);
      return '★'.repeat(full) + '☆'.repeat(Math.max(0, 5 - full));
    }

    function populateCheckboxes(containerId, items, name) {
      const el = document.getElementById(containerId);
      el.innerHTML = items.map(v => `
        <label class="filter-item">
          <input type="checkbox" name="${name}" value="${v}" checked />
          <span>${v}</span>
        </label>
      `).join('');
      el.querySelectorAll('input').forEach(cb => cb.addEventListener('change', refreshDashboard));
    }

    function getSelected(name) {
      return Array.from(document.querySelectorAll(`input[name="${name}"]:checked`)).map(i => i.value);
    }

    function buildQueryString() {
      const params = new URLSearchParams();
      const locs = getSelected('loc');
      const outlets = getSelected('outlet_type');
      const cats = getSelected('category');
      const fats = getSelected('fat');
      const yMin = document.getElementById('year-min').value;
      const yMax = document.getElementById('year-max').value;

      if (!locs.length || !outlets.length || !cats.length || !fats.length) {
        return null;
      }
      locs.forEach(v => params.append('loc', v));
      outlets.forEach(v => params.append('outlet_type', v));
      cats.forEach(v => params.append('category', v));
      fats.forEach(v => params.append('fat', v));
      params.set('year_min', yMin);
      params.set('year_max', yMax);
      return params.toString();
    }

    function renderTable(containerId, rows) {
      const el = document.getElementById(containerId);
      if (!rows || !rows.length) {
        el.innerHTML = '<div style="padding:1rem;color:#5C6470;font-size:0.85rem;">No rows to display.</div>';
        return;
      }
      const cols = Object.keys(rows[0]);
      const thead = `<thead><tr>${cols.map(c => `<th>${c.replace(/_/g, ' ')}</th>`).join('')}</tr></thead>`;
      const tbody = `<tbody>${rows.map(r => `<tr>${cols.map(c => {
        let v = r[c];
        if (c === 'Sales_INR' || c === 'total_sales' || c === 'avg_sales' || c === 'avg_sales_per_item') {
          v = `₹${Number(v).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
        }
        return `<td>${v ?? ''}</td>`;
      }).join('')}</tr>`).join('')}</tbody>`;
      el.innerHTML = `<table>${thead}${tbody}</table>`;
    }

    function renderCategoryChart(categories) {
      const sorted = [...categories].sort((a, b) => a.total_sales - b.total_sales);
      const maxVal = sorted.length ? Math.max(...sorted.map(d => d.total_sales)) : 1;
      Plotly.newPlot('chart-category', [{
        type: 'bar',
        orientation: 'h',
        x: sorted.map(d => d.total_sales),
        y: sorted.map(d => d.item_type),
        text: sorted.map(d => formatINR(d.total_sales)),
        textposition: 'outside',
        textfont: { color: DARK, size: 11 },
        marker: { color: GREEN },
        customdata: sorted.map(d => [d.total_items_sold, d.avg_rating]),
        hovertemplate: '<b>%{y}</b><br>Total Sales: ₹%{x:,.2f}<br>Items Sold: %{customdata[0]:,}<br>Avg Rating: %{customdata[1]:.2f} / 5.0<extra></extra>'
      }], {
        margin: { l: 138, r: 62, t: 10, b: 40 },
        paper_bgcolor: '#FFFFFF',
        plot_bgcolor: '#FFFFFF',
        xaxis: { title: 'Total Sales (₹)', range: [0, maxVal * 1.2], gridcolor: GRID, tickprefix: '₹', tickfont: { color: MUTED, size: 11 } },
        yaxis: { tickfont: { color: DARK, size: 11 } }
      }, { responsive: true, displayModeBar: false });
    }

    function renderTierChart(tierSize) {
      const palette = {
        'Tier 1': YELLOW, 'Tier 2': GREEN_LIGHT, 'Tier 3': GREEN,
        'Small': YELLOW, 'Medium': GREEN, 'High': '#15803D'
      };
      if (TIER_MODE === 'sunburst') {
        const labels = [];
        const parents = [];
        const values = [];
        const colors = [];
        const tierTotals = {};
        tierSize.forEach(r => {
          tierTotals[r.outlet_location_type] = (tierTotals[r.outlet_location_type] || 0) + r.total_sales;
        });
        Object.entries(tierTotals).forEach(([tier, val]) => {
          labels.push(tier);
          parents.push('');
          values.push(val);
          colors.push(palette[tier] || GREEN);
        });
        tierSize.forEach(r => {
          labels.push(`${r.outlet_location_type} - ${r.outlet_size}`);
          parents.push(r.outlet_location_type);
          values.push(r.total_sales);
          colors.push(palette[r.outlet_size] || GREEN_LIGHT);
        });
        Plotly.newPlot('chart-tier', [{
          type: 'sunburst',
          labels, parents, values,
          branchvalues: 'total',
          textinfo: 'label+percent parent',
          marker: { colors, line: { color: '#FFFFFF', width: 2 } },
          hovertemplate: '<b>%{label}</b><br>Total Sales: ₹%{value:,.2f}<extra></extra>'
        }], {
          margin: { l: 8, r: 8, t: 8, b: 8 },
          paper_bgcolor: '#FFFFFF'
        }, { responsive: true, displayModeBar: false });
        return;
      }

      const key = TIER_MODE === 'tier' ? 'outlet_location_type' : 'outlet_size';
      const grouped = {};
      tierSize.forEach(r => {
        grouped[r[key]] = (grouped[r[key]] || 0) + r.total_sales;
      });
      const entries = Object.entries(grouped).sort((a, b) => b[1] - a[1]);
      const total = entries.reduce((acc, e) => acc + e[1], 0);

      Plotly.newPlot('chart-tier', [{
        type: 'pie',
        hole: 0.55,
        labels: entries.map(e => e[0]),
        values: entries.map(e => e[1]),
        marker: { colors: entries.map(e => palette[e[0]] || GREEN), line: { color: '#FFFFFF', width: 3 } },
        textinfo: 'label+percent',
        textfont: { size: 12, color: DARK },
        hovertemplate: '<b>%{label}</b><br>Total Sales: ₹%{value:,.2f}<br>Share: %{percent}<extra></extra>'
      }], {
        margin: { l: 10, r: 10, t: 12, b: 28 },
        paper_bgcolor: '#FFFFFF',
        legend: { orientation: 'h', y: -0.05, x: 0.5, xanchor: 'center' },
        annotations: [{
          text: `<b>${formatINR(total)}</b><br><span style="font-size:11px;color:${MUTED}">Total Sales</span>`,
          x: 0.5, y: 0.5, showarrow: false, font: { size: 16, color: DARK }
        }]
      }, { responsive: true, displayModeBar: false });
    }

    function renderTrendChart(trend) {
      const maxY = trend.length ? Math.max(...trend.map(d => d.total_sales)) : 1;
      Plotly.newPlot('chart-trend', [{
        type: 'scatter',
        mode: 'lines+markers+text',
        x: trend.map(d => d.outlet_establishment_year),
        y: trend.map(d => d.total_sales),
        text: trend.map(d => formatINR(d.total_sales)),
        textposition: 'top center',
        textfont: { color: DARK, size: 10 },
        line: { color: GREEN, width: 3 },
        marker: { size: 9, color: YELLOW, line: { color: GREEN, width: 2 } },
        fill: 'tozeroy',
        fillcolor: 'rgba(12, 131, 31, 0.12)',
        customdata: trend.map(d => [d.outlet_count, d.total_items_sold]),
        hovertemplate: '<b>Established in %{x}</b><br>Total Sales: ₹%{y:,.2f}<br>Outlets Opened: %{customdata[0]}<br>Items Sold: %{customdata[1]:,}<extra></extra>'
      }], {
        margin: { l: 62, r: 18, t: 24, b: 44 },
        paper_bgcolor: '#FFFFFF',
        plot_bgcolor: '#FFFFFF',
        xaxis: { title: 'Outlet Establishment Year', dtick: 1, gridcolor: GRID, tickfont: { color: MUTED, size: 11 } },
        yaxis: { title: 'Total Sales (₹)', tickprefix: '₹', range: [0, maxY * 1.24], gridcolor: GRID, tickfont: { color: MUTED, size: 11 } }
      }, { responsive: true, displayModeBar: false });
    }

    function renderOutletTypeChart(outletTypes) {
      const colors = [GREEN, GREEN_LIGHT, YELLOW, '#E5A910'];
      const maxY = outletTypes.length ? Math.max(...outletTypes.map(d => d.total_sales)) : 1;
      Plotly.newPlot('chart-outlet-type', [{
        type: 'bar',
        x: outletTypes.map(d => d.outlet_type),
        y: outletTypes.map(d => d.total_sales),
        text: outletTypes.map(d => `${formatINR(d.total_sales)}<br>★ ${Number(d.avg_rating).toFixed(2)}`),
        textposition: 'outside',
        textfont: { color: DARK, size: 11 },
        marker: { color: outletTypes.map((_, i) => colors[i % colors.length]) },
        customdata: outletTypes.map(d => [d.avg_rating, d.total_items_sold, d.outlet_count]),
        hovertemplate: '<b>%{x}</b><br>Total Sales: ₹%{y:,.2f}<br>Avg Rating: %{customdata[0]:.2f} / 5.0<br>Items Sold: %{customdata[1]:,}<br>Outlets: %{customdata[2]}<extra></extra>'
      }], {
        margin: { l: 62, r: 14, t: 26, b: 44 },
        paper_bgcolor: '#FFFFFF',
        plot_bgcolor: '#FFFFFF',
        xaxis: { title: 'Outlet Type', tickfont: { color: DARK, size: 11 } },
        yaxis: { title: 'Total Sales (₹)', tickprefix: '₹', range: [0, maxY * 1.3], gridcolor: GRID, tickfont: { color: MUTED, size: 11 } }
      }, { responsive: true, displayModeBar: false });
    }

    async function refreshDashboard() {
      const qs = buildQueryString();
      const alertEl = document.getElementById('empty-alert');
      if (qs === null) {
        alertEl.style.display = 'block';
        return;
      }

      document.getElementById('download-csv-btn').href = `/api/export?${qs}`;
      const res = await fetch(`/api/dashboard?${qs}`);
      const data = await res.json();
      LAST_DATA = data;

      if (!data.kpi || data.kpi.total_items_sold === 0) {
        alertEl.style.display = 'block';
        return;
      }
      alertEl.style.display = 'none';

      // KPIs & Hero Badge
      document.getElementById('kpi-sales').textContent = formatINR(data.kpi.total_sales);
      document.getElementById('kpi-sales-exact').textContent = `₹${Number(data.kpi.total_sales).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
      document.getElementById('kpi-items').textContent = Number(data.kpi.total_items_sold).toLocaleString('en-IN');
      document.getElementById('kpi-outlets').textContent = data.kpi.active_outlets;
      document.getElementById('kpi-avg-sales').textContent = `₹${Number(data.kpi.avg_sales_per_item).toFixed(2)}`;
      document.getElementById('kpi-rating').textContent = Number(data.kpi.avg_rating).toFixed(2);
      document.getElementById('kpi-stars').textContent = renderStars(data.kpi.avg_rating);

      document.getElementById('hero-summary').textContent = `${data.kpi.active_outlets} Outlets · ${data.categories.length} Categories`;
      document.getElementById('hero-sub').textContent = `Years: ${data.year_min} – ${data.year_max} · Database: blinkit.db`;
      document.getElementById('match-caption').textContent = `Showing ${Number(data.kpi.total_items_sold).toLocaleString('en-IN')} of ${Number(data.total_rows).toLocaleString('en-IN')} records.`;

      // Charts
      renderCategoryChart(data.categories);
      renderTierChart(data.tier_size);
      renderTrendChart(data.trend);
      renderOutletTypeChart(data.outlet_types);

      // Top 100 Table & SQL Queries
      renderTable('top100-table', data.top100);
      const sqlSel = document.getElementById('sql-selector');
      const prevKey = sqlSel.value;
      const keys = Object.keys(data.sql_queries);
      sqlSel.innerHTML = keys.map(k => `<option value="${k}">${k}</option>`).join('');
      if (prevKey && data.sql_queries[prevKey]) sqlSel.value = prevKey;
      document.getElementById('sql-preview').textContent = data.sql_queries[sqlSel.value];
    }

    async function loadViews() {
      const res = await fetch('/api/views');
      VIEWS_DATA = await res.json();
      renderTable('inventory-table', VIEWS_DATA.inventory);
      renderTable('view-preview-table', VIEWS_DATA.views[ACTIVE_VIEW]);
      document.getElementById('schema-code').textContent = VIEWS_DATA.schema_sql;
    }

    async function init() {
      const res = await fetch('/api/options');
      OPTIONS = await res.json();

      populateCheckboxes('filter-loc', OPTIONS.loc_types, 'loc');
      populateCheckboxes('filter-outlet-type', OPTIONS.outlet_types, 'outlet_type');
      populateCheckboxes('filter-category', OPTIONS.item_types, 'category');
      populateCheckboxes('filter-fat', OPTIONS.fat_contents, 'fat');

      const yMin = document.getElementById('year-min');
      const yMax = document.getElementById('year-max');
      yMin.min = OPTIONS.min_year; yMin.max = OPTIONS.max_year; yMin.value = OPTIONS.min_year;
      yMax.min = OPTIONS.min_year; yMax.max = OPTIONS.max_year; yMax.value = OPTIONS.max_year;
      yMin.addEventListener('change', refreshDashboard);
      yMax.addEventListener('change', refreshDashboard);

      document.getElementById('reset-filters-btn').addEventListener('click', () => {
        document.querySelectorAll('.sidebar input[type="checkbox"]').forEach(cb => cb.checked = true);
        yMin.value = OPTIONS.min_year;
        yMax.value = OPTIONS.max_year;
        refreshDashboard();
      });

      document.querySelectorAll('#tier-mode-group .radio-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          document.querySelectorAll('#tier-mode-group .radio-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          TIER_MODE = btn.dataset.mode;
          if (LAST_DATA) renderTierChart(LAST_DATA.tier_size);
        });
      });

      document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
          document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
          btn.classList.add('active');
          document.getElementById(btn.dataset.tab).classList.add('active');
        });
      });

      document.getElementById('sql-selector').addEventListener('change', (e) => {
        if (LAST_DATA) document.getElementById('sql-preview').textContent = LAST_DATA.sql_queries[e.target.value];
      });

      document.querySelectorAll('#view-selector-group .radio-btn').forEach(btn => {
        btn.addEventListener('click', () => {
          document.querySelectorAll('#view-selector-group .radio-btn').forEach(b => b.classList.remove('active'));
          btn.classList.add('active');
          ACTIVE_VIEW = btn.dataset.view;
          if (VIEWS_DATA) renderTable('view-preview-table', VIEWS_DATA.views[ACTIVE_VIEW]);
        });
      });

      await Promise.all([refreshDashboard(), loadViews()]);
    }

    init();
  </script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(debug=True, port=5000)
