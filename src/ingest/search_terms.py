"""Parse Amazon Ads Search Term Report exports (CSV or XLSX)."""

import pandas as pd


# Map Amazon column names to internal names.
# Amazon uses "14 Day" attribution windows; we normalize to generic names.
COLUMN_MAP = {
    "Campaign Name": "campaign_name",
    "Targeting": "targeting",
    "Match Type": "match_type",
    "Customer Search Term": "search_term",
    "Impressions": "impressions",
    "Clicks": "clicks",
    "Click-Thru Rate (CTR)": "ctr",
    "Cost Per Click (CPC)": "cpc",
    "Spend": "spend",
    "Start Date": "start_date",
    "End Date": "end_date",
    # 14-day attribution columns (actual Amazon export format)
    "14 Day Total Sales ": "sales",
    "14 Day Total Sales": "sales",
    "Total Advertising Cost of Sales (ACOS) ": "acos",
    "Total Advertising Cost of Sales (ACOS)": "acos",
    "Total Return on Advertising Spend (ROAS)": "roas",
    "14 Day Total Orders (#)": "orders",
    "14 Day Total Units (#)": "units",
    "14 Day Conversion Rate": "conversion_rate",
    "14 Day Total KENP Read (#)": "kenp_read",
    "Estimated KENP Royalties": "kenp_royalties",
    # 7-day attribution columns (older export format)
    "7 Day Total Sales": "sales",
    "7 Day Total Orders (#)": "orders",
    "Total Advertising Cost of Sales (ACoS)": "acos",
}

CSV_HEADER_MARKER = "Campaign Name"


def _find_header_row(filepath: str, max_rows: int = 10) -> int:
    """Scan first N rows to find the actual header row in a CSV."""
    with open(filepath, "r", encoding="utf-8-sig") as f:
        for i, line in enumerate(f):
            if i >= max_rows:
                break
            if CSV_HEADER_MARKER in line:
                return i
    return 0


def _clean_percentage(series: pd.Series) -> pd.Series:
    """Convert percentage strings like '2.50%' to float 0.025."""
    return (
        series.astype(str)
        .str.replace("%", "", regex=False)
        .str.strip()
        .replace("", "0")
        .astype(float)
        / 100
    )


def _clean_currency(series: pd.Series) -> pd.Series:
    """Convert currency strings like '$0.72' to float 0.72."""
    return (
        series.astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip()
        .replace("", "0")
        .astype(float)
    )


def _normalize_targeting(series: pd.Series) -> pd.Series:
    """Strip ASIN targeting wrappers.

    Handles both formats:
      asin="B01K1T4U5U"     -> B01K1T4U5U
      asin-expanded="B01K"  -> B01K
    """
    return (
        series.astype(str)
        .str.replace('asin-expanded="', "", regex=False)
        .str.replace('asin="', "", regex=False)
        .str.replace('"', "", regex=False)
        .str.strip()
    )


def load_search_term_report(filepath: str) -> pd.DataFrame:
    """Load and normalize an Amazon Search Term Report (CSV or XLSX).

    Returns a DataFrame with standardized column names and clean data types.
    """
    if filepath.endswith((".xlsx", ".xls")):
        df = pd.read_excel(filepath, engine="openpyxl")
    else:
        header_row = _find_header_row(filepath)
        df = pd.read_csv(filepath, skiprows=header_row, encoding="utf-8-sig")

    # Strip whitespace from column names
    df.columns = df.columns.str.strip()

    # Map to internal names (only columns that exist)
    rename_map = {k: v for k, v in COLUMN_MAP.items() if k in df.columns}
    df = df.rename(columns=rename_map)

    # Clean percentage columns (only if stored as strings)
    for col in ["ctr", "acos", "conversion_rate"]:
        if col in df.columns and df[col].dtype == object:
            df[col] = _clean_percentage(df[col])

    # Clean currency columns (only if stored as strings)
    for col in ["cpc", "spend", "sales"]:
        if col in df.columns and df[col].dtype == object:
            df[col] = _clean_currency(df[col])

    # Ensure numeric types
    for col in ["impressions", "clicks", "orders", "units", "kenp_read"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    for col in ["cpc", "spend", "sales", "kenp_royalties"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    # Normalize targeting format
    if "targeting" in df.columns:
        df["targeting_raw"] = df["targeting"]
        df["targeting"] = _normalize_targeting(df["targeting"])

    # Parse dates
    for col in ["start_date", "end_date"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    return df
