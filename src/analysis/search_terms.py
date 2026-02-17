"""Search term analysis with drift detection."""

import pandas as pd


def apply_asin_resolution(result: dict, asin_map: dict) -> dict:
    """Apply ASIN-to-title resolution to search term analysis results.

    Rewrites search_term values in the summary DataFrame and updates
    drift flag messages to use resolved titles.

    Args:
        result: Output dict from analyze_search_terms().
        asin_map: Mapping of raw ASIN → display name from resolve_asins().

    Returns:
        The same result dict, mutated in place.
    """
    if not asin_map:
        return result

    # Resolve summary search terms
    summary = result.get("summary", pd.DataFrame())
    if not summary.empty and "search_term" in summary.columns:
        result["summary"] = summary.copy()
        result["summary"]["search_term"] = result["summary"]["search_term"].map(
            lambda t: asin_map.get(t, t)
        )

    # Resolve ASINs in drift flag messages
    drift_flags = result.get("drift_flags", [])
    for flag in drift_flags:
        st = flag.get("search_term", "")
        tgt = flag.get("targeting", "")
        st_display = asin_map.get(st, st)
        tgt_display = asin_map.get(tgt, tgt)
        if st_display != st or tgt_display != tgt:
            flag["message"] = (
                f"{flag['type'].replace('_', ' ').title()}: targeted '{tgt_display}' "
                f"but appeared on '{st_display}' "
                f"({flag.get('impressions', 0)} impressions, "
                f"${flag.get('spend', 0):.2f} spend)"
            )

    return result


def analyze_search_terms(
    search_term_df: pd.DataFrame,
    config: dict,
) -> dict:
    """Analyze actual search terms and detect targeting drift.

    Groups search terms by their intended targeting expression and flags
    cases where the actual placement doesn't match the intended target.

    Args:
        search_term_df: Normalized search term report DataFrame.
        config: Parsed campaigns.yaml config dict.

    Returns:
        dict with keys:
            - grouped: dict mapping targeting expression to DataFrame of search terms
            - drift_flags: list of drift flag dicts
            - summary: DataFrame with search term rollup
    """
    settings = config.get("settings", {})
    transition_date = settings.get("exact_match_transition_date")

    df = search_term_df.copy()

    if df.empty:
        return {"grouped": {}, "drift_flags": [], "summary": pd.DataFrame()}

    # Drift detection: compare targeting vs search_term
    # For exact match, they should be identical
    # For broad/phrase match, search_term can legitimately differ from targeting
    drift_flags = []

    for _, row in df.iterrows():
        targeting = str(row.get("targeting", "")).strip()
        search_term = str(row.get("search_term", "")).strip()
        match_type = str(row.get("match_type", "")).strip().lower()
        campaign = row.get("campaign_name", "")

        # For ASIN campaigns with exact match, search term should equal targeting
        if match_type == "exact" and targeting != search_term:
            drift_flags.append({
                "type": "exact_match_drift",
                "severity": "warning",
                "campaign": campaign,
                "targeting": targeting,
                "search_term": search_term,
                "impressions": row.get("impressions", 0),
                "spend": row.get("spend", 0),
                "message": (
                    f"Exact match drift: targeted '{targeting}' but appeared on "
                    f"'{search_term}' ({row.get('impressions', 0)} impressions, "
                    f"${row.get('spend', 0):.2f} spend)"
                ),
            })

        # For broad match keywords, flag if search term is very different
        # (This is informational — broad match is expected to expand)
        if match_type == "broad" and targeting.lower() not in search_term.lower():
            # Only flag if there's meaningful spend
            if row.get("spend", 0) > 0.50:
                drift_flags.append({
                    "type": "broad_match_expansion",
                    "severity": "info",
                    "campaign": campaign,
                    "targeting": targeting,
                    "search_term": search_term,
                    "impressions": row.get("impressions", 0),
                    "spend": row.get("spend", 0),
                    "message": (
                        f"Broad match expanded: '{targeting}' → '{search_term}' "
                        f"(${row.get('spend', 0):.2f} spend)"
                    ),
                })

    # Group search terms by targeting expression
    grouped = {}
    for targeting_expr, group_df in df.groupby("targeting"):
        grouped[targeting_expr] = group_df.sort_values(
            "impressions", ascending=False
        ).reset_index(drop=True)

    # Summary: top search terms by spend
    summary = (
        df.groupby("search_term")
        .agg(
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
            spend=("spend", "sum"),
            orders=("orders", "sum"),
        )
        .sort_values("spend", ascending=False)
        .reset_index()
    )

    transition_note = ""
    if transition_date:
        transition_note = (
            f"Note: Switched from expanded to exact ASIN matching on {transition_date}. "
            "Drift before this date may reflect expanded match behavior."
        )

    return {
        "grouped": grouped,
        "drift_flags": drift_flags,
        "summary": summary,
        "transition_note": transition_note,
    }
