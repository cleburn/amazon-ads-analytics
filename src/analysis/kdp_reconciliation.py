"""KDP sales reconciliation against ad-attributed orders."""

import pandas as pd


def reconcile_kdp_sales(
    kdp_df: pd.DataFrame,
    campaign_summary: dict,
    week_start: str,
    week_end: str,
) -> dict:
    """Reconcile KDP sales data against Amazon ad-attributed orders.

    Compares ground-truth KDP sales with the attributed orders from ad
    campaigns to calculate the attribution gap.

    KDP data may be daily or monthly granularity. When monthly, we match
    on the month containing the week and note that the comparison is
    approximate (monthly KDP vs weekly ads).

    Args:
        kdp_df: Normalized KDP sales DataFrame.
        campaign_summary: Output from generate_campaign_summary().
        week_start: Week start date string (YYYY-MM-DD).
        week_end: Week end date string (YYYY-MM-DD).

    Returns:
        dict with keys:
            - daily_breakdown: DataFrame with sales by period x title x format
            - totals: dict with aggregate numbers
            - attribution_gap: dict with gap analysis
    """
    df = kdp_df.copy()

    if df.empty:
        return {
            "daily_breakdown": pd.DataFrame(),
            "title_totals": pd.DataFrame(),
            "format_totals": pd.DataFrame(),
            "totals": {
                "kdp_units": 0,
                "kdp_royalty": 0.0,
                "ad_attributed_orders": 0,
                "attribution_gap": 0,
                "attribution_gap_pct": 0.0,
            },
            "attribution_gap": {},
        }

    start = pd.to_datetime(week_start)
    end = pd.to_datetime(week_end)
    granularity = "daily"

    # Filter to relevant time window
    if "date" in df.columns:
        # Detect granularity: if all dates are the 1st of the month, it's monthly
        dates = df["date"].dropna()
        if not dates.empty and (dates.dt.day == 1).all():
            granularity = "monthly"
            # Match on the month(s) overlapping with the week
            target_months = set()
            target_months.add(start.to_period("M"))
            target_months.add(end.to_period("M"))
            df = df[df["date"].dt.to_period("M").isin(target_months)].copy()
        else:
            # Daily data — filter to exact week range
            df = df[(df["date"] >= start) & (df["date"] <= end)].copy()

    # Determine units column
    units_col = "net_units_sold" if "net_units_sold" in df.columns else "units_sold"

    # Group columns for breakdown
    group_cols = ["title", "format"]
    if "date" in df.columns and not df.empty:
        group_cols = ["date"] + group_cols

    daily_breakdown = pd.DataFrame()
    if not df.empty and units_col in df.columns:
        daily_breakdown = (
            df.groupby([c for c in group_cols if c in df.columns])
            .agg(
                units=(units_col, "sum"),
                royalty=("royalty", "sum") if "royalty" in df.columns else (units_col, "count"),
            )
            .reset_index()
        )
        if "date" in daily_breakdown.columns:
            daily_breakdown = daily_breakdown.sort_values(["date", "title"])

    # Totals
    total_kdp_units = int(df[units_col].sum()) if units_col in df.columns and not df.empty else 0
    total_kdp_royalty = float(df["royalty"].sum()) if "royalty" in df.columns and not df.empty else 0.0

    # Ad-attributed orders from campaign summary
    summary_table = campaign_summary.get("table", pd.DataFrame())
    total_ad_orders = 0
    if not summary_table.empty and "orders" in summary_table.columns:
        total_ad_orders = int(summary_table["orders"].sum())

    # Attribution gap
    gap = total_kdp_units - total_ad_orders
    gap_pct = (gap / total_kdp_units * 100) if total_kdp_units > 0 else 0

    # Per-title breakdown
    title_totals = pd.DataFrame()
    if not df.empty and units_col in df.columns:
        title_totals = (
            df.groupby("title")
            .agg(
                units=(units_col, "sum"),
                royalty=("royalty", "sum") if "royalty" in df.columns else (units_col, "count"),
            )
            .reset_index()
        )

    # Per-format breakdown
    format_totals = pd.DataFrame()
    if not df.empty and "format" in df.columns:
        format_totals = (
            df.groupby("format")
            .agg(
                units=(units_col, "sum"),
                royalty=("royalty", "sum") if "royalty" in df.columns else (units_col, "count"),
            )
            .reset_index()
        )

    # Build the comparison note
    if granularity == "monthly":
        month_names = sorted(set(
            d.strftime("%B %Y") for d in df["date"].dropna()
        )) if "date" in df.columns and not df.empty else []
        period_str = ", ".join(month_names) if month_names else "the matching month"
        note = (
            f"KDP data is monthly granularity ({period_str}). "
            "Weekly ad-attributed orders compared against full-month KDP sales — "
            "gap may be larger than actual weekly difference. "
            "Amazon's attributed sales often undercount actual sales. "
            "KDP report is ground truth."
        )
    else:
        note = (
            "Amazon's attributed sales often undercount actual sales. "
            "KDP report is ground truth. Unattributed sales may include "
            "organic discovery, read-through, and delayed attribution."
        )

    return {
        "daily_breakdown": daily_breakdown,
        "title_totals": title_totals,
        "format_totals": format_totals,
        "granularity": granularity,
        "totals": {
            "kdp_units": total_kdp_units,
            "kdp_royalty": total_kdp_royalty,
            "ad_attributed_orders": total_ad_orders,
            "attribution_gap": int(gap),
            "attribution_gap_pct": float(gap_pct),
        },
        "attribution_gap": {
            "kdp_total_units": total_kdp_units,
            "ad_attributed_orders": total_ad_orders,
            "unattributed_sales": int(gap),
            "unattributed_pct": float(gap_pct),
            "note": note,
        },
    }
