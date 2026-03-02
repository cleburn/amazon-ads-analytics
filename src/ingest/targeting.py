"""Parse Amazon Ads Targeting/Campaign Report exports.

Handles three report types:
1. Campaign-level CSV (one row per campaign)
2. Per-campaign targeting report CSVs (bid + suggested bid data)
3. Search term aggregation to per-target level
"""

import pandas as pd


# Column map for per-campaign targeting report CSVs
# Two variants: ASIN campaigns have "Categories & products", keyword campaigns have "Keyword"
TARGETING_REPORT_COLUMN_MAP = {
    "State": "state",
    "Categories & products": "targeting_raw",
    "Keyword": "targeting_raw",
    "Target match type": "target_match_type",
    "Status": "status",
    "Suggested bid (low)(USD)": "suggested_bid_low",
    "Suggested bid (median)(USD)": "suggested_bid_median",
    "Suggested bid (high)(USD)": "suggested_bid_high",
    "Bid (USD)": "bid",
    "Impressions": "impressions",
    "Top-of-search impression share": "top_search_share",
    "Clicks": "clicks",
    "CTR": "ctr",
    "Total cost (USD)": "spend",
    "CPC (USD)": "cpc",
    "Purchases": "orders",
    "Sales (USD)": "sales",
    "ACOS": "acos",
    "KENP read": "kenp_read",
    "Estimated KENP royalties (USD)": "kenp_royalty",
    "Purchase rate": "purchase_rate",
}

def _clean_percentage(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.replace("%", "", regex=False)
        .str.replace("<", "", regex=False)
        .str.strip()
        .replace("", "0")
        .replace("nan", "0")
        .astype(float)
    )


def _clean_currency(series: pd.Series) -> pd.Series:
    cleaned = (
        series.astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip()
        .replace("", "0")
    )
    return pd.to_numeric(cleaned, errors="coerce").fillna(0.0)


def _normalize_targeting(series: pd.Series) -> pd.Series:
    """Strip ASIN targeting wrappers: asin-expanded="X" and asin="X" -> X."""
    return (
        series.astype(str)
        .str.replace('asin-expanded="', "", regex=False)
        .str.replace('asin="', "", regex=False)
        .str.replace('"', "", regex=False)
        .str.strip()
    )


def _derive_match_type(targeting_raw: str, target_match_type: str) -> str:
    """Derive match type from raw targeting string and report column.

    For ASIN targets: asin="X" -> exact, asin-expanded="X" -> expanded
    For keywords: use the Target match type column value (e.g. "Broad")
    """
    raw = str(targeting_raw)
    if raw.startswith('asin="'):
        return "exact"
    elif raw.startswith('asin-expanded="'):
        return "expanded"
    else:
        # Keyword — use the report's match type column
        mt = str(target_match_type).strip()
        return mt if mt and mt != "—" and mt != "nan" else "broad"


def build_targeting_from_search_terms(search_term_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate search term report data to per-target level.

    When no separate targeting report is available, we derive per-target
    metrics by grouping the search term report by (campaign_name, targeting).
    """
    if search_term_df.empty:
        return pd.DataFrame()

    grouped = (
        search_term_df.groupby(["campaign_name", "targeting"])
        .agg(
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
            spend=("spend", "sum"),
            sales=("sales", "sum"),
            orders=("orders", "sum"),
        )
        .reset_index()
    )

    # Compute derived metrics
    grouped["ctr"] = grouped.apply(
        lambda r: r["clicks"] / r["impressions"] if r["impressions"] > 0 else 0,
        axis=1,
    )
    grouped["cpc"] = grouped.apply(
        lambda r: r["spend"] / r["clicks"] if r["clicks"] > 0 else 0,
        axis=1,
    )
    grouped["acos"] = grouped.apply(
        lambda r: r["spend"] / r["sales"] if r["sales"] > 0 else None,
        axis=1,
    )

    grouped["targeting_raw"] = grouped["targeting"]

    return grouped


def load_targeting_reports(filepaths: list) -> pd.DataFrame:
    """Load and concatenate multiple per-campaign targeting report CSVs.

    Handles two column variants:
    - ASIN campaigns: "Categories & products" column with asin="..." values
    - Keyword campaigns: "Keyword" column with keyword text

    Returns a DataFrame with normalized columns including bid and suggested bids.
    Note: performance metrics are lifetime cumulative, not weekly.
    """
    frames = []
    for filepath in filepaths:
        df = pd.read_csv(filepath, encoding="utf-8-sig")
        df.columns = df.columns.str.strip()

        rename_map = {k: v for k, v in TARGETING_REPORT_COLUMN_MAP.items() if k in df.columns}
        df = df.rename(columns=rename_map)

        if "targeting_raw" not in df.columns:
            import sys
            print(f"  Warning: Skipping {filepath} — no targeting column found", file=sys.stderr)
            continue

        # Derive match type from raw targeting string
        df["match_type"] = df.apply(
            lambda r: _derive_match_type(
                r.get("targeting_raw", ""),
                r.get("target_match_type", ""),
            ),
            axis=1,
        )

        # Normalize targeting (strip asin="..." wrappers)
        df["targeting"] = _normalize_targeting(df["targeting_raw"])

        # Clean currency columns
        for col in ["bid", "suggested_bid_low", "suggested_bid_median",
                     "suggested_bid_high", "spend", "cpc", "sales", "kenp_royalty"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

        # Clean integer columns
        for col in ["impressions", "clicks", "orders", "kenp_read"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        # Clean percentage columns
        for col in ["ctr", "acos", "purchase_rate"]:
            if col in df.columns and df[col].dtype == object:
                df[col] = _clean_percentage(df[col])

        # Top-of-search impression share: can be "0", "<5%", "92.86%", etc.
        if "top_search_share" in df.columns and df["top_search_share"].dtype == object:
            df["top_search_share"] = (
                df["top_search_share"]
                .astype(str)
                .str.replace("%", "", regex=False)
                .str.replace("<", "", regex=False)
                .str.strip()
                .replace("", "0")
                .replace("nan", "0")
            )
            df["top_search_share"] = pd.to_numeric(
                df["top_search_share"], errors="coerce"
            ).fillna(0.0)

        # Normalize state column
        if "state" in df.columns:
            df["state"] = df["state"].astype(str).str.strip().str.upper()

        # Drop the intermediate column
        if "target_match_type" in df.columns:
            df = df.drop(columns=["target_match_type"])

        frames.append(df)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


def build_target_to_campaign_map(config: dict) -> dict:
    """Build a mapping from normalized targeting value to campaign name.

    Each ASIN/keyword appears in only one campaign, so the mapping is
    unambiguous. Includes both active and paused targets.
    """
    mapping = {}
    for _key, campaign in config.get("campaigns", {}).items():
        name = campaign["name"]
        for target in campaign.get("targets", []):
            mapping[target["asin"]] = name
        for target in campaign.get("paused_targets", []):
            mapping[target["asin"]] = name
        for kw in campaign.get("keywords", []):
            mapping[kw["keyword"]] = name
        for kw in campaign.get("paused_keywords", []):
            mapping[kw["keyword"]] = name
    return mapping


def build_supplemental_targeting(
    targeting_report_df: pd.DataFrame,
    prior_lifetime_df: pd.DataFrame,
    search_term_targeting_df: pd.DataFrame,
    config: dict,
    bid_lookup: dict = None,
) -> pd.DataFrame:
    """Build targeting rows for targets not in search term data.

    Computes week-over-week deltas from lifetime targeting report data.
    Only creates rows for targets absent from search_term_targeting_df.
    This surfaces campaigns like Self Targeting and Deconstruction that
    don't generate search term rows, as well as ASIN targets that had
    impressions but zero clicks.

    Args:
        targeting_report_df: Full targeting report DataFrame (lifetime cumulative).
        prior_lifetime_df: Prior week's targeting report lifetime DataFrame.
        search_term_targeting_df: Per-target DataFrame derived from search terms.
        config: Campaign config dict.
        bid_lookup: Optional bid data dict from build_bid_lookup().

    Returns:
        DataFrame with supplemental targeting rows (same schema as
        build_targeting_from_search_terms output), with an added
        data_source column ("targeting_report_delta" or "targeting_report_lifetime").
    """
    if targeting_report_df.empty:
        return pd.DataFrame()

    bid_lookup = bid_lookup or {}
    target_to_campaign = build_target_to_campaign_map(config)

    # Get campaigns and targets already in search term data
    existing_targets = set()
    existing_campaigns = set()
    if not search_term_targeting_df.empty:
        existing_targets = set(search_term_targeting_df["targeting"].unique())
        if "campaign_name" in search_term_targeting_df.columns:
            existing_campaigns = set(search_term_targeting_df["campaign_name"].unique())

    # Aggregate current lifetime by normalized targeting (sum exact + expanded)
    current = targeting_report_df.copy()
    current_grouped = (
        current.groupby("targeting")
        .agg(
            impressions=("impressions", "sum"),
            clicks=("clicks", "sum"),
            spend=("spend", "sum"),
            orders=("orders", "sum"),
            sales=("sales", "sum"),
        )
        .reset_index()
    )

    # Compute deltas if prior data available
    if prior_lifetime_df is not None and not prior_lifetime_df.empty:
        prior_grouped = (
            prior_lifetime_df.groupby("targeting")
            .agg(
                impressions=("impressions", "sum"),
                clicks=("clicks", "sum"),
                spend=("spend", "sum"),
                orders=("orders", "sum"),
                sales=("sales", "sum"),
            )
            .reset_index()
        )

        merged = current_grouped.merge(
            prior_grouped, on="targeting", how="left", suffixes=("", "_prior")
        )
        for col in ["impressions", "clicks", "spend", "orders", "sales"]:
            prior_col = f"{col}_prior"
            if prior_col in merged.columns:
                merged[col] = merged[col] - merged[prior_col].fillna(0)
                merged[col] = merged[col].clip(lower=0)

        delta = merged.drop(
            columns=[c for c in merged.columns if c.endswith("_prior")]
        )
        data_source = "targeting_report_delta"
    else:
        delta = current_grouped
        data_source = "targeting_report_lifetime"

    # Map to campaign names via config (before filtering)
    delta["campaign_name"] = delta["targeting"].map(target_to_campaign)
    delta = delta.dropna(subset=["campaign_name"])

    if delta.empty:
        return pd.DataFrame()

    # Only include targets for campaigns ENTIRELY absent from search term data.
    # For campaigns that DO appear in search term data (ASIN, Keyword), their
    # zero-click targets remain as zero_activity flags rather than inflating
    # the campaign summary with lifetime numbers.
    supplemental = delta[
        ~delta["campaign_name"].isin(existing_campaigns)
    ].copy()

    if supplemental.empty:
        return pd.DataFrame()

    # Add derived metrics
    supplemental["ctr"] = supplemental.apply(
        lambda r: r["clicks"] / r["impressions"] if r["impressions"] > 0 else 0,
        axis=1,
    )
    supplemental["cpc"] = supplemental.apply(
        lambda r: r["spend"] / r["clicks"] if r["clicks"] > 0 else 0,
        axis=1,
    )
    supplemental["acos"] = supplemental.apply(
        lambda r: r["spend"] / r["sales"] if r["sales"] > 0 else None,
        axis=1,
    )

    # Enrich with bid data
    supplemental["bid"] = supplemental["targeting"].map(
        lambda t: bid_lookup.get(t, {}).get("bid"))
    supplemental["suggested_bid_low"] = supplemental["targeting"].map(
        lambda t: bid_lookup.get(t, {}).get("suggested_bid_low"))
    supplemental["suggested_bid_median"] = supplemental["targeting"].map(
        lambda t: bid_lookup.get(t, {}).get("suggested_bid_median"))
    supplemental["suggested_bid_high"] = supplemental["targeting"].map(
        lambda t: bid_lookup.get(t, {}).get("suggested_bid_high"))

    supplemental["data_source"] = data_source
    supplemental["targeting_raw"] = supplemental["targeting"]

    return supplemental


def build_bid_lookup(targeting_report_df: pd.DataFrame) -> dict:
    """Build a targeting -> bid data lookup from targeting reports.

    Filters to ENABLED rows. If multiple ENABLED rows exist for the same
    normalized targeting (e.g. Sophia Code with both exact + expanded),
    takes the row with higher impressions.

    Returns:
        dict of {targeting: {"bid", "suggested_bid_low", "suggested_bid_median",
                             "suggested_bid_high"}}
    """
    if targeting_report_df.empty:
        return {}

    df = targeting_report_df.copy()

    # Prefer ENABLED rows
    enabled = df[df["state"] == "ENABLED"]
    if enabled.empty:
        enabled = df  # Fall back to all rows if none are enabled

    # For each normalized targeting, keep the row with most impressions
    impr_col = "impressions" if "impressions" in enabled.columns else None
    if impr_col:
        enabled = enabled.sort_values(impr_col, ascending=False)

    enabled = enabled.drop_duplicates(subset=["targeting"], keep="first")

    lookup = {}
    for _, row in enabled.iterrows():
        targeting = row["targeting"]
        bid_val = row.get("bid", 0.0)
        lookup[targeting] = {
            "bid": bid_val if bid_val > 0 else None,
            "suggested_bid_low": row.get("suggested_bid_low") or None,
            "suggested_bid_median": row.get("suggested_bid_median") or None,
            "suggested_bid_high": row.get("suggested_bid_high") or None,
        }

    return lookup
