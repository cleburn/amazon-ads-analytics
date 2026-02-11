"""Parse KDP Sales Dashboard exports (CSV or XLSX multi-sheet workbook).

KDP exports as XLSX workbooks with multiple sheets:
  - Summary: Monthly aggregates
  - Combined Sales: All royalties by month
  - eBook Royalty: eBook detail
  - Paperback Royalty: Paperback detail
  - Hardcover Royalty: Hardcover detail
  - Orders Processed: Paperback orders by month
  - eBook Orders Placed: Daily eBook orders
  - KENP Read: Kindle Unlimited page reads

We use "Combined Sales" for royalty data and "eBook Orders Placed" + "Orders Processed"
for unit counts with the best date granularity available.
"""

import pandas as pd


def _clean_currency(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.replace("$", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip()
        .replace("", "0")
        .replace("nan", "0")
        .astype(float)
    )


def load_kdp_report(filepath: str) -> pd.DataFrame:
    """Load and normalize a KDP Sales Dashboard export.

    Handles both:
    - XLSX workbook (multi-sheet, actual KDP format)
    - CSV flat file (template/manual format)

    Returns a DataFrame with columns:
        date, title, author, asin, format, units_sold, net_units_sold, royalty, marketplace
    """
    if filepath.endswith((".xlsx", ".xls")):
        return _load_xlsx_workbook(filepath)
    else:
        return _load_csv(filepath)


def _load_xlsx_workbook(filepath: str) -> pd.DataFrame:
    """Parse the multi-sheet KDP XLSX workbook.

    Combines eBook and Paperback royalty sheets into a unified DataFrame.
    """
    xls = pd.ExcelFile(filepath, engine="openpyxl")
    frames = []

    # eBook Royalty sheet
    if "eBook Royalty" in xls.sheet_names:
        ebook_df = pd.read_excel(xls, sheet_name="eBook Royalty")
        ebook_df = _normalize_royalty_sheet(ebook_df, book_format="ebook")
        frames.append(ebook_df)

    # Paperback Royalty sheet
    if "Paperback Royalty" in xls.sheet_names:
        pb_df = pd.read_excel(xls, sheet_name="Paperback Royalty")
        pb_df = _normalize_royalty_sheet(pb_df, book_format="paperback")
        frames.append(pb_df)

    # Hardcover Royalty sheet
    if "Hardcover Royalty" in xls.sheet_names:
        hc_df = pd.read_excel(xls, sheet_name="Hardcover Royalty")
        if not hc_df.empty:
            hc_df = _normalize_royalty_sheet(hc_df, book_format="hardcover")
            frames.append(hc_df)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)

    # Filter to Amazon.com marketplace
    if "marketplace" in df.columns:
        df = df[df["marketplace"].str.contains("Amazon.com", na=False)].copy()

    return df


def _normalize_royalty_sheet(df: pd.DataFrame, book_format: str) -> pd.DataFrame:
    """Normalize a KDP royalty sheet (eBook, Paperback, or Hardcover)."""
    col_map = {
        "Royalty Date": "date",
        "Order Date": "order_date",
        "Title": "title",
        "Author Name": "author",
        "ASIN": "asin",
        "ASIN/ISBN": "asin",
        "ISBN": "isbn",
        "Marketplace": "marketplace",
        "Royalty Type": "royalty_type",
        "Transaction Type": "transaction_type",
        "Units Sold": "units_sold",
        "Units Refunded": "units_refunded",
        "Net Units Sold": "net_units_sold",
        "Avg. List Price without tax": "avg_list_price",
        "Avg. Offer Price without tax": "avg_offer_price",
        "Avg. Manufacturing Cost": "manufacturing_cost",
        "Avg. Delivery Cost": "delivery_cost",
        "Royalty": "royalty",
        "Currency": "currency",
    }

    df.columns = df.columns.str.strip()
    rename_map = {k: v for k, v in col_map.items() if k in df.columns}
    df = df.rename(columns=rename_map)

    df["format"] = book_format

    # Parse date (KDP uses YYYY-MM format for royalty dates)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], format="mixed", errors="coerce")

    # Clean numeric columns
    for col in ["units_sold", "units_refunded", "net_units_sold"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    for col in ["royalty", "avg_list_price", "avg_offer_price"]:
        if col in df.columns:
            if df[col].dtype == object:
                df[col] = _clean_currency(df[col])
            else:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    return df


def load_kdp_orders(filepath: str) -> pd.DataFrame:
    """Load daily order data from the KDP workbook.

    Uses "eBook Orders Placed" for daily eBook data and
    "Orders Processed" for paperback data (monthly granularity).
    """
    if not filepath.endswith((".xlsx", ".xls")):
        return pd.DataFrame()

    xls = pd.ExcelFile(filepath, engine="openpyxl")
    frames = []

    if "eBook Orders Placed" in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name="eBook Orders Placed")
        df.columns = df.columns.str.strip()
        df = df.rename(columns={
            "Date": "date",
            "Title": "title",
            "Author Name": "author",
            "ASIN": "asin",
            "Marketplace": "marketplace",
            "Paid Units": "paid_units",
            "Free Units": "free_units",
        })
        df["format"] = "ebook"
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        if "marketplace" in df.columns:
            df = df[df["marketplace"].str.contains("Amazon.com", na=False)].copy()
        frames.append(df)

    if "Orders Processed" in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name="Orders Processed")
        df.columns = df.columns.str.strip()
        df = df.rename(columns={
            "Date": "date",
            "Title": "title",
            "Author Name": "author",
            "ASIN": "asin",
            "Marketplace": "marketplace",
            "Paid Units": "paid_units",
            "Free Units": "free_units",
        })
        # Orders Processed includes all formats — these are paperback ASINs
        df["format"] = "paperback"
        df["date"] = pd.to_datetime(df["date"], format="mixed", errors="coerce")
        if "marketplace" in df.columns:
            df = df[df["marketplace"].str.contains("Amazon.com", na=False)].copy()
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


def _load_csv(filepath: str) -> pd.DataFrame:
    """Fallback: load a flat KDP CSV (template format)."""
    col_map = {
        "Date": "date",
        "Title": "title",
        "Author": "author",
        "ASIN": "asin",
        "Marketplace": "marketplace",
        "Royalty Type": "royalty_type",
        "Transaction Type": "transaction_type",
        "Units Sold": "units_sold",
        "Units Returned": "units_refunded",
        "Net Units Sold": "net_units_sold",
        "Currency": "currency",
        "Average List Price": "avg_list_price",
        "Average Offer Price": "avg_offer_price",
        "Royalty": "royalty",
    }

    # Find header row
    header_row = 0
    with open(filepath, "r", encoding="utf-8-sig") as f:
        for i, line in enumerate(f):
            if i >= 10:
                break
            if line.strip().startswith("Date") and "Title" in line:
                header_row = i
                break

    df = pd.read_csv(filepath, skiprows=header_row, encoding="utf-8-sig")
    df.columns = df.columns.str.strip()
    rename_map = {k: v for k, v in col_map.items() if k in df.columns}
    df = df.rename(columns=rename_map)

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    for col in ["royalty", "avg_list_price", "avg_offer_price"]:
        if col in df.columns and df[col].dtype == object:
            df[col] = _clean_currency(df[col])

    for col in ["units_sold", "units_refunded", "net_units_sold"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

    # Infer format from ASIN
    if "format" not in df.columns and "asin" in df.columns:
        df["format"] = df["asin"].apply(
            lambda x: "ebook" if str(x).startswith("B0") else "paperback"
        )

    if "marketplace" in df.columns:
        df = df[df["marketplace"].str.contains("Amazon.com", na=False)].copy()

    return df
