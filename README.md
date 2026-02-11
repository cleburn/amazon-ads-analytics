# Amazon Ads Analytics

CLI tool for analyzing Amazon Sponsored Products campaigns. Ingests Amazon Ads XLSX exports and KDP sales data, produces weekly performance reports with actionable flags and bid recommendations. Stores historical data in SQLite for trend analysis.

Built to manage ad campaigns for [Ascension: Knowing God in You](https://www.amazon.com/dp/B0CW1BMHMZ), a 2-book spiritual/consciousness series.

## What It Does

- **Weekly Reports**: Campaign rollups, per-target drilldowns, search term drift detection, KDP sales reconciliation, and max-profitable-bid calculations
- **ASIN Resolution**: Resolves raw ASIN search terms to book titles so you can see which product pages your ads appeared on
- **Flags & Recommendations**: Automatically identifies high-spend/no-order targets, underserving ASINs, bid misalignment, broad match drift, and attribution gaps
- **Trend Tracking**: SQLite-backed historical snapshots with week-over-week comparisons
- **Dual Output**: Rich terminal tables + Markdown reports for archiving

## Campaign Structure

3 Amazon Sponsored Products campaigns ($15/day total):
- **ASIN Targeting** ($8/day) — 12 competitor book ASINs in the spiritual/consciousness genre
- **Keyword Targeting** ($5/day) — 28 broad-match keywords
- **Self Targeting** ($2/day) — Book 1 product pages → Book 2

## Quick Start

```bash
conda create -n ascension-ads python=3.11
conda activate ascension-ads
pip install -r requirements.txt

# Weekly report (using the wrapper script)
bash run-report.sh 2026-02-04 --save

# Or run directly (supports multiple search term files)
python analyze.py report \
  --week 2026-02-04 \
  --search-terms "data/raw/Sponsored_Products_Search_term_report.xlsx" \
  --search-terms "data/raw/Sponsored_Products_Search_term_report (1).xlsx" \
  --kdp "data/raw/KDP_Dashboard-*.xlsx" \
  --save

# Trends over time (requires prior --save runs)
python analyze.py trends --metric acos --weeks 8

# Lifetime summary
python analyze.py lifetime
```

`run-report.sh` handles conda activation and auto-discovers files in `data/raw/`. See [weekly-update-workflow.md](weekly-update-workflow.md) for the full export-to-report workflow.

## Architecture

```
analyze.py                  CLI entry point (Click)
config/campaigns.yaml       Campaign config, book data, timeline milestones
data/asin_lookup.json       ASIN-to-title mapping for search term display names

src/ingest/
  search_terms.py           Parse Amazon Search Term Report (CSV or XLSX)
  targeting.py              Campaign Report parser + target aggregation from search terms
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
  database.py               SQLite schema (6 tables)
  snapshots.py              Save/retrieve weekly snapshots, trend queries
```

## Key Metrics

| Metric | Formula | Target |
|--------|---------|--------|
| ACoS | spend / sales | < 50% |
| ROAS | sales / spend | > 2.0x |
| Max Profitable Bid | blended_royalty × conversion_rate / target_acos | — |
| Attribution Gap | KDP units − ad-attributed orders | context-dependent |

## Data Sources

- **Amazon Ads Search Term Report** (XLSX) — primary input, one row per search term per target per day, 14-day attribution window
- **Amazon Ads Campaign Report** (CSV) — optional campaign-level summary
- **KDP Dashboard Report** (XLSX) — preferred for weekly analysis; daily granularity for all formats via Combined Sales sheet
- **KDP Orders/Lifetime Report** (XLSX) — monthly granularity; used for historical context. Auto-detected by the tool

- **ASIN Lookup** (`data/asin_lookup.json`) — maps competitor ASINs to book titles. Pre-seeded with the 12 campaign targets. Unknown ASINs encountered in reports are auto-scraped from Amazon and cached here.

Raw data files are gitignored. Place exports in `data/raw/` to run reports.

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
| `no_conversions` | Info | Clicks but 0 orders |

## Project Phases

- **Phase 1** ✓ — Weekly report generator (CLI → ingest → analysis → reports)
- **Phase 2** ✓ — SQLite cumulative tracker (snapshots, trends, lifetime stats)
- **Phase 3** — Bayesian bid optimizer (architecture placeholder in `src/models/`)

## Tech Stack

Python 3.11 · pandas · openpyxl · Click · Rich · SQLite · PyYAML
