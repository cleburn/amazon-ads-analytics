"""Parse Amazon Ads Targeting/Campaign Report exports (CSV or XLSX).

Amazon provides two kinds of exports:
1. A per-target "Targeting Report" with one row per keyword/ASIN (not always available)
2. A campaign-level CSV with one row per campaign

This module handles both. When only the campaign-level CSV is available,
per-target data comes from the search term report aggregated by targeting.
"""

import pandas as pd


COLUMN_MAP = {
    # Campaign-level CSV columns (actual format from Amazon)
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
    "Targeting": "targeting_mode",
    "Top-of-search impression share": "top_search_share",
    # Per-target report columns (if available)
    "Campaign Name": "campaign_name",
    "Targeting": "targeting",
    "Match Type": "match_type",
    "Bid": "bid",
    "Impressions": "impressions",
    "Spend": "spend",
    "Cost Per Click (CPC)": "cpc",
    "Click-Thru Rate (CTR)": "ctr",
    "14 Day Total Sales ": "sales",
    "14 Day Total Sales": "sales",
    "14 Day Total Orders (#)": "orders",
    "Total Advertising Cost of Sales (ACOS) ": "acos",
    "Total Advertising Cost of Sales (ACOS)": "acos",
    "7 Day Total Sales": "sales",
    "7 Day Total Orders (#)": "orders",
    "Total Advertising Cost of Sales (ACoS)": "acos",
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
    return (
        series.astype(str)
        .str.replace('asin-expanded="', "", regex=False)
        .str.replace('asin="', "", regex=False)
        .str.replace('"', "", regex=False)
        .str.strip()
    )


def load_campaign_report(filepath: str) -> pd.DataFrame:
    """Load a campaign-level report CSV (one row per campaign).

    Returns a DataFrame with campaign-level metrics.
    """
    if filepath.endswith((".xlsx", ".xls")):
        df = pd.read_excel(filepath, engine="openpyxl")
    else:
        header_row = _find_header_row(filepath)
        df = pd.read_csv(filepath, skiprows=header_row, encoding="utf-8-sig")

    df.columns = df.columns.str.strip()
    rename_map = {k: v for k, v in COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=rename_map)

    # Clean percentage/currency columns if stored as strings
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

    # Preserve targeting_raw (same as targeting here since already normalized)
    grouped["targeting_raw"] = grouped["targeting"]

    return grouped


def load_targeting_report(filepath: str) -> pd.DataFrame:
    """Load a per-target targeting report (CSV or XLSX).

    Falls back gracefully if the file is actually campaign-level.
    """
    if filepath.endswith((".xlsx", ".xls")):
        df = pd.read_excel(filepath, engine="openpyxl")
    else:
        header_row = _find_header_row(filepath)
        df = pd.read_csv(filepath, skiprows=header_row, encoding="utf-8-sig")

    df.columns = df.columns.str.strip()
    rename_map = {k: v for k, v in COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=rename_map)

    for col in ["ctr", "acos"]:
        if col in df.columns and df[col].dtype == object:
            df[col] = _clean_percentage(df[col])
    for col in ["cpc", "spend", "sales", "bid"]:
        if col in df.columns and df[col].dtype == object:
            df[col] = _clean_currency(df[col])
    for col in ["impressions", "clicks", "orders"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    if "targeting" in df.columns:
        df["targeting_raw"] = df["targeting"]
        df["targeting"] = _normalize_targeting(df["targeting"])

    return df
