"""Ascension Ads Analytics — CLI entry point."""

import os
import sys
from datetime import datetime, timedelta

import click
import pandas as pd
import yaml

from src.ingest.search_terms import load_search_term_report
from src.ingest.targeting import build_targeting_from_search_terms, load_targeting_reports, build_bid_lookup
from src.ingest.kdp import load_kdp_report, load_kdp_orders
from src.analysis.campaign_summary import generate_campaign_summary
from src.analysis.asin_performance import analyze_asin_targets
from src.analysis.keyword_performance import analyze_keywords
from src.analysis.search_terms import analyze_search_terms, apply_asin_resolution
from src.analysis.kdp_reconciliation import reconcile_kdp_sales
from src.analysis.bid_recommendations import recommend_bids
from src.reports.terminal import render_full_report
from src.reports.markdown import write_weekly_report


def load_config(config_path: str = "config/campaigns.yaml") -> dict:
    """Load campaign configuration from YAML file."""
    # Resolve relative to the script's directory
    if not os.path.isabs(config_path):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(base_dir, config_path)

    with open(config_path, "r") as f:
        return yaml.safe_load(f)


@click.group()
def cli():
    """Ascension Ads Analytics — Amazon Ads performance analysis tool."""
    pass


@cli.command()
@click.option("--week", required=True, help="Pull date (YYYY-MM-DD). Report covers the 7 days before this date.")
@click.option("--search-terms", "search_terms_paths", required=True, multiple=True,
              type=click.Path(exists=True),
              help="Path to Search Term Report (CSV or XLSX). Can specify multiple.")
@click.option("--kdp", "kdp_paths", required=True, multiple=True,
              type=click.Path(exists=True),
              help="Path to KDP Sales export (CSV or XLSX). Can specify multiple.")
@click.option("--targeting", "targeting_paths", multiple=True,
              type=click.Path(exists=True),
              help="Path to Targeting Report CSV (one per campaign). Can specify multiple.")
@click.option("--config", "config_path", default="config/campaigns.yaml",
              help="Path to campaign config YAML")
@click.option("--save", is_flag=True, default=False,
              help="Save snapshot to SQLite database (Phase 2)")
@click.option("--resolve-asins/--no-resolve-asins", default=True,
              help="Resolve ASIN search terms to book titles (default: on)")
@click.option("--no-terminal", is_flag=True, default=False,
              help="Skip terminal output (only write markdown)")
@click.option("--output-dir", default="reports",
              help="Directory for markdown reports")
def report(week, search_terms_paths, kdp_paths, targeting_paths,
           config_path, resolve_asins, save, no_terminal, output_dir):
    """Generate a weekly performance report from CSV/XLSX exports."""
    config = load_config(config_path)

    # --week is the pull date; report covers the 7 days before it
    pull_date = datetime.strptime(week, "%Y-%m-%d")
    week_end = pull_date - timedelta(days=1)
    week_start = pull_date - timedelta(days=7)
    week_start_str = week_start.strftime("%Y-%m-%d")
    week_end_str = week_end.strftime("%Y-%m-%d")

    click.echo(f"Pull date: {week} — reporting period: {week_start_str} to {week_end_str}")

    # Ingest search term reports (may be multiple files for different date ranges)
    search_term_frames = []
    for path in search_terms_paths:
        df = load_search_term_report(path)
        search_term_frames.append(df)
        click.echo(f"  Search terms ({os.path.basename(path)}): {len(df)} rows")

    search_term_df = pd.concat(search_term_frames, ignore_index=True) if search_term_frames else pd.DataFrame()

    # Deduplicate overlapping exports (same row from multiple files)
    if not search_term_df.empty:
        dedup_cols = ["campaign_name", "targeting_raw", "search_term"]
        for col in ["start_date", "end_date"]:
            if col in search_term_df.columns:
                dedup_cols.append(col)
        before = len(search_term_df)
        search_term_df = search_term_df.drop_duplicates(subset=dedup_cols, keep="first")
        dupes = before - len(search_term_df)
        if dupes:
            click.echo(f"  Deduplicated: removed {dupes} overlapping rows")

    click.echo(f"  Search terms total: {len(search_term_df)} rows")

    # Build per-target data by aggregating search terms
    # (Amazon doesn't provide a separate targeting report in the current export format)
    targeting_df = build_targeting_from_search_terms(search_term_df)
    click.echo(f"  Targeting (derived from search terms): {len(targeting_df)} targets")

    # Enrich targeting_df with bid + suggested bid data from targeting reports
    bid_lookup = {}
    if targeting_paths:
        targeting_report_df = load_targeting_reports(list(targeting_paths))
        click.echo(f"  Targeting reports: {len(targeting_report_df)} rows from {len(targeting_paths)} files")
        bid_lookup = build_bid_lookup(targeting_report_df)
        if not targeting_df.empty and bid_lookup:
            targeting_df["bid"] = targeting_df["targeting"].map(
                lambda t: bid_lookup.get(t, {}).get("bid"))
            targeting_df["suggested_bid_low"] = targeting_df["targeting"].map(
                lambda t: bid_lookup.get(t, {}).get("suggested_bid_low"))
            targeting_df["suggested_bid_median"] = targeting_df["targeting"].map(
                lambda t: bid_lookup.get(t, {}).get("suggested_bid_median"))
            targeting_df["suggested_bid_high"] = targeting_df["targeting"].map(
                lambda t: bid_lookup.get(t, {}).get("suggested_bid_high"))
            enriched = targeting_df["bid"].notna().sum()
            click.echo(f"  Bid enrichment: {enriched}/{len(targeting_df)} targets matched")

    # KDP sales (may be multiple files for cross-month boundaries)
    kdp_frames = []
    kdp_orders_frames = []
    for path in kdp_paths:
        df = load_kdp_report(path)
        kdp_frames.append(df)
        click.echo(f"  KDP sales ({os.path.basename(path)}): {len(df)} rows")
        odf = load_kdp_orders(path)
        if not odf.empty:
            kdp_orders_frames.append(odf)
            click.echo(f"  KDP daily orders ({os.path.basename(path)}): {len(odf)} rows")

    kdp_df = pd.concat(kdp_frames, ignore_index=True) if kdp_frames else pd.DataFrame()
    kdp_orders_df = pd.concat(kdp_orders_frames, ignore_index=True) if kdp_orders_frames else pd.DataFrame()

    # Deduplicate overlapping KDP exports (same row from multiple files)
    if not kdp_df.empty:
        kdp_dedup_cols = [c for c in ["date", "title", "format", "marketplace", "units_sold", "royalty"]
                          if c in kdp_df.columns]
        if kdp_dedup_cols:
            before = len(kdp_df)
            kdp_df = kdp_df.drop_duplicates(subset=kdp_dedup_cols, keep="first")
            kdp_dupes = before - len(kdp_df)
            if kdp_dupes:
                click.echo(f"  KDP deduplicated: removed {kdp_dupes} overlapping rows")

    if not kdp_orders_df.empty:
        orders_dedup_cols = [c for c in ["date", "title", "format", "asin"]
                             if c in kdp_orders_df.columns]
        if orders_dedup_cols:
            before = len(kdp_orders_df)
            kdp_orders_df = kdp_orders_df.drop_duplicates(subset=orders_dedup_cols, keep="first")
            orders_dupes = before - len(kdp_orders_df)
            if orders_dupes:
                click.echo(f"  KDP orders deduplicated: removed {orders_dupes} overlapping rows")

    click.echo(f"  KDP sales total: {len(kdp_df)} rows")

    # Try to load prior week for WoW comparison
    prior_week_df = None
    if save:
        try:
            from src.storage.snapshots import get_prior_week_summary
            prior_week_df = get_prior_week_summary(week_start_str)
        except ImportError:
            pass
        except Exception as e:
            click.echo(f"  Warning: Could not load prior week for WoW comparison: {e}")

    # Try to load cumulative ad spend from prior snapshots (for ad-influenced ROAS)
    cumulative_prior_spend = None
    try:
        from src.storage.snapshots import get_cumulative_ad_spend
        cumulative_prior_spend = get_cumulative_ad_spend(current_week_start=week_start_str)
    except ImportError:
        pass
    except Exception as e:
        click.echo(f"  Warning: Could not load cumulative ad spend: {e}")

    # Analysis
    click.echo("Running analysis...")
    campaign_summary = generate_campaign_summary(targeting_df, prior_week_df)
    asin_performance = analyze_asin_targets(targeting_df, config, bid_lookup=bid_lookup)
    keyword_performance = analyze_keywords(targeting_df, config)
    search_term_analysis = analyze_search_terms(search_term_df, config)
    kdp_recon = reconcile_kdp_sales(
        kdp_df, campaign_summary, week_start_str, week_end_str,
        kdp_orders_df=kdp_orders_df, config=config,
        cumulative_prior_spend=cumulative_prior_spend,
    )
    bid_recs = recommend_bids(targeting_df, config)

    # Resolve ASIN search terms to book titles
    if resolve_asins:
        from src.utils.asin_resolver import resolve_asins as _resolve_asins

        summary = search_term_analysis.get("summary", pd.DataFrame())
        if not summary.empty:
            terms = summary["search_term"].tolist()
            asin_map = _resolve_asins(terms, scrape=True)
            if asin_map:
                search_term_analysis = apply_asin_resolution(
                    search_term_analysis, asin_map
                )
                resolved_count = len(asin_map)
                click.echo(f"  Resolved {resolved_count} ASIN search terms to titles")

    # Terminal output
    if not no_terminal:
        render_full_report(
            week=week,
            campaign_summary=campaign_summary,
            asin_performance=asin_performance,
            keyword_performance=keyword_performance,
            search_term_analysis=search_term_analysis,
            kdp_reconciliation=kdp_recon,
            bid_recommendations=bid_recs,
            week_start=week_start_str,
            week_end=week_end_str,
        )

    # Markdown output
    md_path = write_weekly_report(
        week=week,
        campaign_summary=campaign_summary,
        asin_performance=asin_performance,
        keyword_performance=keyword_performance,
        search_term_analysis=search_term_analysis,
        kdp_reconciliation=kdp_recon,
        bid_recommendations=bid_recs,
        output_dir=output_dir,
        week_start=week_start_str,
        week_end=week_end_str,
    )
    click.echo(f"Markdown report written to: {md_path}")

    # Save to SQLite (Phase 2)
    if save:
        try:
            from src.storage.snapshots import save_weekly_snapshot
            save_weekly_snapshot(
                week_start=week_start_str,
                week_end=week_end_str,
                targeting_df=targeting_df,
                search_term_df=search_term_df,
                kdp_df=kdp_df,
                campaign_summary=campaign_summary,
                bid_recommendations=bid_recs,
                drift_flags=search_term_analysis.get("drift_flags", []),
            )
            click.echo("Snapshot saved to database.")
        except ImportError:
            click.echo("Warning: Storage module not available. Skipping database save.")
        except Exception as e:
            click.echo(f"Warning: Failed to save snapshot: {e}")


@cli.command()
@click.option("--metric", required=True,
              type=click.Choice(["spend", "impressions", "clicks", "ctr", "acos", "orders", "roas"]),
              help="Metric to track over time")
@click.option("--campaign", default=None, help="Filter to specific campaign name")
@click.option("--weeks", default=8, type=int, help="Number of weeks to show")
def trends(metric, campaign, weeks):
    """Show metric trends over time (requires saved snapshots)."""
    try:
        from src.storage.snapshots import get_trend_data
        from rich.console import Console
        from rich.table import Table

        console = Console()
        data = get_trend_data(metric=metric, campaign=campaign, weeks=weeks)

        if data.empty:
            click.echo("No historical data found. Run 'report --save' first.")
            return

        table = Table(title=f"{metric.upper()} Trend — Last {weeks} Weeks")
        table.add_column("Week", style="bold")
        if campaign:
            table.add_column(campaign)
        else:
            for col in data.columns:
                if col != "week_start":
                    table.add_column(col)

        for _, row in data.iterrows():
            values = [row["week_start"]]
            for col in data.columns:
                if col != "week_start":
                    val = row[col]
                    if val is None or pd.isna(val):
                        values.append("—")
                    elif metric in ("ctr", "acos"):
                        values.append(f"{val * 100:.2f}%")
                    elif metric in ("spend",):
                        values.append(f"${val:.2f}")
                    elif metric in ("roas",):
                        values.append(f"{val:.2f}x")
                    else:
                        values.append(str(int(val)))
            table.add_row(*values)

        console.print(table)

    except ImportError:
        click.echo("Storage module not available. Build Phase 2 first.")


@cli.command()
def lifetime():
    """Show lifetime summary across all saved snapshots."""
    try:
        from src.storage.snapshots import get_lifetime_summary
        from rich.console import Console
        from rich.panel import Panel

        console = Console()
        summary = get_lifetime_summary()

        if not summary:
            click.echo("No historical data found. Run 'report --save' first.")
            return

        text = (
            f"Weeks tracked: {summary['weeks_tracked']}\n"
            f"Total spend: ${summary['total_spend']:.2f}\n"
            f"Total orders: {summary['total_orders']}\n"
            f"Total sales: ${summary['total_sales']:.2f}\n"
            f"Overall ACoS: {summary['overall_acos'] * 100:.1f}%\n"
            f"Overall ROAS: {summary['overall_roas']:.2f}x\n"
            f"Avg weekly spend: ${summary['avg_weekly_spend']:.2f}\n"
        )
        console.print(Panel(text, title="Lifetime Campaign Summary"))

    except ImportError:
        click.echo("Storage module not available. Build Phase 2 first.")


if __name__ == "__main__":
    cli()
