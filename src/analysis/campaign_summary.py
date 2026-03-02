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
    if targeting_df.empty or "campaign_name" not in targeting_df.columns:
        return {"table": pd.DataFrame(), "wow_available": False}

    agg_dict = {
        "impressions": ("impressions", "sum"),
        "clicks": ("clicks", "sum"),
        "spend": ("spend", "sum"),
        "sales": ("sales", "sum"),
        "orders": ("orders", "sum"),
    }

    grouped = targeting_df.groupby("campaign_name").agg(**agg_dict).reset_index()

    # Propagate data_source: if any row for a campaign is supplemental, label it
    if "data_source" in targeting_df.columns:
        source_map = (
            targeting_df.groupby("campaign_name")["data_source"]
            .apply(lambda x: x.iloc[0] if x.nunique() == 1 else "mixed")
            .to_dict()
        )
        grouped["data_source"] = grouped["campaign_name"].map(source_map)
    else:
        grouped["data_source"] = "search_terms"

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
