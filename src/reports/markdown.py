"""Markdown file writer for weekly reports."""

import os
from datetime import datetime

import pandas as pd


def _fmt_pct(val, decimals=2) -> str:
    if val is None or pd.isna(val):
        return "—"
    return f"{val * 100:.{decimals}f}%"


def _fmt_dollar(val) -> str:
    if val is None or pd.isna(val):
        return "—"
    return f"${val:.2f}"


def _fmt_int(val) -> str:
    if val is None or pd.isna(val):
        return "—"
    return f"{int(val):,}"


def _md_table(headers: list, rows: list) -> str:
    """Build a markdown table from headers and row data."""
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)


def _campaign_summary_section(result: dict) -> str:
    """Generate campaign summary markdown section."""
    df = result["table"]
    headers = ["Campaign", "Spend", "Impr", "Clicks", "CTR", "Avg CPC", "Orders", "Sales", "ACoS", "ROAS"]
    rows = []
    for _, row in df.iterrows():
        roas_val = row.get("roas")
        roas_str = f"{roas_val:.2f}x" if roas_val and pd.notna(roas_val) else "—"
        rows.append([
            row["campaign_name"],
            _fmt_dollar(row["spend"]),
            _fmt_int(row["impressions"]),
            _fmt_int(row["clicks"]),
            _fmt_pct(row["ctr"]),
            _fmt_dollar(row["avg_cpc"]),
            _fmt_int(row["orders"]),
            _fmt_dollar(row["sales"]),
            _fmt_pct(row.get("acos")),
            roas_str,
        ])
    return "## 1. Campaign Summary\n\n" + _md_table(headers, rows)


def _asin_performance_section(result: dict) -> str:
    """Generate ASIN performance markdown section."""
    df = result["table"]
    flags = result["flags"]

    if df.empty:
        return "## 2. ASIN Target Performance\n\nNo ASIN targeting data."

    headers = ["Target", "Impr", "Clicks", "CTR", "CPC", "Spend", "Orders", "Conv Rate"]
    rows = []
    for _, row in df.iterrows():
        title = row.get("target_title", "")
        display = f"{title} ({row['targeting']})" if title else row["targeting"]
        rows.append([
            display,
            _fmt_int(row["impressions"]),
            _fmt_int(row["clicks"]),
            _fmt_pct(row.get("ctr")),
            _fmt_dollar(row.get("cpc")),
            _fmt_dollar(row["spend"]),
            _fmt_int(row["orders"]),
            _fmt_pct(row.get("conversion_rate")),
        ])

    section = "## 2. ASIN Target Performance\n\n" + _md_table(headers, rows)

    if flags:
        section += "\n\n**Flags:**\n"
        for f in flags:
            icon = "!!!" if f["severity"] == "warning" else ">"
            section += f"- {icon} {f['message']}\n"

    zero_activity = result.get("zero_activity_targets", [])
    if zero_activity:
        section += "\n### Targets with Zero Activity\n\n"
        za_headers = ["ASIN", "Title", "Bid"]
        za_rows = []
        for t in zero_activity:
            za_rows.append([t["asin"], t["title"], _fmt_dollar(t["bid"])])
        section += _md_table(za_headers, za_rows) + "\n"

    return section


def _keyword_performance_section(result: dict) -> str:
    """Generate keyword performance markdown section."""
    df = result["table"]
    flags = result["flags"]

    if df.empty:
        return "## 3. Keyword Performance\n\nNo keyword targeting data."

    headers = ["Keyword", "Match", "Impr", "Clicks", "CTR", "CPC", "Spend", "Orders"]
    rows = []
    for _, row in df.iterrows():
        rows.append([
            row["targeting"],
            row.get("match_type", ""),
            _fmt_int(row["impressions"]),
            _fmt_int(row["clicks"]),
            _fmt_pct(row.get("ctr")),
            _fmt_dollar(row.get("cpc")),
            _fmt_dollar(row["spend"]),
            _fmt_int(row["orders"]),
        ])

    section = "## 3. Keyword Performance\n\n" + _md_table(headers, rows)

    if flags:
        section += "\n\n**Flags:**\n"
        for f in flags:
            icon = "!!!" if f["severity"] == "warning" else ">"
            section += f"- {icon} {f['message']}\n"

    return section


def _search_term_section(result: dict) -> str:
    """Generate search term analysis markdown section."""
    summary = result.get("summary", pd.DataFrame())
    drift_flags = result.get("drift_flags", [])
    transition_note = result.get("transition_note", "")

    section = "## 4. Search Term Analysis\n\n"

    if transition_note:
        section += f"> {transition_note}\n\n"

    if drift_flags:
        section += "### Drift Detected\n\n"
        for f in drift_flags:
            icon = "!!!" if f["severity"] == "warning" else ">"
            section += f"- {icon} {f['message']}\n"
        section += "\n"

    if not summary.empty:
        section += "### Top Search Terms (by spend)\n\n"
        headers = ["Search Term", "Impr", "Clicks", "Spend", "Orders"]
        rows = []
        for _, row in summary.head(20).iterrows():
            rows.append([
                str(row["search_term"]),
                _fmt_int(row["impressions"]),
                _fmt_int(row["clicks"]),
                _fmt_dollar(row["spend"]),
                _fmt_int(row["orders"]),
            ])
        section += _md_table(headers, rows)

    return section


def _kdp_section(result: dict) -> str:
    """Generate KDP reconciliation markdown section."""
    totals = result.get("totals", {})
    title_format_breakdown = result.get("title_format_breakdown", pd.DataFrame())
    title_totals = result.get("title_totals", pd.DataFrame())
    gap = result.get("attribution_gap", {})
    paired = result.get("paired_purchases", [])
    ad_influenced = result.get("ad_influenced")

    section = "## 5. KDP Sales Reconciliation\n\n"

    # Title x Format breakdown (preferred) or title-only fallback
    if not title_format_breakdown.empty:
        headers = ["Title", "Format", "Units", "Royalty"]
        rows = []
        for _, row in title_format_breakdown.iterrows():
            rows.append([row["title"], row["format"], _fmt_int(row["units"]), _fmt_dollar(row["royalty"])])
        section += _md_table(headers, rows) + "\n\n"
    elif not title_totals.empty:
        headers = ["Title", "Units", "Royalty"]
        rows = []
        for _, row in title_totals.iterrows():
            rows.append([row["title"], _fmt_int(row["units"]), _fmt_dollar(row["royalty"])])
        section += _md_table(headers, rows) + "\n\n"

    # Paired purchases
    if paired:
        section += "### Paired Purchases Detected\n\n"
        section += "Same-day Book 1 + Book 2 purchases (likely ad-driven):\n\n"
        for p in paired:
            section += f"- **{p['date']}**: {p['details']}\n"
        section += "\n"

    # Attribution gap
    section += "### Attribution Gap\n\n"
    section += f"- **KDP Total Units**: {totals.get('kdp_units', 0)}\n"
    section += f"- **Ad-Attributed Orders**: {totals.get('ad_attributed_orders', 0)}\n"
    section += f"- **Unattributed Sales**: {totals.get('attribution_gap', 0)} ({totals.get('attribution_gap_pct', 0):.1f}%)\n"
    section += f"- **KDP Royalty**: {_fmt_dollar(totals.get('kdp_royalty', 0))}\n"

    if gap.get("note"):
        section += f"\n> {gap['note']}\n"

    # Ad-influenced analysis
    if ad_influenced:
        inf = ad_influenced
        spend = inf.get("ad_spend", 0)

        section += "\n### Ad-Influenced Analysis\n\n"
        section += f"Since ads started ({inf.get('ads_start', 'N/A')}):\n\n"
        section += f"- **Total KDP units** (all books/formats): {inf.get('post_ad_units', 0)}\n"
        section += f"- **Total KDP royalty**: {_fmt_dollar(inf.get('post_ad_royalty', 0))}\n"
        section += f"- **Total ad spend**: {_fmt_dollar(spend)}\n"

        attr_roas = inf.get("attributed_roas")
        inf_roas = inf.get("influenced_roas")
        section += f"- **Amazon-Attributed ROAS**: {f'{attr_roas:.2f}x' if attr_roas else '—'}\n"
        section += f"- **Ad-Influenced ROAS**: {f'{inf_roas:.2f}x' if inf_roas else '—'} (KDP royalty / ad spend)\n"

        breakdown = inf.get("post_ad_breakdown", [])
        if breakdown:
            section += "\n**Post-Ad Sales Breakdown:**\n\n"
            headers = ["Title", "Format", "Units", "Royalty"]
            rows = []
            for item in breakdown:
                rows.append([item["title"], item["format"], _fmt_int(item["units"]), _fmt_dollar(item["royalty"])])
            section += _md_table(headers, rows) + "\n"

        inf_note = inf.get("note", "")
        if inf_note:
            section += f"\n> {inf_note}\n"

    return section


def _bid_section(result: dict) -> str:
    """Generate bid recommendations markdown section."""
    df = result["table"]
    flags = result["flags"]

    if df.empty:
        return "## 6. Bid Recommendations\n\nNo bid recommendation data."

    headers = ["Target", "Campaign", "Clicks", "Orders", "Conv Rate", "Current Bid", "Max Bid"]
    rows = []
    for _, row in df.iterrows():
        rows.append([
            row["targeting"],
            row.get("campaign_name", ""),
            _fmt_int(row["clicks"]),
            _fmt_int(row["orders"]),
            _fmt_pct(row.get("conversion_rate")),
            _fmt_dollar(row.get("current_bid")),
            _fmt_dollar(row.get("max_profitable_bid")),
        ])

    section = "## 6. Bid Recommendations\n\n" + _md_table(headers, rows)

    if flags:
        section += "\n\n**Flags:**\n"
        for f in flags:
            icon = "!!!" if f["severity"] == "warning" else ">"
            section += f"- {icon} {f['message']}\n"

    return section


def _action_items_section(all_flags: list) -> str:
    """Generate consolidated action items section."""
    if not all_flags:
        return "## Action Items\n\nNo action items — all targets performing within thresholds."

    warnings = [f for f in all_flags if f.get("severity") == "warning"]
    infos = [f for f in all_flags if f.get("severity") == "info"]

    section = "## Action Items\n\n"
    if warnings:
        section += "### Warnings\n\n"
        for f in warnings:
            section += f"- {f['message']}\n"
        section += "\n"

    if infos:
        section += "### Info\n\n"
        for f in infos:
            section += f"- {f['message']}\n"

    return section


def write_weekly_report(
    week: str,
    campaign_summary: dict,
    asin_performance: dict,
    keyword_performance: dict,
    search_term_analysis: dict,
    kdp_reconciliation: dict,
    bid_recommendations: dict,
    output_dir: str = "reports",
) -> str:
    """Write the complete weekly report as a markdown file.

    Returns the path to the written file.
    """
    os.makedirs(output_dir, exist_ok=True)

    filename = f"week-{week}.md"
    filepath = os.path.join(output_dir, filename)

    # Front matter
    lines = [
        f"# Weekly Ad Report — Week of {week}",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    # Total spend/orders from campaign summary
    summary_table = campaign_summary.get("table", pd.DataFrame())
    if not summary_table.empty:
        total_spend = summary_table["spend"].sum()
        total_orders = summary_table["orders"].sum()
        lines.append(f"**Total Spend**: {_fmt_dollar(total_spend)} | **Total Orders**: {_fmt_int(total_orders)}")
        lines.append("")

    lines.append("---\n")

    # Sections
    lines.append(_campaign_summary_section(campaign_summary))
    lines.append("\n---\n")
    lines.append(_asin_performance_section(asin_performance))
    lines.append("\n---\n")
    lines.append(_keyword_performance_section(keyword_performance))
    lines.append("\n---\n")
    lines.append(_search_term_section(search_term_analysis))
    lines.append("\n---\n")
    lines.append(_kdp_section(kdp_reconciliation))
    lines.append("\n---\n")
    lines.append(_bid_section(bid_recommendations))
    lines.append("\n---\n")

    # Action items
    all_flags = (
        asin_performance.get("flags", [])
        + keyword_performance.get("flags", [])
        + search_term_analysis.get("drift_flags", [])
        + bid_recommendations.get("flags", [])
    )
    lines.append(_action_items_section(all_flags))

    with open(filepath, "w") as f:
        f.write("\n".join(lines))

    return filepath
