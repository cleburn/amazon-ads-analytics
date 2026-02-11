"""KDP sales reconciliation against ad-attributed orders."""

import pandas as pd


def reconcile_kdp_sales(
    kdp_df: pd.DataFrame,
    campaign_summary: dict,
    week_start: str,
    week_end: str,
    kdp_orders_df: pd.DataFrame = None,
    config: dict = None,
) -> dict:
    """Reconcile KDP sales data against Amazon ad-attributed orders.

    Compares ground-truth KDP sales with the attributed orders from ad
    campaigns to calculate the attribution gap. Also detects paired
    purchases and estimates ad-influenced sales across all formats.

    Args:
        kdp_df: Normalized KDP royalty DataFrame.
        campaign_summary: Output from generate_campaign_summary().
        week_start: Week start date string (YYYY-MM-DD).
        week_end: Week end date string (YYYY-MM-DD).
        kdp_orders_df: Daily order data from load_kdp_orders() (optional).
        config: Campaign config dict with timeline and book data (optional).

    Returns:
        dict with reconciliation results including attribution gap,
        title/format breakdowns, paired purchases, and ad-influenced analysis.
    """
    df = kdp_df.copy()

    empty_result = {
        "daily_breakdown": pd.DataFrame(),
        "title_format_breakdown": pd.DataFrame(),
        "title_totals": pd.DataFrame(),
        "format_totals": pd.DataFrame(),
        "granularity": "daily",
        "totals": {
            "kdp_units": 0,
            "kdp_royalty": 0.0,
            "ad_attributed_orders": 0,
            "ad_attributed_sales": 0.0,
            "attribution_gap": 0,
            "attribution_gap_pct": 0.0,
        },
        "attribution_gap": {},
        "paired_purchases": [],
        "ad_influenced": None,
    }

    if df.empty:
        return empty_result

    start = pd.to_datetime(week_start)
    end = pd.to_datetime(week_end)
    granularity = "daily"

    # Filter to relevant time window
    if "date" in df.columns:
        dates = df["date"].dropna()
        if not dates.empty and (dates.dt.day == 1).all():
            granularity = "monthly"
            target_months = set()
            target_months.add(start.to_period("M"))
            target_months.add(end.to_period("M"))
            df = df[df["date"].dt.to_period("M").isin(target_months)].copy()
        else:
            df = df[(df["date"] >= start) & (df["date"] <= end)].copy()

    units_col = "net_units_sold" if "net_units_sold" in df.columns else "units_sold"

    # --- Title x Format breakdown ---
    title_format_breakdown = pd.DataFrame()
    if not df.empty and units_col in df.columns and "format" in df.columns:
        title_format_breakdown = (
            df.groupby(["title", "format"])
            .agg(
                units=(units_col, "sum"),
                royalty=("royalty", "sum") if "royalty" in df.columns else (units_col, "count"),
            )
            .reset_index()
            .sort_values(["title", "format"])
        )

    # --- Daily breakdown ---
    group_cols = ["title", "format"]
    if "date" in df.columns and not df.empty:
        group_cols = ["date"] + group_cols

    daily_breakdown = pd.DataFrame()
    if not df.empty and units_col in df.columns:
        daily_breakdown = (
            df.groupby([c for c in group_cols if c in df.columns])
            .agg(
                units=(units_col, "sum"),
                royalty=("royalty", "sum") if "royalty" in df.columns else (units_col, "count"),
            )
            .reset_index()
        )
        if "date" in daily_breakdown.columns:
            daily_breakdown = daily_breakdown.sort_values(["date", "title"])

    # --- Totals ---
    total_kdp_units = int(df[units_col].sum()) if units_col in df.columns and not df.empty else 0
    total_kdp_royalty = float(df["royalty"].sum()) if "royalty" in df.columns and not df.empty else 0.0

    # Ad-attributed orders and sales from campaign summary
    summary_table = campaign_summary.get("table", pd.DataFrame())
    total_ad_orders = 0
    total_ad_sales = 0.0
    total_ad_spend = 0.0
    if not summary_table.empty:
        if "orders" in summary_table.columns:
            total_ad_orders = int(summary_table["orders"].sum())
        if "sales" in summary_table.columns:
            total_ad_sales = float(summary_table["sales"].sum())
        if "spend" in summary_table.columns:
            total_ad_spend = float(summary_table["spend"].sum())

    # Attribution gap
    gap = total_kdp_units - total_ad_orders
    gap_pct = (gap / total_kdp_units * 100) if total_kdp_units > 0 else 0

    # --- Per-title breakdown ---
    title_totals = pd.DataFrame()
    if not df.empty and units_col in df.columns:
        title_totals = (
            df.groupby("title")
            .agg(
                units=(units_col, "sum"),
                royalty=("royalty", "sum") if "royalty" in df.columns else (units_col, "count"),
            )
            .reset_index()
        )

    # --- Per-format breakdown ---
    format_totals = pd.DataFrame()
    if not df.empty and "format" in df.columns:
        format_totals = (
            df.groupby("format")
            .agg(
                units=(units_col, "sum"),
                royalty=("royalty", "sum") if "royalty" in df.columns else (units_col, "count"),
            )
            .reset_index()
        )

    # --- Paired purchase detection ---
    paired_purchases = _detect_paired_purchases(kdp_orders_df, config)

    # --- Ad-influenced analysis ---
    ad_influenced = _estimate_ad_influenced(
        kdp_df=kdp_df,
        kdp_orders_df=kdp_orders_df,
        config=config,
        total_ad_spend=total_ad_spend,
        total_ad_orders=total_ad_orders,
        total_ad_sales=total_ad_sales,
    )

    # --- Build the comparison note ---
    if granularity == "monthly":
        month_names = sorted(set(
            d.strftime("%B %Y") for d in df["date"].dropna()
        )) if "date" in df.columns and not df.empty else []
        period_str = ", ".join(month_names) if month_names else "the matching month"
        note = (
            f"KDP data is monthly granularity ({period_str}). "
            "Weekly ad-attributed orders compared against full-month KDP sales — "
            "gap may be larger than actual weekly difference. "
            "Amazon only attributes sales of the exact advertised ASIN (Book 2 Kindle). "
            "Book 1 sales and paperback sales driven by ads are not attributed. "
            "KDP report is ground truth."
        )
    else:
        note = (
            "Amazon only attributes sales of the exact advertised ASIN (Book 2 Kindle). "
            "Book 1 sales, paperback sales, and read-through purchases driven by ads "
            "are not attributed. KDP report is ground truth."
        )

    return {
        "daily_breakdown": daily_breakdown,
        "title_format_breakdown": title_format_breakdown,
        "title_totals": title_totals,
        "format_totals": format_totals,
        "granularity": granularity,
        "totals": {
            "kdp_units": total_kdp_units,
            "kdp_royalty": total_kdp_royalty,
            "ad_attributed_orders": total_ad_orders,
            "ad_attributed_sales": total_ad_sales,
            "attribution_gap": int(gap),
            "attribution_gap_pct": float(gap_pct),
        },
        "attribution_gap": {
            "kdp_total_units": total_kdp_units,
            "ad_attributed_orders": total_ad_orders,
            "unattributed_sales": int(gap),
            "unattributed_pct": float(gap_pct),
            "note": note,
        },
        "paired_purchases": paired_purchases,
        "ad_influenced": ad_influenced,
    }


def _detect_paired_purchases(
    kdp_orders_df: pd.DataFrame,
    config: dict,
) -> list:
    """Detect same-day purchases of both Book 1 and Book 2.

    Uses the eBook Orders Placed data (daily granularity) to find dates
    where both books were ordered — a strong signal of ad-driven behavior
    since the ads target Book 2 and the buyer also grabs Book 1.

    Returns a list of dicts with date and details for each paired purchase.
    """
    if kdp_orders_df is None or kdp_orders_df.empty or config is None:
        return []

    # Get book ASINs from config
    books = config.get("books", {})
    book1_asins = set()
    book2_asins = set()
    for key, book in books.items():
        asins = {book.get("asin_kindle", ""), book.get("asin_paperback", "")} - {""}
        if "book_1" in key or "Book 1" in book.get("short_title", ""):
            book1_asins.update(asins)
        elif "book_2" in key or "Book 2" in book.get("short_title", ""):
            book2_asins.update(asins)

    if not book1_asins or not book2_asins:
        return []

    df = kdp_orders_df.copy()
    if "date" not in df.columns or "asin" not in df.columns:
        return []

    # Only look at rows with daily dates (not monthly)
    df = df.dropna(subset=["date"])
    if df.empty:
        return []

    # Filter to rows that are actually daily (not first-of-month monthly)
    daily_mask = ~((df["date"].dt.day == 1) & (df["date"].dt.is_month_start))
    # If all dates are 1st, they might still be daily — check if there are different days
    if not daily_mask.any():
        daily_mask = pd.Series(True, index=df.index)
    df = df[daily_mask].copy()

    # Check for daily dates only (skip monthly-granularity data)
    if df.empty:
        return []

    paired = []
    for date, group in df.groupby("date"):
        asins_on_date = set(group["asin"].astype(str))
        has_book1 = bool(asins_on_date & book1_asins)
        has_book2 = bool(asins_on_date & book2_asins)

        if has_book1 and has_book2:
            titles = group[["asin", "title"]].drop_duplicates()
            detail_parts = []
            for _, row in titles.iterrows():
                asin = str(row["asin"])
                title = row.get("title", asin)
                if asin in book1_asins:
                    detail_parts.append(f"Book 1: {title}")
                elif asin in book2_asins:
                    detail_parts.append(f"Book 2: {title}")
            paired.append({
                "date": date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date),
                "details": " + ".join(sorted(detail_parts)),
            })

    return sorted(paired, key=lambda x: x["date"])


def _estimate_ad_influenced(
    kdp_df: pd.DataFrame,
    kdp_orders_df: pd.DataFrame,
    config: dict,
    total_ad_spend: float,
    total_ad_orders: int,
    total_ad_sales: float,
) -> dict:
    """Estimate total ad-influenced sales across all books and formats.

    Amazon only attributes sales of the exact advertised ASIN (Book 2 Kindle).
    But ads also drive:
    - Book 2 Paperback purchases (visitor picks a different format)
    - Book 1 purchases (halo/read-through effect)
    - Paired purchases (both books bought together)

    Uses the ads start date from config to separate pre-ad from post-ad sales.
    """
    if config is None:
        return None

    timeline = config.get("timeline", {})
    ads_start_str = timeline.get("amazon_ads_start")
    if not ads_start_str:
        return None

    ads_start = pd.to_datetime(ads_start_str)

    # --- Collect all post-ad KDP royalty data ---
    post_ad_units = 0
    post_ad_royalty = 0.0
    pre_ad_units = 0
    pre_ad_royalty = 0.0
    post_ad_breakdown = []

    if not kdp_df.empty and "date" in kdp_df.columns:
        df = kdp_df.copy()
        units_col = "net_units_sold" if "net_units_sold" in df.columns else "units_sold"

        # For monthly data, consider a month "post-ad" if it contains or follows the ad start
        dates = df["date"].dropna()
        is_monthly = not dates.empty and (dates.dt.day == 1).all()

        if is_monthly:
            ads_start_period = ads_start.to_period("M")
            post_mask = df["date"].dt.to_period("M") >= ads_start_period
        else:
            post_mask = df["date"] >= ads_start

        post_df = df[post_mask]
        pre_df = df[~post_mask]

        if units_col in post_df.columns:
            post_ad_units = int(post_df[units_col].sum())
            pre_ad_units = int(pre_df[units_col].sum()) if not pre_df.empty else 0
        if "royalty" in post_df.columns:
            post_ad_royalty = float(post_df["royalty"].sum())
            pre_ad_royalty = float(pre_df["royalty"].sum()) if not pre_df.empty else 0

        # Breakdown by title x format for post-ad period
        if not post_df.empty and units_col in post_df.columns and "format" in post_df.columns:
            breakdown = (
                post_df.groupby(["title", "format"])
                .agg(
                    units=(units_col, "sum"),
                    royalty=("royalty", "sum") if "royalty" in post_df.columns else (units_col, "count"),
                )
                .reset_index()
                .sort_values(["title", "format"])
            )
            post_ad_breakdown = breakdown.to_dict("records")

    # --- Also count post-ad ebook orders from daily data ---
    post_ad_ebook_units = 0
    if kdp_orders_df is not None and not kdp_orders_df.empty:
        orders = kdp_orders_df.copy()
        if "date" in orders.columns:
            orders_post = orders[orders["date"] >= ads_start]
            if "paid_units" in orders_post.columns:
                post_ad_ebook_units = int(orders_post["paid_units"].sum())

    # --- Calculate influenced ROAS ---
    influenced_roas = None
    if total_ad_spend > 0 and post_ad_royalty > 0:
        influenced_roas = post_ad_royalty / total_ad_spend

    attributed_roas = None
    if total_ad_spend > 0 and total_ad_sales > 0:
        attributed_roas = total_ad_sales / total_ad_spend

    # Determine the note about data granularity
    note_parts = []
    if kdp_df is not None and not kdp_df.empty and "date" in kdp_df.columns:
        dates = kdp_df["date"].dropna()
        if not dates.empty and (dates.dt.day == 1).all():
            note_parts.append(
                "KDP royalty data is monthly. Post-ad totals include the full month "
                "of the ad start date — some pre-ad sales may be included."
            )
    note_parts.append(
        "Ad-influenced includes all KDP sales (both books, all formats) since "
        f"ads started ({ads_start_str}). Amazon only attributes Book 2 Kindle sales."
    )

    return {
        "ads_start": ads_start_str,
        "post_ad_units": post_ad_units,
        "post_ad_royalty": post_ad_royalty,
        "post_ad_ebook_daily_units": post_ad_ebook_units,
        "post_ad_breakdown": post_ad_breakdown,
        "pre_ad_units": pre_ad_units,
        "pre_ad_royalty": pre_ad_royalty,
        "ad_spend": total_ad_spend,
        "ad_attributed_orders": total_ad_orders,
        "ad_attributed_sales": total_ad_sales,
        "attributed_roas": attributed_roas,
        "influenced_roas": influenced_roas,
        "note": " ".join(note_parts),
    }
