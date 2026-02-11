"""Rich terminal output for weekly reports."""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

import pandas as pd

console = Console()


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


def _delta_str(val, fmt_func, invert=False) -> str:
    """Format a delta value with +/- prefix and color hint."""
    if val is None or pd.isna(val):
        return ""
    prefix = "+" if val > 0 else ""
    return f" ({prefix}{fmt_func(val)})"


def render_campaign_summary(result: dict) -> None:
    """Render campaign summary table to terminal."""
    df = result["table"]
    wow = result["wow_available"]

    table = Table(title="Campaign Summary", show_lines=True)
    table.add_column("Campaign", style="bold")
    table.add_column("Spend", justify="right")
    table.add_column("Impressions", justify="right")
    table.add_column("Clicks", justify="right")
    table.add_column("CTR", justify="right")
    table.add_column("Avg CPC", justify="right")
    table.add_column("Orders", justify="right")
    table.add_column("Sales", justify="right")
    table.add_column("ACoS", justify="right")
    table.add_column("ROAS", justify="right")

    for _, row in df.iterrows():
        spend_str = _fmt_dollar(row["spend"])
        if wow and "spend_delta" in row.index:
            spend_str += _delta_str(row["spend_delta"], _fmt_dollar)

        ctr_str = _fmt_pct(row["ctr"])
        if wow and "ctr_delta" in row.index:
            ctr_str += _delta_str(row["ctr_delta"], _fmt_pct)

        acos_str = _fmt_pct(row.get("acos"))
        orders_str = _fmt_int(row["orders"])
        if wow and "orders_delta" in row.index:
            orders_str += _delta_str(row["orders_delta"], _fmt_int)

        roas_val = row.get("roas")
        roas_str = f"{roas_val:.2f}x" if roas_val and pd.notna(roas_val) else "—"

        table.add_row(
            row["campaign_name"],
            spend_str,
            _fmt_int(row["impressions"]),
            _fmt_int(row["clicks"]),
            ctr_str,
            _fmt_dollar(row["avg_cpc"]),
            orders_str,
            _fmt_dollar(row["sales"]),
            acos_str,
            roas_str,
        )

    console.print(table)
    console.print()


def render_asin_performance(result: dict) -> None:
    """Render ASIN target performance table to terminal."""
    df = result["table"]
    flags = result["flags"]

    if df.empty:
        console.print("[dim]No ASIN targeting data.[/dim]")
        return

    table = Table(title="ASIN Target Performance", show_lines=True)
    table.add_column("Target", style="bold", max_width=35)
    table.add_column("Impr", justify="right")
    table.add_column("Clicks", justify="right")
    table.add_column("CTR", justify="right")
    table.add_column("CPC", justify="right")
    table.add_column("Spend", justify="right")
    table.add_column("Orders", justify="right")
    table.add_column("Conv Rate", justify="right")
    table.add_column("Flags", max_width=20)

    # Build flag lookup
    flag_map = {}
    for f in flags:
        target = f["target"]
        flag_map.setdefault(target, []).append(f)

    for _, row in df.iterrows():
        target = row["targeting"]
        title = row.get("target_title", "")
        display = f"{title}\n{target}" if title else target

        target_flags = flag_map.get(target, [])
        flag_text = Text()
        for f in target_flags:
            color = "red" if f["severity"] == "warning" else "yellow"
            flag_text.append(f"[{f['type']}]", style=color)

        table.add_row(
            display,
            _fmt_int(row["impressions"]),
            _fmt_int(row["clicks"]),
            _fmt_pct(row.get("ctr")),
            _fmt_dollar(row.get("cpc")),
            _fmt_dollar(row["spend"]),
            _fmt_int(row["orders"]),
            _fmt_pct(row.get("conversion_rate")),
            flag_text,
        )

    console.print(table)
    console.print()


def render_keyword_performance(result: dict) -> None:
    """Render keyword performance table to terminal."""
    df = result["table"]
    flags = result["flags"]

    if df.empty:
        console.print("[dim]No keyword targeting data.[/dim]")
        return

    table = Table(title="Keyword Performance", show_lines=True)
    table.add_column("Keyword", style="bold", max_width=35)
    table.add_column("Match", justify="center")
    table.add_column("Impr", justify="right")
    table.add_column("Clicks", justify="right")
    table.add_column("CTR", justify="right")
    table.add_column("CPC", justify="right")
    table.add_column("Spend", justify="right")
    table.add_column("Orders", justify="right")
    table.add_column("Flags", max_width=20)

    flag_map = {}
    for f in flags:
        flag_map.setdefault(f["target"], []).append(f)

    for _, row in df.iterrows():
        keyword = row["targeting"]
        target_flags = flag_map.get(keyword, [])
        flag_text = Text()
        for f in target_flags:
            color = "red" if f["severity"] == "warning" else "yellow"
            flag_text.append(f"[{f['type']}]", style=color)

        table.add_row(
            keyword,
            row.get("match_type", ""),
            _fmt_int(row["impressions"]),
            _fmt_int(row["clicks"]),
            _fmt_pct(row.get("ctr")),
            _fmt_dollar(row.get("cpc")),
            _fmt_dollar(row["spend"]),
            _fmt_int(row["orders"]),
            flag_text,
        )

    console.print(table)
    console.print()


def render_search_term_analysis(result: dict) -> None:
    """Render search term analysis to terminal."""
    summary = result.get("summary", pd.DataFrame())
    drift_flags = result.get("drift_flags", [])
    transition_note = result.get("transition_note", "")

    if transition_note:
        console.print(Panel(transition_note, title="Context", style="dim"))

    # Drift flags
    if drift_flags:
        console.print(Panel("[bold red]Drift Detected[/bold red]", expand=False))
        for f in drift_flags:
            color = "red" if f["severity"] == "warning" else "yellow"
            console.print(f"  [{color}]{f['message']}[/{color}]")
        console.print()

    # Top search terms
    if not summary.empty:
        table = Table(title="Top Search Terms (by spend)", show_lines=True)
        table.add_column("Search Term", style="bold", max_width=40)
        table.add_column("Impr", justify="right")
        table.add_column("Clicks", justify="right")
        table.add_column("Spend", justify="right")
        table.add_column("Orders", justify="right")

        for _, row in summary.head(20).iterrows():
            table.add_row(
                str(row["search_term"]),
                _fmt_int(row["impressions"]),
                _fmt_int(row["clicks"]),
                _fmt_dollar(row["spend"]),
                _fmt_int(row["orders"]),
            )

        console.print(table)
        console.print()


def render_kdp_reconciliation(result: dict) -> None:
    """Render KDP sales reconciliation to terminal."""
    totals = result.get("totals", {})
    title_format_breakdown = result.get("title_format_breakdown", pd.DataFrame())
    title_totals = result.get("title_totals", pd.DataFrame())
    gap = result.get("attribution_gap", {})
    paired = result.get("paired_purchases", [])
    ad_influenced = result.get("ad_influenced")

    # Title x Format breakdown (preferred) or title-only fallback
    if not title_format_breakdown.empty:
        table = Table(title="KDP Sales by Title & Format", show_lines=True)
        table.add_column("Title", style="bold", max_width=50)
        table.add_column("Format", justify="center")
        table.add_column("Units", justify="right")
        table.add_column("Royalty", justify="right")

        for _, row in title_format_breakdown.iterrows():
            table.add_row(
                row["title"],
                row["format"],
                _fmt_int(row["units"]),
                _fmt_dollar(row["royalty"]),
            )

        console.print(table)
    elif not title_totals.empty:
        table = Table(title="KDP Sales by Title", show_lines=True)
        table.add_column("Title", style="bold")
        table.add_column("Units", justify="right")
        table.add_column("Royalty", justify="right")

        for _, row in title_totals.iterrows():
            table.add_row(
                row["title"],
                _fmt_int(row["units"]),
                _fmt_dollar(row["royalty"]),
            )

        console.print(table)

    # Paired purchases
    if paired:
        paired_text = "[bold]Same-day Book 1 + Book 2 purchases (likely ad-driven):[/bold]\n"
        for p in paired:
            paired_text += f"  {p['date']}: {p['details']}\n"
        console.print(Panel(paired_text.rstrip(), title="Paired Purchases Detected"))

    # Attribution gap panel
    gap_text = (
        f"KDP Total Units: {totals.get('kdp_units', 0)}\n"
        f"Ad-Attributed Orders: {totals.get('ad_attributed_orders', 0)}\n"
        f"Unattributed Sales: {totals.get('attribution_gap', 0)} "
        f"({totals.get('attribution_gap_pct', 0):.1f}%)\n"
        f"KDP Royalty: {_fmt_dollar(totals.get('kdp_royalty', 0))}"
    )
    note = gap.get("note", "")
    if note:
        gap_text += f"\n\n[dim]{note}[/dim]"
    console.print(Panel(gap_text, title="Attribution Gap"))

    # Ad-influenced analysis
    if ad_influenced:
        inf = ad_influenced
        spend = inf.get("ad_spend", 0)

        inf_text = f"[bold]Since ads started ({inf.get('ads_start', 'N/A')}):[/bold]\n"
        inf_text += f"  Total KDP units (all books/formats): {inf.get('post_ad_units', 0)}\n"
        inf_text += f"  Total KDP royalty: {_fmt_dollar(inf.get('post_ad_royalty', 0))}\n"
        inf_text += f"  Total ad spend: {_fmt_dollar(spend)}\n\n"

        attr_roas = inf.get("attributed_roas")
        inf_roas = inf.get("influenced_roas")
        inf_text += f"  Amazon-Attributed ROAS:  {f'{attr_roas:.2f}x' if attr_roas else '—'}\n"
        inf_text += f"  Ad-Influenced ROAS:      {f'{inf_roas:.2f}x' if inf_roas else '—'}"
        inf_text += "  [dim](KDP royalty / ad spend)[/dim]\n"

        # Post-ad breakdown
        breakdown = inf.get("post_ad_breakdown", [])
        if breakdown:
            inf_text += "\n  [bold]Post-Ad Sales Breakdown:[/bold]\n"
            for item in breakdown:
                title_short = item["title"][:45]
                inf_text += (
                    f"    {title_short} ({item['format']}): "
                    f"{item['units']} units, {_fmt_dollar(item['royalty'])}\n"
                )

        inf_note = inf.get("note", "")
        if inf_note:
            inf_text += f"\n[dim]{inf_note}[/dim]"

        console.print(Panel(inf_text.rstrip(), title="Ad-Influenced Analysis"))

    console.print()


def render_bid_recommendations(result: dict) -> None:
    """Render bid recommendations to terminal."""
    df = result["table"]
    flags = result["flags"]

    if df.empty:
        console.print("[dim]No bid recommendation data.[/dim]")
        return

    table = Table(title="Bid Recommendations", show_lines=True)
    table.add_column("Target", style="bold", max_width=35)
    table.add_column("Campaign", max_width=20)
    table.add_column("Clicks", justify="right")
    table.add_column("Orders", justify="right")
    table.add_column("Conv Rate", justify="right")
    table.add_column("Current Bid", justify="right")
    table.add_column("Max Bid", justify="right")
    table.add_column("Flag")

    flag_map = {}
    for f in flags:
        flag_map.setdefault(f["target"], []).append(f)

    for _, row in df.iterrows():
        target = row["targeting"]
        target_flags = flag_map.get(target, [])
        flag_text = Text()
        for f in target_flags:
            color = "red" if f["severity"] == "warning" else "yellow"
            flag_text.append(f"[{f['type']}] ", style=color)

        table.add_row(
            target,
            row.get("campaign_name", ""),
            _fmt_int(row["clicks"]),
            _fmt_int(row["orders"]),
            _fmt_pct(row.get("conversion_rate")),
            _fmt_dollar(row.get("current_bid")),
            _fmt_dollar(row.get("max_profitable_bid")),
            flag_text,
        )

    console.print(table)
    console.print()


def render_action_items(all_flags: list) -> None:
    """Render consolidated action items panel."""
    if not all_flags:
        console.print(Panel("[green]No action items — all targets performing within thresholds.[/green]"))
        return

    warnings = [f for f in all_flags if f.get("severity") == "warning"]
    infos = [f for f in all_flags if f.get("severity") == "info"]

    text_parts = []
    if warnings:
        text_parts.append("[bold red]Warnings:[/bold red]")
        for f in warnings:
            text_parts.append(f"  - {f['message']}")

    if infos:
        text_parts.append("[bold yellow]Info:[/bold yellow]")
        for f in infos:
            text_parts.append(f"  - {f['message']}")

    console.print(Panel("\n".join(text_parts), title="Action Items"))


def render_full_report(
    week: str,
    campaign_summary: dict,
    asin_performance: dict,
    keyword_performance: dict,
    search_term_analysis: dict,
    kdp_reconciliation: dict,
    bid_recommendations: dict,
) -> None:
    """Render the complete weekly report to terminal."""
    console.print()
    console.print(
        Panel(f"[bold]Weekly Ad Report — Week of {week}[/bold]", style="blue")
    )
    console.print()

    render_campaign_summary(campaign_summary)
    render_asin_performance(asin_performance)
    render_keyword_performance(keyword_performance)
    render_search_term_analysis(search_term_analysis)
    render_kdp_reconciliation(kdp_reconciliation)
    render_bid_recommendations(bid_recommendations)

    # Collect all flags for action items
    all_flags = (
        asin_performance.get("flags", [])
        + keyword_performance.get("flags", [])
        + search_term_analysis.get("drift_flags", [])
        + bid_recommendations.get("flags", [])
    )
    render_action_items(all_flags)
