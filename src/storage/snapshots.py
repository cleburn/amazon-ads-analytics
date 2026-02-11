"""Weekly snapshot save/retrieve operations."""

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from src.storage.database import get_connection


def save_weekly_snapshot(
    week_start: str,
    week_end: str,
    targeting_df: pd.DataFrame,
    search_term_df: pd.DataFrame,
    kdp_df: pd.DataFrame,
    campaign_summary: dict,
    bid_recommendations: dict,
    db_path: str = None,
    notes: str = None,
) -> int:
    """Save a complete weekly snapshot to SQLite.

    Returns the snapshot_id.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    try:
        # Check for existing snapshot for this week and clean it up first
        existing = cursor.execute(
            "SELECT id FROM weekly_snapshots WHERE week_start = ?",
            (week_start,),
        ).fetchone()

        if existing:
            old_id = existing[0]
            # Delete child records before replacing the snapshot
            for child_table in [
                "campaign_metrics",
                "target_metrics",
                "search_term_metrics",
                "kdp_daily_sales",
                "bid_recommendations",
            ]:
                cursor.execute(
                    f"DELETE FROM {child_table} WHERE snapshot_id = ?",
                    (old_id,),
                )
            cursor.execute(
                "DELETE FROM weekly_snapshots WHERE id = ?",
                (old_id,),
            )

        # Insert snapshot record
        cursor.execute(
            """INSERT INTO weekly_snapshots (week_start, week_end, imported_at, notes)
               VALUES (?, ?, ?, ?)""",
            (week_start, week_end, datetime.now().isoformat(), notes),
        )
        snapshot_id = cursor.lastrowid

        # Save campaign metrics
        summary_table = campaign_summary.get("table", pd.DataFrame())
        for _, row in summary_table.iterrows():
            cursor.execute(
                """INSERT OR REPLACE INTO campaign_metrics
                   (snapshot_id, campaign_name, impressions, clicks, spend,
                    sales, orders, ctr, avg_cpc, acos, roas)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot_id,
                    row["campaign_name"],
                    int(row.get("impressions", 0)),
                    int(row.get("clicks", 0)),
                    float(row.get("spend", 0)),
                    float(row.get("sales", 0)),
                    int(row.get("orders", 0)),
                    float(row.get("ctr", 0)),
                    float(row.get("avg_cpc", 0)),
                    float(row["acos"]) if pd.notna(row.get("acos")) else None,
                    float(row["roas"]) if pd.notna(row.get("roas")) else None,
                ),
            )

        # Save target metrics
        for _, row in targeting_df.iterrows():
            # Determine target type
            targeting_val = str(row.get("targeting", ""))
            is_asin = (
                len(targeting_val) == 10
                and (targeting_val[0].isdigit() or targeting_val.startswith("B0"))
            )
            target_type = "asin" if is_asin else "keyword"

            conv_rate = 0
            if row.get("clicks", 0) > 0:
                conv_rate = row.get("orders", 0) / row["clicks"]

            cursor.execute(
                """INSERT OR REPLACE INTO target_metrics
                   (snapshot_id, campaign_name, targeting, target_type, match_type,
                    bid, impressions, clicks, spend, sales, orders, ctr, cpc,
                    conversion_rate)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot_id,
                    row.get("campaign_name", ""),
                    targeting_val,
                    target_type,
                    row.get("match_type", ""),
                    float(row["bid"]) if pd.notna(row.get("bid")) else None,
                    int(row.get("impressions", 0)),
                    int(row.get("clicks", 0)),
                    float(row.get("spend", 0)),
                    float(row.get("sales", 0)),
                    int(row.get("orders", 0)),
                    float(row.get("ctr", 0)),
                    float(row.get("cpc", 0)),
                    float(conv_rate),
                ),
            )

        # Save search term metrics
        drift_targets = set()
        # We don't have drift_flags here directly, so mark all as non-drift
        # Drift detection is in the analysis layer

        for _, row in search_term_df.iterrows():
            cursor.execute(
                """INSERT INTO search_term_metrics
                   (snapshot_id, campaign_name, targeting, search_term, match_type,
                    impressions, clicks, spend, sales, orders, is_drift)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot_id,
                    row.get("campaign_name", ""),
                    row.get("targeting", ""),
                    row.get("search_term", ""),
                    row.get("match_type", ""),
                    int(row.get("impressions", 0)),
                    int(row.get("clicks", 0)),
                    float(row.get("spend", 0)),
                    float(row.get("sales", 0)),
                    int(row.get("orders", 0)),
                    0,
                ),
            )

        # Save KDP daily sales
        units_col = "net_units_sold" if "net_units_sold" in kdp_df.columns else "units_sold"
        for _, row in kdp_df.iterrows():
            date_val = row.get("date")
            if hasattr(date_val, "strftime"):
                date_val = date_val.strftime("%Y-%m-%d")

            cursor.execute(
                """INSERT OR REPLACE INTO kdp_daily_sales
                   (snapshot_id, date, title, format, units_sold, net_units_sold, royalty)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot_id,
                    str(date_val),
                    row.get("title", ""),
                    row.get("format", ""),
                    int(row.get("units_sold", 0)),
                    int(row.get(units_col, 0)),
                    float(row.get("royalty", 0)),
                ),
            )

        # Save bid recommendations
        bid_table = bid_recommendations.get("table", pd.DataFrame())
        bid_flags = bid_recommendations.get("flags", [])
        flag_lookup = {f["target"]: f.get("type", "") for f in bid_flags}

        for _, row in bid_table.iterrows():
            cursor.execute(
                """INSERT INTO bid_recommendations
                   (snapshot_id, targeting, current_bid, recommended_max_bid,
                    conversion_rate, flag)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    snapshot_id,
                    row.get("targeting", ""),
                    float(row["current_bid"]) if pd.notna(row.get("current_bid")) else None,
                    float(row["max_profitable_bid"]) if pd.notna(row.get("max_profitable_bid")) else None,
                    float(row.get("conversion_rate", 0)),
                    flag_lookup.get(row.get("targeting", ""), None),
                ),
            )

        conn.commit()
        return snapshot_id

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_prior_week_summary(
    current_week: str,
    db_path: str = None,
) -> Optional[pd.DataFrame]:
    """Retrieve the prior week's campaign summary for WoW comparison."""
    conn = get_connection(db_path)

    try:
        # Find the most recent snapshot before current_week
        row = conn.execute(
            """SELECT id FROM weekly_snapshots
               WHERE week_start < ? ORDER BY week_start DESC LIMIT 1""",
            (current_week,),
        ).fetchone()

        if not row:
            return None

        snapshot_id = row["id"]

        df = pd.read_sql_query(
            """SELECT campaign_name, impressions, clicks, spend, sales,
                      orders, ctr, avg_cpc, acos, roas
               FROM campaign_metrics WHERE snapshot_id = ?""",
            conn,
            params=(snapshot_id,),
        )

        return df if not df.empty else None

    finally:
        conn.close()


def get_trend_data(
    metric: str,
    campaign: str = None,
    weeks: int = 8,
    db_path: str = None,
) -> pd.DataFrame:
    """Retrieve trend data for a metric over time.

    Returns a DataFrame with week_start as rows and campaigns as columns.
    """
    allowed_metrics = {"spend", "impressions", "clicks", "ctr", "acos", "orders", "roas", "avg_cpc", "sales"}
    # Map CLI-friendly names to column names
    metric_map = {"orders": "orders"}
    metric = metric_map.get(metric, metric)
    if metric not in allowed_metrics:
        raise ValueError(f"Invalid metric: {metric}")

    conn = get_connection(db_path)

    try:
        query = """
            SELECT ws.week_start, cm.campaign_name, cm.{metric}
            FROM campaign_metrics cm
            JOIN weekly_snapshots ws ON cm.snapshot_id = ws.id
            {where}
            ORDER BY ws.week_start DESC
            LIMIT ?
        """

        where_clause = ""
        params = []
        if campaign:
            where_clause = "WHERE cm.campaign_name = ?"
            params.append(campaign)

        # Use the metric name directly — it matches column names
        formatted_query = query.format(metric=metric, where=where_clause)
        params.append(weeks * 3)  # multiplied because multiple campaigns per week

        df = pd.read_sql_query(formatted_query, conn, params=params)

        if df.empty:
            return pd.DataFrame()

        # Pivot: weeks as rows, campaigns as columns
        pivoted = df.pivot_table(
            index="week_start",
            columns="campaign_name",
            values=metric,
            aggfunc="first",
        ).reset_index()

        return pivoted.sort_values("week_start")

    finally:
        conn.close()


def get_lifetime_summary(db_path: str = None) -> Optional[dict]:
    """Get lifetime aggregate metrics across all snapshots."""
    conn = get_connection(db_path)

    try:
        row = conn.execute(
            """SELECT
                COUNT(DISTINCT ws.id) as weeks_tracked,
                SUM(cm.spend) as total_spend,
                SUM(cm.orders) as total_orders,
                SUM(cm.sales) as total_sales
               FROM campaign_metrics cm
               JOIN weekly_snapshots ws ON cm.snapshot_id = ws.id"""
        ).fetchone()

        if not row or row["weeks_tracked"] == 0:
            return None

        total_spend = row["total_spend"] or 0
        total_sales = row["total_sales"] or 0
        total_orders = row["total_orders"] or 0
        weeks = row["weeks_tracked"]

        return {
            "weeks_tracked": weeks,
            "total_spend": total_spend,
            "total_orders": total_orders,
            "total_sales": total_sales,
            "overall_acos": total_spend / total_sales if total_sales > 0 else 0,
            "overall_roas": total_sales / total_spend if total_spend > 0 else 0,
            "avg_weekly_spend": total_spend / weeks if weeks > 0 else 0,
        }

    finally:
        conn.close()
