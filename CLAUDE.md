# CLAUDE.md — Amazon Ads Analytics

## Project Overview

CLI tool for analyzing Amazon Sponsored Products campaigns for Cleburn Walker's 2-book spiritual/consciousness series ("Ascension: Knowing God in You"). Ingests Amazon Ads XLSX exports and KDP sales data, produces weekly performance reports with flags and bid recommendations. Stores historical data in SQLite for trend analysis.

## The Books

- **Book 1**: "Ascension: Knowing God in You: Removing the Veil to Source & Activating the Christos Within"
  - Published March 2024. Kindle $7.99, Paperback $11.99
  - ASINs: B0CW1BMHMZ (Kindle), B0CY8YG9Q1 (Paperback)
  - Had steady organic sales through 2024 (~10-44 units/month), tapered to near-zero from May-Nov 2025
- **Book 2**: "Ascension: Knowing God in You: Book 2: I AM, Unveiled"
  - Published December 2025. Kindle $9.99, Paperback $22.99
  - ASINs: B0G873GXM4 (Kindle), B0G8JJCFP2 (Paperback)

## Sales & Marketing Timeline

Understanding this timeline is critical for interpreting all data:

1. **Mar 2024**: Book 1 launches. Strong initial sales (44 units), gradual decline through 2024
2. **May-Nov 2025**: Dead zone. Near-zero Book 1 sales, Book 2 not yet published
3. **Dec 2025**: 3-part email campaign sent to 460-person list. First real sales push for Book 2. Result: 10 Book 2 + 3 Book 1 units in December
4. **Late Jan 2026**: Book 2 reaches 3 Amazon reviews — minimum threshold to start ads
5. **Jan 26, 2026**: Amazon Sponsored Products campaigns go live ($15/day total budget)
6. **Feb 3, 2026**: Self-targeting campaign added (Book 1 pages → Book 2)

Pre-ad sales are entirely organic/email-driven. Any KDP sales before Jan 26, 2026 have zero ad attribution.

## Campaign Structure

3 campaigns at $15/day total:
- **ASIN Targeting** ($8/day): 12 competitor book ASINs (spiritual/consciousness genre). Expanded match. The Sophia Code paperback dominates impressions (~70-80%)
- **Keyword Targeting** ($5/day): 28 broad-match keywords. Low impressions, early data
- **Self Targeting** ($2/day): Book 1 product pages → Book 2. Currently zero impressions — this is expected behavior, not a bug

All campaign names are prefixed "Ascension Book2 - " in Amazon's system.

## Data Sources & Formats

Amazon exports are **XLSX** (not CSV). KDP exports are multi-sheet **XLSX** workbooks.

### Amazon Ads — Search Term Reports (XLSX)
- Exported from Amazon Advertising console, possibly split across multiple files by date range
- Uses 14-day attribution window (columns: "14 Day Total Sales", "14 Day Total Orders (#)")
- Targeting format: `asin-expanded="0997935502"` (tool normalizes to just the ASIN)
- One row per search term per targeting expression per day
- This is the primary data source — no separate "targeting report" is needed. Per-target metrics are derived by aggregating the search term report.

### Amazon Ads — Campaign Report (CSV)
- Campaign-level summary (one row per campaign). Optional input.
- Has different column names than search term report (e.g., "Campaign name" vs "Campaign Name")

### KDP Sales Dashboard (XLSX Workbook)
- **Lifetime export** — contains full sales history, not just one week
- Multiple sheets: Summary, Combined Sales, eBook Royalty, Paperback Royalty, Orders Processed, eBook Orders Placed, KENP Read
- Royalty sheets use **monthly** date granularity (e.g., "2026-01"), not daily
- eBook Orders Placed has daily granularity but only for ebooks
- The tool auto-detects monthly vs daily granularity and adjusts the reconciliation window accordingly
- Filter to Amazon.com marketplace (international sales exist but are separate)

## Quick Start

```bash
conda activate ascension-ads
pip install -r requirements.txt

# Weekly analysis (multiple search term files supported)
python analyze.py report \
  --week 2026-02-04 \
  --search-terms "data/raw/Sponsored_Products_Search_term_report (1).xlsx" \
  --search-terms "data/raw/Sponsored_Products_Search_term_report.xlsx" \
  --kdp "data/raw/KDP_Orders-823dff75-adfa-4f72-b784-1cd0a206b439.xlsx" \
  --save

# View trends (requires prior --save runs)
python analyze.py trends --metric acos --weeks 8

# Lifetime summary
python analyze.py lifetime
```

## Architecture

```
analyze.py              CLI entry point (Click)
config/campaigns.yaml   Campaign config, book data, timeline milestones
src/ingest/
  search_terms.py       Parse Amazon Search Term Report (CSV or XLSX)
  targeting.py          Parse Campaign Report + build_targeting_from_search_terms()
  kdp.py                Parse KDP multi-sheet XLSX workbook
src/analysis/
  campaign_summary.py   Campaign-level rollup + WoW comparison
  asin_performance.py   ASIN target drilldown + flags
  keyword_performance.py Keyword drilldown + flags
  search_terms.py       Drift detection, broad match expansion tracking
  kdp_reconciliation.py KDP vs ad-attributed reconciliation (handles monthly data)
  bid_recommendations.py Max profitable bid calculator
src/reports/
  terminal.py           Rich console output (tables, panels, color-coded flags)
  markdown.py           Markdown file writer (reports/week-YYYY-MM-DD.md)
src/storage/
  database.py           SQLite schema (6 tables), connection management
  snapshots.py          Save/retrieve weekly snapshots, trend queries, lifetime stats
src/models/             Phase 3 placeholder (Bayesian bid optimizer — not yet built)
```

## Key Design Decisions

- **No separate targeting report needed**: Per-target metrics are derived from search term report via `build_targeting_from_search_terms()`. Amazon's current export format doesn't provide a per-target breakdown as a separate report.
- **Multiple search term files**: CLI accepts `--search-terms` multiple times. Files are concatenated before analysis. Amazon sometimes exports different date ranges as separate files.
- **Bid enrichment from config**: Since per-target bid data isn't in the search term export, bids are mapped from `campaigns.yaml` target list.
- **KDP monthly detection**: Reconciliation auto-detects if KDP dates are monthly (all 1st-of-month) and adjusts the comparison window. Notes in output explain the monthly-vs-weekly approximation.
- **SQLite opt-in**: `--save` flag. Phase 1 works standalone without a database.
- **Analysis modules return dicts + DataFrames**: Decoupled from rendering. Phase 3 optimizer can consume same structures.
- **Column naming**: Internally uses `orders` and `sales` (not `orders_7d`/`sales_7d`) since attribution window varies (14-day in current exports).

## Key Metrics & Formulas

- **ACoS** = spend / sales (target: <50%)
- **ROAS** = sales / spend
- **Max Profitable Bid** = blended_royalty x conversion_rate / target_acos
- **Blended royalty**: $5.00 default (configurable). Rough average across kindle/paperback for both books.

## Flags the Tool Generates

- `high_spend_no_orders`: Target with >$5 spend and 0 orders (warning)
- `underserving`: Target with <10 impressions (info)
- `bid_above_profitable`: Current bid exceeds max profitable bid at target ACoS (warning)
- `bid_below_range`: Current bid is <50% of max profitable bid (info — room to increase)
- `zero_impressions`: Keyword with 0 impressions (info — bid too low)
- `exact_match_drift`: Search term differs from targeting on exact match (warning)
- `broad_match_expansion`: Broad match keyword expanded to unrelated term with spend (info)
- `no_conversions`: Target with clicks but 0 orders (info)
- `no_data`: Target with 0 impressions and 0 clicks (info)

## Phases

- **Phase 1** (done): Weekly report generator. CLI → ingest → analysis → reports.
- **Phase 2** (done): SQLite cumulative tracker. `--save`, `trends`, `lifetime` commands.
- **Phase 3** (future): Bayesian bid optimizer. `src/models/` is the placeholder. Will use `target_metrics` and `bid_recommendations` tables for historical conversion data.

## Development Methodology

**Discuss logic first, confirm data understanding, validate methodology before generating code. Wait for explicit approval before implementation.**

## Git Commit Guidelines

- Focus on what changed and why
- Do NOT include mentions of Claude, AI assistance, or tool credits
- Do NOT include "Co-Authored-By" attributions
