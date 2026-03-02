"""Campaign-level summary with week-over-week comparison."""

from typing import Optional

import pandas as pd

from src.ingest.targeting import _METRIC_AGG, DATA_SOURCE_SEARCH_TERMS


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

    grouped = targeting_df.groupby("campaign_name").agg(**_METRIC_AGG).reset_index()

    # Propagate data_source: if any row for a campaign is supplemental, label it
    if "data_source" in targeting_df.columns:
        source_map = (
            targeting_df.groupby("campaign_name")["data_source"]
            .apply(lambda x: x.iloc[0] if x.nunique() == 1 else "mixed")
            .to_dict()
        )
        grouped["data_source"] = grouped["campaign_name"].map(source_map)
    else:
        grouped["data_source"] = DATA_SOURCE_SEARCH_TERMS

    # Compute derived metrics
    grouped["ctr"] = (grouped["clicks"] / grouped["impressions"]).where(grouped["impressions"] > 0, 0)
    grouped["avg_cpc"] = (grouped["spend"] / grouped["clicks"]).where(grouped["clicks"] > 0, 0)
    grouped["acos"] = (grouped["spend"] / grouped["sales"]).where(grouped["sales"] > 0, None)
    grouped["roas"] = (grouped["sales"] / grouped["spend"]).where(grouped["spend"] > 0, None)

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
