"""Bid recommendations based on conversion rates and profitability."""

import pandas as pd


def recommend_bids(
    targeting_df: pd.DataFrame,
    config: dict,
) -> dict:
    """Calculate max profitable bids for each target/keyword.

    Formula: max_bid = blended_royalty * conversion_rate / target_acos

    Args:
        targeting_df: Normalized targeting report DataFrame.
        config: Parsed campaigns.yaml config dict.

    Returns:
        dict with keys:
            - table: DataFrame with bid recommendations
            - flags: list of flag dicts
    """
    settings = config.get("settings", {})
    target_acos = settings.get("target_acos", 0.50)
    blended_royalty = settings.get("blended_royalty", 5.00)

    if target_acos <= 0:
        target_acos = 0.50

    df = targeting_df.copy()

    if df.empty:
        return {"table": pd.DataFrame(), "flags": []}

    # Compute conversion rate
    df["conversion_rate"] = df.apply(
        lambda r: r["orders"] / r["clicks"] if r["clicks"] > 0 else 0,
        axis=1,
    )

    # Calculate max profitable bid
    # max_bid = blended_royalty * conversion_rate / target_acos
    df["max_profitable_bid"] = df["conversion_rate"].apply(
        lambda cr: (blended_royalty * cr / target_acos) if cr > 0 else None
    )

    # Current bid (from report or config)
    current_bid_col = "bid" if "bid" in df.columns else None

    # Generate flags
    flags = []
    for _, row in df.iterrows():
        target = row["targeting"]
        campaign = row.get("campaign_name", "")
        current_bid = row.get("bid") if current_bid_col else None
        max_bid = row.get("max_profitable_bid")
        clicks = row.get("clicks", 0)

        if clicks == 0:
            if row.get("impressions", 0) == 0:
                flags.append({
                    "type": "no_data",
                    "severity": "info",
                    "target": target,
                    "campaign": campaign,
                    "current_bid": current_bid,
                    "recommended_bid": None,
                    "message": "No impressions or clicks — insufficient data for bid recommendation",
                })
            continue

        if row.get("orders", 0) == 0:
            flags.append({
                "type": "no_conversions",
                "severity": "info",
                "target": target,
                "campaign": campaign,
                "current_bid": current_bid,
                "recommended_bid": None,
                "message": (
                    f"{clicks} clicks but 0 orders — no conversion data yet. "
                    "Consider lowering bid or pausing if trend continues."
                ),
            })
            continue

        if current_bid is not None and max_bid is not None:
            if current_bid > max_bid:
                flags.append({
                    "type": "bid_above_profitable",
                    "severity": "warning",
                    "target": target,
                    "campaign": campaign,
                    "current_bid": current_bid,
                    "recommended_bid": max_bid,
                    "message": (
                        f"Current bid ${current_bid:.2f} exceeds max profitable "
                        f"bid ${max_bid:.2f} at {target_acos:.0%} ACoS target"
                    ),
                })
            elif current_bid < max_bid * 0.5:
                # Bid is less than half the profitable max — may be missing impressions
                flags.append({
                    "type": "bid_below_range",
                    "severity": "info",
                    "target": target,
                    "campaign": campaign,
                    "current_bid": current_bid,
                    "recommended_bid": max_bid,
                    "message": (
                        f"Current bid ${current_bid:.2f} is well below max profitable "
                        f"bid ${max_bid:.2f} — room to increase for more impressions"
                    ),
                })

    # Add recommendation columns for display
    rec_df = df[
        [
            "campaign_name",
            "targeting",
            "impressions",
            "clicks",
            "orders",
            "spend",
            "conversion_rate",
        ]
    ].copy()

    if current_bid_col:
        rec_df["current_bid"] = df["bid"]
    rec_df["max_profitable_bid"] = df["max_profitable_bid"]

    # Sort by spend descending (most spend = most important to optimize)
    rec_df = rec_df.sort_values("spend", ascending=False).reset_index(drop=True)

    return {"table": rec_df, "flags": flags}
