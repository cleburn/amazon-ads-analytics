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
    drift_flags: list = None,
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
        # Build drift lookup from analysis-layer drift flags
        drift_keys = set()
        for flag in (drift_flags or []):
            drift_keys.add((
                flag.get("campaign", ""),
                flag.get("targeting", ""),
                flag.get("search_term", ""),
            ))

        for _, row in search_term_df.iterrows():
            campaign = row.get("campaign_name", "")
            targeting = row.get("targeting", "")
            search_term = row.get("search_term", "")
            is_drift = 1 if (campaign, targeting, search_term) in drift_keys else 0

            cursor.execute(
                """INSERT INTO search_term_metrics
                   (snapshot_id, campaign_name, targeting, search_term, match_type,
                    impressions, clicks, spend, sales, orders, is_drift)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot_id,
                    campaign,
                    targeting,
                    search_term,
                    row.get("match_type", ""),
                    int(row.get("impressions", 0)),
                    int(row.get("clicks", 0)),
                    float(row.get("spend", 0)),
                    float(row.get("sales", 0)),
                    int(row.get("orders", 0)),
                    is_drift,
                ),
            )

        # Save KDP daily sales — only rows within the snapshot's date window
        units_col = "net_units_sold" if "net_units_sold" in kdp_df.columns else "units_sold"
        kdp_filtered = kdp_df.copy()
        if not kdp_filtered.empty and "date" in kdp_filtered.columns:
            kdp_filtered = kdp_filtered.dropna(subset=["date"])
            kdp_filtered["_date_str"] = kdp_filtered["date"].apply(
                lambda d: d.strftime("%Y-%m-%d") if pd.notna(d) and hasattr(d, "strftime") else str(d)
            )
            kdp_filtered = kdp_filtered[
                (kdp_filtered["_date_str"] >= week_start)
                & (kdp_filtered["_date_str"] <= week_end)
            ]
        for _, row in kdp_filtered.iterrows():
            date_val = row.get("date")
            if pd.notna(date_val) and hasattr(date_val, "strftime"):
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


def get_cumulative_ad_spend(
    current_week_start: str = None,
    db_path: str = None,
) -> float:
    """Get total ad spend from all saved snapshots.

    Optionally excludes a specific week (e.g., the current week being
    analyzed, whose data hasn't been saved yet or will be replaced).
    """
    conn = get_connection(db_path)

    try:
        if current_week_start:
            row = conn.execute(
                """SELECT COALESCE(SUM(cm.spend), 0) as total_spend
                   FROM campaign_metrics cm
                   JOIN weekly_snapshots ws ON cm.snapshot_id = ws.id
                   WHERE ws.week_start != ?""",
                (current_week_start,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COALESCE(SUM(spend), 0) as total_spend FROM campaign_metrics"
            ).fetchone()

        return float(row["total_spend"])

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
        # Use a subquery to get the N most recent weeks, then fetch all
        # campaign rows for those weeks (avoids hardcoded campaign count)
        query = """
            SELECT ws.week_start, cm.campaign_name, cm.{metric}
            FROM campaign_metrics cm
            JOIN weekly_snapshots ws ON cm.snapshot_id = ws.id
            WHERE ws.week_start IN (
                SELECT DISTINCT week_start FROM weekly_snapshots
                ORDER BY week_start DESC LIMIT ?
            )
            {extra_where}
            ORDER BY ws.week_start DESC
        """

        extra_where = ""
        params = [weeks]
        if campaign:
            extra_where = "AND cm.campaign_name = ?"
            params.append(campaign)

        formatted_query = query.format(metric=metric, extra_where=extra_where)

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
