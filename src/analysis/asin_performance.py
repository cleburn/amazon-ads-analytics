"""ASIN target performance analysis with flags."""

import pandas as pd
import yaml


def analyze_asin_targets(
    targeting_df: pd.DataFrame,
    config: dict,
) -> dict:
    """Analyze ASIN-targeting campaign performance.

    Filters to product_targeting campaigns, enriches with config data,
    and flags underperforming targets.

    Args:
        targeting_df: Normalized targeting report DataFrame.
        config: Parsed campaigns.yaml config dict.

    Returns:
        dict with keys:
            - table: DataFrame with per-target metrics
            - flags: list of flag dicts
    """
    if targeting_df.empty or "campaign_name" not in targeting_df.columns:
        return {"table": pd.DataFrame(), "flags": [], "zero_activity_targets": []}

    settings = config.get("settings", {})
    high_spend_threshold = settings.get("high_spend_flag", 5.0)
    low_impressions_threshold = settings.get("low_impressions_flag", 10)

    # Filter to product targeting campaigns
    asin_campaigns = []
    for key, campaign in config.get("campaigns", {}).items():
        if campaign.get("type") == "product_targeting":
            asin_campaigns.append(campaign["name"])

    df = targeting_df[targeting_df["campaign_name"].isin(asin_campaigns)].copy()

    # Build lookup from config targets (product_targeting campaigns only)
    target_lookup = {}
    for key, campaign in config.get("campaigns", {}).items():
        if campaign.get("type") != "product_targeting":
            continue
        for target in campaign.get("targets", []):
            target_lookup[target["asin"]] = {
                "title": target.get("title", ""),
                "config_bid": target.get("bid", None),
                "campaign_key": key,
            }

    flags = []
    zero_activity_targets = []

    if not df.empty:
        # Enrich with config data
        df["target_title"] = df["targeting"].map(
            lambda x: target_lookup.get(x, {}).get("title", "")
        )
        df["config_bid"] = df["targeting"].map(
            lambda x: target_lookup.get(x, {}).get("config_bid")
        )

        # Compute derived metrics
        df["conversion_rate"] = df.apply(
            lambda r: r["orders"] / r["clicks"] if r["clicks"] > 0 else 0,
            axis=1,
        )

        # Sort by spend descending
        df = df.sort_values("spend", ascending=False).reset_index(drop=True)

        # Generate flags for targets with data
        for _, row in df.iterrows():
            target_id = row["targeting"]
            title = row["target_title"] or target_id

            if row["spend"] > high_spend_threshold and row["orders"] == 0:
                flags.append({
                    "type": "high_spend_no_orders",
                    "severity": "warning",
                    "target": target_id,
                    "title": title,
                    "message": f"${row['spend']:.2f} spent with 0 orders",
                })

            if row["impressions"] < low_impressions_threshold:
                flags.append({
                    "type": "underserving",
                    "severity": "info",
                    "target": target_id,
                    "title": title,
                    "message": f"Only {row['impressions']} impressions (bid may be too low)",
                })

    # Detect zero-activity targets: configured but absent from search term data
    active_asins = set(df["targeting"].unique()) if not df.empty else set()
    for asin, info in target_lookup.items():
        if asin not in active_asins:
            zero_activity_targets.append({
                "asin": asin,
                "title": info["title"],
                "bid": info["config_bid"],
            })
            flags.append({
                "type": "zero_activity",
                "severity": "info",
                "target": asin,
                "title": info["title"] or asin,
                "message": (
                    f"{info['title'] or asin} ({asin}): "
                    f"No activity this week — not appearing in search term data"
                ),
            })

    return {"table": df, "flags": flags, "zero_activity_targets": zero_activity_targets}
