"""Keyword targeting performance analysis with flags."""

import pandas as pd


def analyze_keywords(
    targeting_df: pd.DataFrame,
    config: dict,
) -> dict:
    """Analyze keyword-targeting campaign performance.

    Filters to keyword_targeting campaigns and flags underperforming keywords.

    Args:
        targeting_df: Normalized targeting report DataFrame.
        config: Parsed campaigns.yaml config dict.

    Returns:
        dict with keys:
            - table: DataFrame with per-keyword metrics
            - flags: list of flag dicts
    """
    if targeting_df.empty or "campaign_name" not in targeting_df.columns:
        return {"table": pd.DataFrame(), "flags": []}

    settings = config.get("settings", {})
    high_spend_threshold = settings.get("high_spend_flag", 5.0)

    # Filter to keyword targeting campaigns
    kw_campaigns = []
    for key, campaign in config.get("campaigns", {}).items():
        if campaign.get("type") == "keyword_targeting":
            kw_campaigns.append(campaign["name"])

    df = targeting_df[targeting_df["campaign_name"].isin(kw_campaigns)].copy()

    if df.empty:
        return {"table": pd.DataFrame(), "flags": []}

    # Compute derived metrics
    df["conversion_rate"] = df.apply(
        lambda r: r["orders"] / r["clicks"] if r["clicks"] > 0 else 0,
        axis=1,
    )

    # Sort by impressions descending
    df = df.sort_values("impressions", ascending=False).reset_index(drop=True)

    # Generate flags
    flags = []
    for _, row in df.iterrows():
        keyword = row["targeting"]

        if row["impressions"] == 0:
            flags.append({
                "type": "zero_impressions",
                "severity": "info",
                "target": keyword,
                "message": f"Zero impressions — bid (${row.get('bid', 0):.2f}) may be too low",
            })

        if row["spend"] > high_spend_threshold and row["orders"] == 0:
            flags.append({
                "type": "high_spend_no_orders",
                "severity": "warning",
                "target": keyword,
                "message": f"${row['spend']:.2f} spent with 0 orders",
            })

    return {"table": df, "flags": flags}
