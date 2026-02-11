"""Campaign-level summary with week-over-week comparison."""

from typing import Optional

import pandas as pd


def generate_campaign_summary(
    targeting_df: pd.DataFrame,
    prior_week_df: Optional[pd.DataFrame] = None,
) -> dict:
    """Aggregate targeting data to campaign-level metrics.

    Args:
        targeting_df: Normalized targeting report DataFrame.
        prior_week_df: Optional prior week campaign summary for WoW comparison.

    Returns:
        dict with keys:
            - table: DataFrame with campaign-level metrics
            - wow_available: bool
    """
    grouped = targeting_df.groupby("campaign_name").agg(
        impressions=("impressions", "sum"),
        clicks=("clicks", "sum"),
        spend=("spend", "sum"),
        sales=("sales", "sum"),
        orders=("orders", "sum"),
    ).reset_index()

    # Compute derived metrics
    grouped["ctr"] = grouped.apply(
        lambda r: r["clicks"] / r["impressions"] if r["impressions"] > 0 else 0,
        axis=1,
    )
    grouped["avg_cpc"] = grouped.apply(
        lambda r: r["spend"] / r["clicks"] if r["clicks"] > 0 else 0,
        axis=1,
    )
    grouped["acos"] = grouped.apply(
        lambda r: r["spend"] / r["sales"] if r["sales"] > 0 else None,
        axis=1,
    )
    grouped["roas"] = grouped.apply(
        lambda r: r["sales"] / r["spend"] if r["spend"] > 0 else None,
        axis=1,
    )

    result = {"table": grouped, "wow_available": False}

    # Week-over-week comparison
    if prior_week_df is not None and not prior_week_df.empty:
        prior = prior_week_df.set_index("campaign_name")
        current = grouped.set_index("campaign_name")

        wow_metrics = ["impressions", "clicks", "spend", "orders", "ctr", "acos"]
        for metric in wow_metrics:
            if metric in prior.columns and metric in current.columns:
                delta_col = f"{metric}_delta"
                current[delta_col] = current[metric] - prior[metric]

        grouped = current.reset_index()
        result["table"] = grouped
        result["wow_available"] = True

    return result
