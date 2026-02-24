"""Parse Amazon Ads Targeting/Campaign Report exports.

Handles three report types:
1. Campaign-level CSV (one row per campaign)
2. Per-campaign targeting report CSVs (bid + suggested bid data)
3. Search term aggregation to per-target level
"""

import pandas as pd


# Column map for campaign-level CSV
CAMPAIGN_COLUMN_MAP = {
    "Campaign name": "campaign_name",
    "Campaign budget amount": "daily_budget",
    "Clicks": "clicks",
    "CTR": "ctr",
    "Total cost": "spend",
    "Total cost (converted)": "spend",
    "CPC": "cpc",
    "CPC (converted)": "cpc",
    "Purchases": "orders",
    "Sales": "sales",
    "Sales (converted)": "sales",
    "ACOS": "acos",
    "Status": "status",
    "Type": "campaign_type",
    "Top-of-search impression share": "top_search_share",
    "Campaign Name": "campaign_name",
}

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

CSV_HEADER_MARKER = "Campaign name"


def _find_header_row(filepath: str, max_rows: int = 10) -> int:
    with open(filepath, "r", encoding="utf-8-sig") as f:
        for i, line in enumerate(f):
            if i >= max_rows:
                break
            if CSV_HEADER_MARKER in line or "Campaign Name" in line:
                return i
    return 0


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


def load_campaign_report(filepath: str) -> pd.DataFrame:
    """Load a campaign-level report CSV (one row per campaign)."""
    if filepath.endswith((".xlsx", ".xls")):
        df = pd.read_excel(filepath, engine="openpyxl")
    else:
        header_row = _find_header_row(filepath)
        df = pd.read_csv(filepath, skiprows=header_row, encoding="utf-8-sig")

    df.columns = df.columns.str.strip()
    rename_map = {k: v for k, v in CAMPAIGN_COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=rename_map)

    for col in ["ctr", "acos"]:
        if col in df.columns and df[col].dtype == object:
            df[col] = _clean_percentage(df[col])
    for col in ["cpc", "spend", "sales", "daily_budget"]:
        if col in df.columns and df[col].dtype == object:
            df[col] = _clean_currency(df[col])
    for col in ["clicks", "orders"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    return df


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
