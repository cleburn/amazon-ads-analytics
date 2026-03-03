# Amazon Ads Analytics

CLI tool for analyzing Amazon Sponsored Products campaigns. Ingests Amazon Ads XLSX exports and KDP sales data, produces weekly performance reports with actionable flags and bid recommendations. Stores historical data in SQLite for trend analysis.

Built to manage ad campaigns for [Ascension: Knowing God in You](https://a.co/d/043lKRSd), a 2-book spiritual/consciousness series.

## What It Does

- **Weekly Reports**: Campaign rollups, per-target drilldowns, search term drift detection, KDP sales reconciliation, and max-profitable-bid calculations
- **ASIN Resolution**: Resolves raw ASIN search terms to book titles so you can see which product pages your ads appeared on
- **Flags & Recommendations**: Automatically identifies high-spend/no-order targets, underserving ASINs, bid misalignment, broad match drift, and attribution gaps
- **Trend Tracking**: SQLite-backed historical snapshots with week-over-week comparisons
- **Dual Output**: Rich terminal tables + Markdown reports for archiving

## Campaign Structure

4 Amazon Sponsored Products campaigns ($50/day total):
- **ASIN Targeting** ($25/day) — Sophia Code (exact + expanded), 6 other competitors (expanded)
- **Keyword Targeting** ($10/day) — 33 active broad-match keywords
- **Self Targeting** ($3/day) — Book 1 pages → Book 2
- **Deconstruction Targeting** ($12/day) — 13 faith deconstruction/progressive Christianity targets

## Architecture

```
analyze.py                  CLI entry point (Click)
config/campaigns.yaml       Campaign config, book data, timeline milestones
data/asin_lookup.json       ASIN-to-title mapping for search term display names

src/ingest/
  search_terms.py           Parse Amazon Search Term Report (CSV or XLSX)
  targeting.py              Targeting report parser + bid lookup + supplemental targeting deltas
  kdp.py                    Parse KDP multi-sheet XLSX workbook

src/analysis/
  campaign_summary.py       Campaign-level rollup with WoW comparison
  asin_performance.py       ASIN target drilldown + flags
  keyword_performance.py    Keyword drilldown + flags
  search_terms.py           Drift detection, broad match expansion, ASIN resolution
  kdp_reconciliation.py     KDP reconciliation, paired purchase detection, ad-influenced ROAS
  bid_recommendations.py    Max profitable bid calculator

src/utils/
  asin_resolver.py          ASIN-to-title lookup (JSON file + Amazon scraping fallback)

src/reports/
  terminal.py               Rich console output (tables, panels, color-coded flags)
  markdown.py               Markdown file writer

src/storage/
  database.py               SQLite schema (7 tables)
  snapshots.py              Save/retrieve weekly snapshots, targeting lifetime, trend queries
```

## Key Metrics

| Metric | Formula | Target |
|--------|---------|--------|
| ACoS | spend / sales | < 50% |
| ROAS | sales / spend | > 2.0x |
| Max Profitable Bid | blended_royalty × conversion_rate / target_acos | — |
| Attribution Gap | KDP units − ad-attributed orders | context-dependent |

## Data Sources

- **Amazon Ads Search Term Report** (XLSX) — primary weekly performance data, one row per search term per target per day
- **Amazon Ads Targeting Reports** (CSV, 4 per week) — per-campaign exports with actual bids, Amazon's suggested bid ranges, and target state. Lifetime cumulative; bid data extracted for enrichment, full data saved for weekly delta computation
- **KDP Orders Report** (XLSX, preferred) — exported from KDP Reports → Orders with a custom date range. Daily granularity, all formats. Single file covers the full period
- **KDP Dashboard Report** (XLSX, alternative) — exported from KDP Dashboard → "This Month." Same daily data, but limited to current month (may need multiple files for cross-month boundaries)
- **ASIN Lookup** (`data/asin_lookup.json`) — maps competitor ASINs to book titles. Unknown ASINs auto-scraped from Amazon and cached

Raw data files are gitignored. Exports are held in `data/raw/` to run reports, then moved to `data/archive/`

## Flags Generated

| Flag | Severity | Meaning |
|------|----------|---------|
| `high_spend_no_orders` | Warning | Target with >$5 spend and 0 orders |
| `bid_above_profitable` | Warning | Current bid exceeds max profitable bid |
| `exact_match_drift` | Warning | Search term differs from exact-match target |
| `underserving` | Info | Target with <10 impressions |
| `bid_below_range` | Info | Bid is <50% of max profitable (room to increase) |
| `broad_match_expansion` | Info | Broad match expanded to unrelated term |
| `zero_impressions` | Info | Keyword getting 0 impressions |
| `zero_activity` | Info | Configured target absent from search term data |
| `no_conversions` | Info | Clicks but 0 orders |
| `impressions_no_clicks` | Info | Ad showing but not generating clicks |
| `no_data` | Info | No impressions or clicks |

## Project Phases

- **Phase 1** ✓ — Weekly report generator (CLI → ingest → analysis → reports)
- **Phase 2** ✓ — SQLite cumulative tracker (snapshots, trends, lifetime stats)
- **Phase 3** — Bayesian bid optimizer (architecture placeholder in `src/models/`)

## Tech Stack

Python 3.11 · pandas · openpyxl · Click · Rich · SQLite · PyYAML
