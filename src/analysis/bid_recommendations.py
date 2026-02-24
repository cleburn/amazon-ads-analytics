"""Bid recommendations based on conversion rates and profitability."""

import pandas as pd


def recommend_bids(
    targeting_df: pd.DataFrame,
    config: dict,
) -> dict:
    """Calculate max profitable bids for each target/keyword.

    Formula: max_bid = blended_royalty * conversion_rate / target_acos

    The three-column bid display:
    - Current Bid: actual bid from targeting report exports
    - Suggested Bid: Amazon's median suggested bid from targeting report
    - Max Profitable Bid: calculated ceiling based on conversion data

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

    # Current bid and suggested bid (from targeting report enrichment)
    has_bid = "bid" in df.columns
    has_suggested = "suggested_bid_median" in df.columns

    # Generate flags
    flags = []
    for _, row in df.iterrows():
        target = row["targeting"]
        campaign = row.get("campaign_name", "")
        current_bid = row.get("bid") if has_bid and pd.notna(row.get("bid")) else None
        suggested_bid = row.get("suggested_bid_median") if has_suggested and pd.notna(row.get("suggested_bid_median")) else None
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
                    "suggested_bid": suggested_bid,
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
                "suggested_bid": suggested_bid,
                "recommended_bid": None,
                "message": (
                    f"{clicks} clicks but 0 orders — no conversion data yet. "
                    "Consider lowering bid or pausing if trend continues."
                ),
            })
            continue

        if current_bid is not None and max_bid is not None:
            if current_bid > max_bid:
                msg = f"Current bid ${current_bid:.2f} exceeds max profitable bid ${max_bid:.2f} at {target_acos:.0%} ACoS target"
                if suggested_bid:
                    msg += f" (Amazon suggests ${suggested_bid:.2f})"
                flags.append({
                    "type": "bid_above_profitable",
                    "severity": "warning",
                    "target": target,
                    "campaign": campaign,
                    "current_bid": current_bid,
                    "suggested_bid": suggested_bid,
                    "recommended_bid": max_bid,
                    "message": msg,
                })
            elif current_bid < max_bid * 0.5:
                msg = (
                    f"Current bid ${current_bid:.2f} is well below max profitable "
                    f"bid ${max_bid:.2f} — room to increase for more impressions"
                )
                if suggested_bid:
                    msg += f" (Amazon suggests ${suggested_bid:.2f})"
                flags.append({
                    "type": "bid_below_range",
                    "severity": "info",
                    "target": target,
                    "campaign": campaign,
                    "current_bid": current_bid,
                    "suggested_bid": suggested_bid,
                    "recommended_bid": max_bid,
                    "message": msg,
                })

    # Build recommendation table
    cols = [
        "campaign_name",
        "targeting",
        "impressions",
        "clicks",
        "orders",
        "spend",
        "conversion_rate",
    ]
    rec_df = df[cols].copy()

    if has_bid:
        rec_df["current_bid"] = df["bid"]
    if has_suggested:
        rec_df["suggested_bid"] = df["suggested_bid_median"]
    rec_df["max_profitable_bid"] = df["max_profitable_bid"]

    # Sort by spend descending (most spend = most important to optimize)
    rec_df = rec_df.sort_values("spend", ascending=False).reset_index(drop=True)

    return {"table": rec_df, "flags": flags}
