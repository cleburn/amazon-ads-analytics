"""Ascension Ads Analytics — CLI entry point."""

import os
import sys
from datetime import datetime, timedelta

import click
import yaml

from src.ingest.search_terms import load_search_term_report
from src.ingest.targeting import load_campaign_report, build_targeting_from_search_terms
from src.ingest.kdp import load_kdp_report
from src.analysis.campaign_summary import generate_campaign_summary
from src.analysis.asin_performance import analyze_asin_targets
from src.analysis.keyword_performance import analyze_keywords
from src.analysis.search_terms import analyze_search_terms
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
@click.option("--week", required=True, help="Week start date (YYYY-MM-DD)")
@click.option("--search-terms", "search_terms_paths", required=True, multiple=True,
              type=click.Path(exists=True),
              help="Path to Search Term Report (CSV or XLSX). Can specify multiple.")
@click.option("--campaign", "campaign_path", default=None,
              type=click.Path(exists=True),
              help="Path to Campaign Report CSV (optional, for campaign-level totals)")
@click.option("--kdp", "kdp_path", required=True,
              type=click.Path(exists=True), help="Path to KDP Sales export (CSV or XLSX)")
@click.option("--config", "config_path", default="config/campaigns.yaml",
              help="Path to campaign config YAML")
@click.option("--save", is_flag=True, default=False,
              help="Save snapshot to SQLite database (Phase 2)")
@click.option("--no-terminal", is_flag=True, default=False,
              help="Skip terminal output (only write markdown)")
@click.option("--output-dir", default="reports",
              help="Directory for markdown reports")
def report(week, search_terms_paths, campaign_path, kdp_path, config_path,
           save, no_terminal, output_dir):
    """Generate a weekly performance report from CSV/XLSX exports."""
    config = load_config(config_path)

    # Calculate week end (7 days from start)
    week_start = datetime.strptime(week, "%Y-%m-%d")
    week_end = week_start + timedelta(days=6)
    week_end_str = week_end.strftime("%Y-%m-%d")

    click.echo(f"Loading data for week of {week}...")

    # Ingest search term reports (may be multiple files for different date ranges)
    import pandas as pd
    search_term_frames = []
    for path in search_terms_paths:
        df = load_search_term_report(path)
        search_term_frames.append(df)
        click.echo(f"  Search terms ({os.path.basename(path)}): {len(df)} rows")

    search_term_df = pd.concat(search_term_frames, ignore_index=True) if search_term_frames else pd.DataFrame()
    click.echo(f"  Search terms total: {len(search_term_df)} rows")

    # Build per-target data by aggregating search terms
    # (Amazon doesn't provide a separate targeting report in the current export format)
    targeting_df = build_targeting_from_search_terms(search_term_df)
    click.echo(f"  Targeting (derived from search terms): {len(targeting_df)} targets")

    # Enrich targeting_df with bid data from config
    target_bids = {}
    for key, campaign in config.get("campaigns", {}).items():
        for target in campaign.get("targets", []):
            target_bids[target["asin"]] = target.get("bid")
    if not targeting_df.empty:
        targeting_df["bid"] = targeting_df["targeting"].map(target_bids)

    # Load campaign report if provided (for reference/validation)
    if campaign_path:
        campaign_report = load_campaign_report(campaign_path)
        click.echo(f"  Campaign report: {len(campaign_report)} campaigns")

    # KDP sales
    kdp_df = load_kdp_report(kdp_path)
    click.echo(f"  KDP sales: {len(kdp_df)} rows")

    # Try to load prior week for WoW comparison
    prior_week_df = None
    if save:
        try:
            from src.storage.snapshots import get_prior_week_summary
            prior_week_df = get_prior_week_summary(week)
        except Exception:
            pass

    # Analysis
    click.echo("Running analysis...")
    campaign_summary = generate_campaign_summary(targeting_df, prior_week_df)
    asin_performance = analyze_asin_targets(targeting_df, config)
    keyword_performance = analyze_keywords(targeting_df, config)
    search_term_analysis = analyze_search_terms(search_term_df, config)
    kdp_recon = reconcile_kdp_sales(kdp_df, campaign_summary, week, week_end_str)
    bid_recs = recommend_bids(targeting_df, config)

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
    )
    click.echo(f"Markdown report written to: {md_path}")

    # Save to SQLite (Phase 2)
    if save:
        try:
            from src.storage.snapshots import save_weekly_snapshot
            save_weekly_snapshot(
                week_start=week,
                week_end=week_end_str,
                targeting_df=targeting_df,
                search_term_df=search_term_df,
                kdp_df=kdp_df,
                campaign_summary=campaign_summary,
                bid_recommendations=bid_recs,
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
                    if metric in ("ctr", "acos"):
                        values.append(f"{val * 100:.2f}%" if val else "—")
                    elif metric in ("spend",):
                        values.append(f"${val:.2f}" if val else "—")
                    else:
                        values.append(str(int(val)) if val else "—")
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
