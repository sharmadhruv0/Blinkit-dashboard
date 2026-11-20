"""
Blinkit Sales Analysis Dashboard — Interactive Web Application
==============================================================
Reads cleaned, normalized sales data from SQLite (data/processed/blinkit.db)
and displays key metrics, simple charts, filtered data export, and SQL queries.

Run locally:
    streamlit run app_streamlit/app.py
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# -----------------------------------------------------------------------------
# Paths & Official Blinkit Brand Colors
# -----------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "processed" / "blinkit.db"
SCHEMA_PATH = PROJECT_ROOT / "scripts" / "schema.sql"

BLINKIT_YELLOW = "#F8CB46"      # Official Blinkit Yellow
BLINKIT_YELLOW_SOFT = "#FFF8DB" # Soft warm yellow tint
BLINKIT_GREEN = "#0C831F"       # Official Blinkit Green
BLINKIT_GREEN_LIGHT = "#2E9E3F" # Fresh mid green
BLINKIT_GREEN_MINT = "#86D293"  # Soft leaf green
BLINKIT_DARK = "#1A1A1A"        # Crisp Blinkit black/charcoal text
TEXT_MUTED = "#5C6470"          # Clean secondary gray text
PAGE_BG = "#F6F7F9"             # Clean light Blinkit storefront background
CARD_BG = "#FFFFFF"             # Pure white cards
CARD_BORDER = "#E5E7EB"         # Subtle neutral border
GRID_COLOR = "#E5E7EB"

# -----------------------------------------------------------------------------
# Page Configuration
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Blinkit Sales Analysis Dashboard",
    page_icon="🛒",
    layout="wide",
    initial_sidebar_state="expanded",
)


# -----------------------------------------------------------------------------
# Clean Blinkit Theme CSS
# -----------------------------------------------------------------------------
def inject_custom_css() -> None:
    st.markdown(
        f"""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

            html, body, [class*="css"] {{
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                color: {BLINKIT_DARK};
            }}

            /* Main Page & Sidebar Backgrounds */
            [data-testid="stAppViewContainer"] {{
                background: linear-gradient(180deg, #FFFDF4 0%, {PAGE_BG} 260px, {PAGE_BG} 100%);
                color: {BLINKIT_DARK};
            }}
            [data-testid="stHeader"] {{
                background: rgba(255, 253, 244, 0.9);
                backdrop-filter: blur(8px);
            }}
            [data-testid="stSidebar"] {{
                background-color: {CARD_BG};
                border-right: 1px solid {CARD_BORDER};
            }}
            [data-testid="stSidebar"] * {{
                color: {BLINKIT_DARK};
            }}

            /* Give comfortable breathing room at top so the Blinkit header sits lower */
            .block-container {{
                padding-top: 3.1rem;
                padding-bottom: 2.5rem;
                max-width: 1420px;
            }}

            /* Larger, Prominent Blinkit Header Banner (moved slightly down) */
            .blinkit-hero {{
                background: linear-gradient(135deg, {BLINKIT_YELLOW} 0%, #FAD96B 100%);
                border: 1px solid #EBC03D;
                border-bottom: 5px solid {BLINKIT_GREEN};
                border-radius: 18px;
                padding: 2.15rem 2.3rem;
                margin-top: 0.9rem;
                margin-bottom: 1.8rem;
                display: flex;
                justify-content: space-between;
                align-items: center;
                flex-wrap: wrap;
                gap: 1.25rem;
                box-shadow: 0 6px 20px rgba(17, 24, 39, 0.08);
            }}
            .blinkit-logo {{
                font-size: 2.6rem;
                font-weight: 800;
                letter-spacing: -0.04em;
                line-height: 1.1;
                display: flex;
                align-items: baseline;
                flex-wrap: wrap;
                gap: 0.65rem;
            }}
            .logo-blink {{
                color: {BLINKIT_DARK};
            }}
            .logo-it {{
                color: {BLINKIT_GREEN};
            }}
            .logo-title {{
                font-size: 1.85rem;
                font-weight: 700;
                color: {BLINKIT_DARK};
                letter-spacing: -0.02em;
            }}
            .blinkit-subtitle {{
                color: #374151;
                font-size: 0.98rem;
                font-weight: 500;
                margin-top: 0.5rem;
            }}
            .hero-badge {{
                background: {CARD_BG};
                border: 1px solid rgba(12, 131, 31, 0.25);
                border-radius: 12px;
                padding: 0.7rem 1.15rem;
                text-align: right;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
            }}
            .hero-badge-main {{
                color: {BLINKIT_GREEN};
                font-size: 0.92rem;
                font-weight: 700;
            }}
            .hero-badge-sub {{
                color: {TEXT_MUTED};
                font-size: 0.8rem;
                margin-top: 0.15rem;
            }}

            /* Simple, Crisp KPI Cards */
            .kpi-card {{
                background: {CARD_BG};
                border: 1px solid {CARD_BORDER};
                border-radius: 14px;
                padding: 1.2rem 1.3rem;
                box-shadow: 0 2px 10px rgba(17, 24, 39, 0.04);
                transition: transform 0.18s ease, box-shadow 0.18s ease;
            }}
            .kpi-card:hover {{
                transform: translateY(-2px);
                box-shadow: 0 6px 16px rgba(12, 131, 31, 0.1);
            }}
            .kpi-green  {{ border-top: 4px solid {BLINKIT_GREEN}; }}
            .kpi-yellow {{ border-top: 4px solid {BLINKIT_YELLOW}; }}

            .kpi-label {{
                font-size: 0.8rem;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                color: {TEXT_MUTED};
                margin-bottom: 0.4rem;
            }}
            .kpi-value {{
                font-size: 1.95rem;
                font-weight: 800;
                color: {BLINKIT_DARK};
                font-variant-numeric: tabular-nums;
                line-height: 1.15;
                margin-bottom: 0.35rem;
            }}
            .kpi-sub {{
                font-size: 0.82rem;
                color: {TEXT_MUTED};
            }}
            .kpi-green-text {{
                color: {BLINKIT_GREEN};
                font-weight: 600;
            }}
            .kpi-star {{
                color: #D97706;
                font-weight: 700;
            }}

            /* Section Headings */
            .chart-title {{
                font-size: 1.08rem;
                font-weight: 700;
                color: {BLINKIT_DARK};
                margin: 0.25rem 0 0.1rem 0;
            }}
            .chart-desc {{
                font-size: 0.84rem;
                color: {TEXT_MUTED};
                margin-bottom: 0.45rem;
            }}
            .section-divider {{
                height: 1px;
                background: {CARD_BORDER};
                margin: 1.25rem 0 1.1rem 0;
            }}

            /* Sidebar Brand Card */
            .sidebar-brand {{
                background: {BLINKIT_YELLOW};
                border-bottom: 3px solid {BLINKIT_GREEN};
                border-radius: 12px;
                padding: 0.9rem 1rem;
                margin-bottom: 1.1rem;
                text-align: center;
            }}
            .sidebar-brand-logo {{
                font-size: 1.65rem;
                font-weight: 800;
                letter-spacing: -0.04em;
            }}
            .sidebar-brand-sub {{
                font-size: 0.75rem;
                font-weight: 600;
                color: #374151;
                margin-top: 0.1rem;
            }}

            /* Multiselect Tags & Download Button */
            span[data-baseweb="tag"] {{
                background-color: #E7F5EA !important;
                border: 1px solid rgba(12, 131, 31, 0.35) !important;
                color: {BLINKIT_GREEN} !important;
            }}
            [data-testid="stDownloadButton"] button {{
                background-color: {BLINKIT_GREEN} !important;
                color: #FFFFFF !important;
                border: none !important;
                font-weight: 700 !important;
                border-radius: 10px !important;
                width: 100%;
                padding: 0.65rem 1rem !important;
            }}
            [data-testid="stDownloadButton"] button:hover {{
                background-color: #096918 !important;
                color: #FFFFFF !important;
            }}

            /* Tabs */
            button[data-baseweb="tab"] {{
                color: {TEXT_MUTED} !important;
                font-weight: 600 !important;
            }}
            button[data-baseweb="tab"][aria-selected="true"] {{
                color: {BLINKIT_GREEN} !important;
                border-bottom-color: {BLINKIT_GREEN} !important;
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# -----------------------------------------------------------------------------
# Database Access Layer (SQLite Parameterized Queries)
# -----------------------------------------------------------------------------
@st.cache_data(ttl=300)
def run_sql_query(query: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    """Execute a parameterized SELECT query against blinkit.db."""
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(query, conn, params=params)


@st.cache_data(ttl=300)
def load_filter_options() -> dict[str, Any]:
    """Load distinct filter values from the SQLite dimension tables."""
    with sqlite3.connect(DB_PATH) as conn:
        loc_types = pd.read_sql_query(
            "SELECT DISTINCT outlet_location_type FROM outlets ORDER BY outlet_location_type;",
            conn,
        )["outlet_location_type"].tolist()

        outlet_types = pd.read_sql_query(
            "SELECT DISTINCT outlet_type FROM outlets ORDER BY outlet_type;",
            conn,
        )["outlet_type"].tolist()

        item_types = pd.read_sql_query(
            "SELECT DISTINCT item_type FROM products ORDER BY item_type;",
            conn,
        )["item_type"].tolist()

        fat_contents = pd.read_sql_query(
            "SELECT DISTINCT item_fat_content FROM products ORDER BY item_fat_content;",
            conn,
        )["item_fat_content"].tolist()

        yr_bounds = pd.read_sql_query(
            """
            SELECT
                MIN(outlet_establishment_year) AS min_year,
                MAX(outlet_establishment_year) AS max_year
            FROM outlets;
            """,
            conn,
        ).iloc[0]

        total_rows = int(
            pd.read_sql_query(
                "SELECT COUNT(*) AS cnt FROM sales_transactions;", conn
            ).iloc[0]["cnt"]
        )

    return {
        "loc_types": loc_types,
        "outlet_types": outlet_types,
        "item_types": item_types,
        "fat_contents": fat_contents,
        "min_year": int(yr_bounds["min_year"]),
        "max_year": int(yr_bounds["max_year"]),
        "total_rows": total_rows,
    }


def build_where_clause(
    loc_types: list[str],
    outlet_types: list[str],
    item_types: list[str],
    fat_contents: list[str],
    year_range: tuple[int, int],
    opts: dict[str, Any],
) -> tuple[str, tuple[Any, ...]]:
    """
    Build a clean parameterized WHERE clause.
    Only adds filters that differ from 'All Selected', keeping the generated
    SQL concise and easy to read in the SQL Inspector tab.
    """
    conditions: list[str] = []
    params: list[Any] = []

    if int(year_range[0]) > opts["min_year"] or int(year_range[1]) < opts["max_year"]:
        conditions.append("o.outlet_establishment_year BETWEEN ? AND ?")
        params.extend([int(year_range[0]), int(year_range[1])])

    def _add_if_filtered(column: str, selected: list[str], all_values: list[str]) -> None:
        if set(selected) != set(all_values):
            placeholders = ", ".join(["?"] * len(selected))
            conditions.append(f"{column} IN ({placeholders})")
            params.extend(selected)

    _add_if_filtered("o.outlet_location_type", loc_types, opts["loc_types"])
    _add_if_filtered("o.outlet_type", outlet_types, opts["outlet_types"])
    _add_if_filtered("p.item_type", item_types, opts["item_types"])
    _add_if_filtered("p.item_fat_content", fat_contents, opts["fat_contents"])

    if not conditions:
        return "", ()
    return "\nWHERE " + "\n  AND ".join(conditions), tuple(params)


def format_sql_preview(query: str, params: tuple[Any, ...]) -> str:
    """Format a parameterized SQL query cleanly for display in the SQL tab."""
    formatted = "\n".join(line.rstrip() for line in query.strip().splitlines())
    for p in params:
        val = f"'{p}'" if isinstance(p, str) else str(p)
        formatted = formatted.replace("?", val, 1)
    return formatted


# -----------------------------------------------------------------------------
# Formatting Helpers
# -----------------------------------------------------------------------------
def format_inr(value: float) -> str:
    if value >= 1_000_000:
        return f"₹{value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"₹{value / 1_000:.1f}K"
    return f"₹{value:,.0f}"


def render_stars(rating: float) -> str:
    full = int(round(rating))
    return "★" * full + "☆" * max(0, 5 - full)


# -----------------------------------------------------------------------------
# Simple, Presentation-Friendly Plotly Chart Builders
# -----------------------------------------------------------------------------
def build_category_bar_chart(df: pd.DataFrame) -> go.Figure:
    plot_df = df.sort_values("total_sales", ascending=True).copy()
    plot_df["label"] = plot_df["total_sales"].apply(format_inr)

    fig = go.Figure(
        go.Bar(
            x=plot_df["total_sales"],
            y=plot_df["item_type"],
            orientation="h",
            text=plot_df["label"],
            textposition="outside",
            textfont=dict(color=BLINKIT_DARK, size=11),
            marker=dict(
                color=BLINKIT_GREEN,
                line=dict(color="#096918", width=0.5),
                cornerradius=5,
            ),
            customdata=plot_df[["total_items_sold", "avg_rating"]].values,
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Total Sales: ₹%{x:,.2f}<br>"
                "Items Sold: %{customdata[0]:,}<br>"
                "Avg Rating: %{customdata[1]:.2f} / 5.0"
                "<extra></extra>"
            ),
        )
    )

    max_val = float(plot_df["total_sales"].max()) if not plot_df.empty else 1.0
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor=CARD_BG,
        plot_bgcolor=CARD_BG,
        height=460,
        margin=dict(l=12, r=65, t=14, b=36),
        xaxis=dict(
            title="Total Sales (₹)",
            range=[0, max_val * 1.18],
            gridcolor=GRID_COLOR,
            tickprefix="₹",
            tickfont=dict(color=TEXT_MUTED, size=11),
            title_font=dict(color=TEXT_MUTED, size=12),
        ),
        yaxis=dict(
            title="",
            tickfont=dict(color=BLINKIT_DARK, size=11),
        ),
    )
    return fig


def build_tier_size_chart(df: pd.DataFrame, view_mode: str = "By City Tier") -> go.Figure:
    palette = {
        "Tier 1": BLINKIT_YELLOW,
        "Tier 2": BLINKIT_GREEN_LIGHT,
        "Tier 3": BLINKIT_GREEN,
        "Small": BLINKIT_YELLOW,
        "Medium": BLINKIT_GREEN,
        "High": "#15803D",
    }

    if view_mode == "Tier & Size (Sunburst)":
        fig = px.sunburst(
            df,
            path=["outlet_location_type", "outlet_size"],
            values="total_sales",
            color="outlet_location_type",
            color_discrete_map=palette,
        )
        fig.update_traces(
            textinfo="label+percent parent",
            marker=dict(line=dict(color="#FFFFFF", width=2)),
            hovertemplate="<b>%{label}</b><br>Total Sales: ₹%{value:,.2f}<br>Share: %{percentRoot:.1%}<extra></extra>",
        )
    else:
        group_col = "outlet_location_type" if view_mode == "By City Tier" else "outlet_size"
        agg = (
            df.groupby(group_col, as_index=False)
            .agg(total_sales=("total_sales", "sum"), total_items_sold=("total_items_sold", "sum"))
            .sort_values("total_sales", ascending=False)
        )
        fig = go.Figure(
            go.Pie(
                labels=agg[group_col],
                values=agg["total_sales"],
                hole=0.55,
                marker=dict(
                    colors=[palette.get(val, BLINKIT_GREEN) for val in agg[group_col]],
                    line=dict(color="#FFFFFF", width=3),
                ),
                textinfo="label+percent",
                textfont=dict(size=12, color=BLINKIT_DARK),
                hovertemplate=(
                    "<b>%{label}</b><br>"
                    "Total Sales: ₹%{value:,.2f}<br>"
                    "Share: %{percent}"
                    "<extra></extra>"
                ),
            )
        )
        total_rev = float(agg["total_sales"].sum())
        fig.add_annotation(
            text=f"<b>{format_inr(total_rev)}</b><br><span style='font-size:11px;color:{TEXT_MUTED}'>Total Sales</span>",
            x=0.5,
            y=0.5,
            font=dict(size=17, color=BLINKIT_DARK),
            showarrow=False,
        )

    fig.update_layout(
        template="plotly_white",
        paper_bgcolor=CARD_BG,
        plot_bgcolor=CARD_BG,
        height=425,
        margin=dict(l=12, r=12, t=14, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=-0.06, xanchor="center", x=0.5),
    )
    return fig


def build_establishment_trend_chart(df: pd.DataFrame) -> go.Figure:
    """
    Simple single-axis Area/Line chart showing Total Sales by Outlet Establishment Year.
    Easy to read and explain in a presentation without confusing dual axes.
    """
    plot_df = df.sort_values("outlet_establishment_year").copy()
    plot_df["label"] = plot_df["total_sales"].apply(format_inr)

    fig = go.Figure(
        go.Scatter(
            x=plot_df["outlet_establishment_year"],
            y=plot_df["total_sales"],
            mode="lines+markers+text",
            text=plot_df["label"],
            textposition="top center",
            textfont=dict(color=BLINKIT_DARK, size=10),
            line=dict(color=BLINKIT_GREEN, width=3),
            marker=dict(size=9, color=BLINKIT_YELLOW, line=dict(color=BLINKIT_GREEN, width=2)),
            fill="tozeroy",
            fillcolor="rgba(12, 131, 31, 0.12)",
            customdata=plot_df[["outlet_count", "total_items_sold"]].values,
            hovertemplate=(
                "<b>Established in %{x}</b><br>"
                "Total Sales: ₹%{y:,.2f}<br>"
                "Outlets Opened: %{customdata[0]}<br>"
                "Items Sold: %{customdata[1]:,}"
                "<extra></extra>"
            ),
        )
    )

    max_y = float(plot_df["total_sales"].max()) if not plot_df.empty else 1.0
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor=CARD_BG,
        plot_bgcolor=CARD_BG,
        height=390,
        margin=dict(l=14, r=18, t=24, b=40),
        xaxis=dict(
            title="Outlet Establishment Year",
            dtick=1,
            gridcolor=GRID_COLOR,
            tickfont=dict(color=TEXT_MUTED, size=11),
            title_font=dict(color=TEXT_MUTED, size=12),
        ),
        yaxis=dict(
            title="Total Sales (₹)",
            tickprefix="₹",
            range=[0, max_y * 1.22],
            gridcolor=GRID_COLOR,
            tickfont=dict(color=TEXT_MUTED, size=11),
            title_font=dict(color=TEXT_MUTED, size=12),
        ),
    )
    return fig


def build_outlet_type_chart(df: pd.DataFrame) -> go.Figure:
    """
    Clean bar chart of Total Sales by Outlet Type with Average Rating displayed
    directly above each bar so both metrics are easy to compare at a glance.
    """
    plot_df = df.sort_values("total_sales", ascending=False).copy()
    plot_df["bar_label"] = plot_df.apply(
        lambda r: f"{format_inr(r['total_sales'])}<br>★ {r['avg_rating']:.2f}", axis=1
    )

    bar_colors = [BLINKIT_GREEN, BLINKIT_GREEN_LIGHT, BLINKIT_YELLOW, "#E5A910"]
    colors = [bar_colors[i % len(bar_colors)] for i in range(len(plot_df))]

    fig = go.Figure(
        go.Bar(
            x=plot_df["outlet_type"],
            y=plot_df["total_sales"],
            text=plot_df["bar_label"],
            textposition="outside",
            textfont=dict(color=BLINKIT_DARK, size=11),
            marker=dict(
                color=colors,
                line=dict(color="rgba(0,0,0,0.08)", width=1),
                cornerradius=6,
            ),
            customdata=plot_df[["avg_rating", "total_items_sold", "outlet_count"]].values,
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Total Sales: ₹%{y:,.2f}<br>"
                "Avg Customer Rating: %{customdata[0]:.2f} / 5.0<br>"
                "Items Sold: %{customdata[1]:,}<br>"
                "Outlets: %{customdata[2]}"
                "<extra></extra>"
            ),
        )
    )

    max_y = float(plot_df["total_sales"].max()) if not plot_df.empty else 1.0
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor=CARD_BG,
        plot_bgcolor=CARD_BG,
        height=390,
        margin=dict(l=14, r=14, t=24, b=40),
        xaxis=dict(
            title="Outlet Type",
            tickfont=dict(color=BLINKIT_DARK, size=11),
            title_font=dict(color=TEXT_MUTED, size=12),
        ),
        yaxis=dict(
            title="Total Sales (₹)",
            tickprefix="₹",
            range=[0, max_y * 1.28],
            gridcolor=GRID_COLOR,
            tickfont=dict(color=TEXT_MUTED, size=11),
            title_font=dict(color=TEXT_MUTED, size=12),
        ),
    )
    return fig


# -----------------------------------------------------------------------------
# Main Dashboard Application
# -----------------------------------------------------------------------------
def main() -> None:
    inject_custom_css()

    if not DB_PATH.exists():
        st.error(
            f"SQLite database not found at `{DB_PATH}`.\n\n"
            "Run the ETL script first:\n"
            "`python scripts/etl_pipeline.py`"
        )
        st.stop()

    opts = load_filter_options()

    # -------------------------------------------------------------------------
    # Sidebar Filters & Export
    # -------------------------------------------------------------------------
    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-brand">
                <div class="sidebar-brand-logo">
                    <span class="logo-blink">blink</span><span class="logo-it">it</span>
                </div>
                <div class="sidebar-brand-sub">Sales Analytics</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("### Filter Data")

        selected_loc = st.multiselect(
            "City Tier (Outlet Location)",
            options=opts["loc_types"],
            default=opts["loc_types"],
        )

        selected_outlet_types = st.multiselect(
            "Outlet Type",
            options=opts["outlet_types"],
            default=opts["outlet_types"],
        )

        selected_categories = st.multiselect(
            "Product Category",
            options=opts["item_types"],
            default=opts["item_types"],
        )

        selected_fat = st.multiselect(
            "Fat Content",
            options=opts["fat_contents"],
            default=opts["fat_contents"],
        )

        selected_years = st.slider(
            "Outlet Establishment Year",
            min_value=opts["min_year"],
            max_value=opts["max_year"],
            value=(opts["min_year"], opts["max_year"]),
            step=1,
        )

        st.markdown("---")
        export_placeholder = st.empty()
        sidebar_meta = st.empty()

    if not (selected_loc and selected_outlet_types and selected_categories and selected_fat):
        st.warning("Please select at least one option in each sidebar filter to view the charts.")
        st.stop()

    where_clause, where_params = build_where_clause(
        selected_loc,
        selected_outlet_types,
        selected_categories,
        selected_fat,
        selected_years,
        opts,
    )

    # -------------------------------------------------------------------------
    # SQL Queries Against Normalized SQLite Tables
    # -------------------------------------------------------------------------
    sql_kpi = f"""
SELECT
    COALESCE(ROUND(SUM(st.sales), 2), 0) AS total_sales,
    COUNT(st.transaction_id)             AS total_items_sold,
    COALESCE(ROUND(AVG(st.sales), 2), 0) AS avg_sales_per_item,
    COALESCE(ROUND(AVG(st.rating), 2), 0) AS avg_rating,
    COUNT(DISTINCT st.outlet_identifier) AS active_outlets
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

    sql_explorer = f"""
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

    sql_export = f"""
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

    kpi = run_sql_query(sql_kpi, where_params).iloc[0]

    if int(kpi["total_items_sold"]) == 0:
        st.warning("No records match the selected filters. Try widening the Establishment Year range.")
        st.stop()

    cat_df = run_sql_query(sql_category, where_params)
    tier_size_df = run_sql_query(sql_tier_size, where_params)
    trend_df = run_sql_query(sql_trend, where_params)
    outlet_type_df = run_sql_query(sql_outlet_type, where_params)
    top100_df = run_sql_query(sql_explorer, where_params)
    export_df = run_sql_query(sql_export, where_params)

    # Sidebar Download Button & Record Count
    export_placeholder.download_button(
        label="Download Filtered Report (CSV)",
        data=export_df.to_csv(index=False).encode("utf-8"),
        file_name="blinkit_filtered_sales_report.csv",
        mime="text/csv",
    )
    sidebar_meta.caption(
        f"Showing **{int(kpi['total_items_sold']):,}** of **{opts['total_rows']:,}** records."
    )

    # -------------------------------------------------------------------------
    # Prominent Blinkit Header Banner
    # -------------------------------------------------------------------------
    st.markdown(
        f"""
        <div class="blinkit-hero">
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
                <div class="hero-badge-main">{int(kpi['active_outlets'])} Outlets &middot; {len(cat_df)} Categories</div>
                <div class="hero-badge-sub">Years: {selected_years[0]} – {selected_years[1]} &middot; Database: blinkit.db</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -------------------------------------------------------------------------
    # Row 1 — Top 4 KPI Cards
    # -------------------------------------------------------------------------
    k1, k2, k3, k4 = st.columns(4, gap="medium")

    with k1:
        st.markdown(
            f"""
            <div class="kpi-card kpi-green">
                <div class="kpi-label">Total Sales</div>
                <div class="kpi-value">{format_inr(float(kpi['total_sales']))}</div>
                <div class="kpi-sub">Exact: <span class="kpi-green-text">₹{float(kpi['total_sales']):,.2f}</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with k2:
        st.markdown(
            f"""
            <div class="kpi-card kpi-yellow">
                <div class="kpi-label">Total Items Sold</div>
                <div class="kpi-value">{int(kpi['total_items_sold']):,}</div>
                <div class="kpi-sub">Across <span class="kpi-green-text">{int(kpi['active_outlets'])}</span> Blinkit outlets</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with k3:
        st.markdown(
            f"""
            <div class="kpi-card kpi-green">
                <div class="kpi-label">Avg Sales per Item</div>
                <div class="kpi-value">₹{float(kpi['avg_sales_per_item']):,.2f}</div>
                <div class="kpi-sub">Average revenue per item</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with k4:
        avg_r = float(kpi["avg_rating"])
        st.markdown(
            f"""
            <div class="kpi-card kpi-yellow">
                <div class="kpi-label">Average Rating</div>
                <div class="kpi-value">{avg_r:.2f} <span style="font-size:1rem;color:{TEXT_MUTED};font-weight:600;">/ 5.0</span></div>
                <div class="kpi-sub"><span class="kpi-star">{render_stars(avg_r)}</span> Customer feedback</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # Row 2 — Core Sales Charts (2 Columns)
    # -------------------------------------------------------------------------
    r2_col1, r2_col2 = st.columns([1.2, 1.0], gap="large")

    with r2_col1:
        st.markdown(
            '<div class="chart-title">Sales by Product Category</div>'
            '<div class="chart-desc">Total sales for each product category, sorted from highest to lowest.</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(build_category_bar_chart(cat_df), width="stretch")

    with r2_col2:
        st.markdown(
            '<div class="chart-title">Sales by City Tier &amp; Outlet Size</div>'
            '<div class="chart-desc">Percentage share of total sales across city tiers and store sizes.</div>',
            unsafe_allow_html=True,
        )
        tier_view = st.radio(
            "Breakdown View",
            options=["By City Tier", "By Outlet Size", "Tier & Size (Sunburst)"],
            horizontal=True,
            label_visibility="collapsed",
        )
        st.plotly_chart(build_tier_size_chart(tier_size_df, view_mode=tier_view), width="stretch")

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # Row 3 — Simple Trend & Outlet Type Comparison (2 Columns)
    # -------------------------------------------------------------------------
    r3_col1, r3_col2 = st.columns(2, gap="large")

    with r3_col1:
        st.markdown(
            '<div class="chart-title">Sales by Outlet Establishment Year</div>'
            '<div class="chart-desc">Total sales generated by outlets grouped by the year they opened.</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(build_establishment_trend_chart(trend_df), width="stretch")

    with r3_col2:
        st.markdown(
            '<div class="chart-title">Sales &amp; Rating by Outlet Type</div>'
            '<div class="chart-desc">Total sales and average customer rating (★) for each store format.</div>',
            unsafe_allow_html=True,
        )
        st.plotly_chart(build_outlet_type_chart(outlet_type_df), width="stretch")

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)

    # -------------------------------------------------------------------------
    # Row 4 — Data Explorer & SQL Queries Tab
    # -------------------------------------------------------------------------
    st.markdown(
        '<div class="chart-title">Data Explorer &amp; SQL Reference</div>'
        '<div class="chart-desc">Browse filtered sales records and view the SQL queries powering this dashboard.</div>',
        unsafe_allow_html=True,
    )

    tab_data, tab_sql, tab_views = st.tabs(
        [
            "Top 100 Sales Records",
            "SQL Queries Used",
            "Database Tables & Views",
        ]
    )

    with tab_data:
        st.dataframe(
            top100_df,
            width="stretch",
            height=400,
            hide_index=True,
            column_config={
                "Transaction_ID": st.column_config.NumberColumn("Txn ID", format="%d"),
                "Weight": st.column_config.NumberColumn("Weight (kg)", format="%.2f"),
                "Sales_INR": st.column_config.NumberColumn("Sales (₹)", format="₹%.2f"),
                "Rating": st.column_config.NumberColumn("Rating", format="%.1f ★"),
                "Est_Year": st.column_config.NumberColumn("Est. Year", format="%d"),
            },
        )

    with tab_sql:
        sql_choice = st.selectbox(
            "Choose a query to view",
            options=[
                "KPI Summary Query",
                "Sales by Product Category Query",
                "Sales by City Tier & Size Query",
                "Sales by Establishment Year Query",
                "Sales & Rating by Outlet Type Query",
                "Top 100 Records Query",
            ],
        )
        query_map = {
            "KPI Summary Query": sql_kpi,
            "Sales by Product Category Query": sql_category,
            "Sales by City Tier & Size Query": sql_tier_size,
            "Sales by Establishment Year Query": sql_trend,
            "Sales & Rating by Outlet Type Query": sql_outlet_type,
            "Top 100 Records Query": sql_explorer,
        }
        st.code(format_sql_preview(query_map[sql_choice], where_params), language="sql")

    with tab_views:
        v_col1, v_col2 = st.columns([1.0, 1.35], gap="large")

        with v_col1:
            st.markdown("##### SQLite Tables & Views")
            schema_inventory = run_sql_query(
                """
                SELECT
                    type AS Type,
                    name AS Name
                FROM sqlite_master
                WHERE type IN ('table', 'view')
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY type DESC, name ASC;
                """
            )
            row_counts = []
            with sqlite3.connect(DB_PATH) as conn:
                for obj_name in schema_inventory["Name"]:
                    cnt = conn.execute(f'SELECT COUNT(*) FROM "{obj_name}";').fetchone()[0]
                    row_counts.append(cnt)
            schema_inventory["Rows"] = row_counts
            st.dataframe(schema_inventory, width="stretch", hide_index=True)

        with v_col2:
            view_selector = st.radio(
                "Preview SQL View",
                options=["vw_kpi_summary", "vw_category_sales", "vw_outlet_performance"],
                horizontal=True,
            )
            st.dataframe(
                run_sql_query(f"SELECT * FROM {view_selector};"),
                width="stretch",
                height=240,
                hide_index=True,
            )

            if SCHEMA_PATH.exists():
                with st.expander("View scripts/schema.sql"):
                    st.code(SCHEMA_PATH.read_text(encoding="utf-8"), language="sql")


if __name__ == "__main__":
    main()
