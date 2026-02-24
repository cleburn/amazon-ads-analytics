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
7. **Feb 16, 2026**: Major campaign restructure — paused underperforming ASIN/keyword targets, added Deconstruction Targeting campaign, raised budgets to $40/day total
8. **Feb 23, 2026**: Shifted ASIN and Deconstruction campaigns from exact to expanded match (exact match on cold targets produced zero impressions). Reactivated 4 keywords. Raised ASIN Targeting to $20/day ($45 total). Integrated per-campaign targeting reports into pipeline; removed bid fields from config.

Pre-ad sales are entirely organic/email-driven. Any KDP sales before Jan 26, 2026 have zero ad attribution.

**Strategic frame**: Campaigns are optimized for maximum impressions and clicks, not direct conversions. ~80% of KDP sales are unattributed by Amazon (wrong format, Book 1 halo, paired purchases). Ad-Influenced ROAS (using all KDP royalty) is the real profitability metric.

## Campaign Structure

4 campaigns at $45/day total (restructured Feb 23, 2026):
- **ASIN Targeting** ($20/day): Mixed match types. Sophia Code PB/Kindle run on both exact + expanded. 6 other targets (Becoming Supernatural, Power of Now, Four Agreements, Autobiography of a Yogi) on expanded only. 14 paused targets. Sophia Code PB dominates impressions (~70-80%)
- **Keyword Targeting** ($10/day): 33 active broad-match keywords + 3 paused. Bids set to Amazon suggested bids
- **Self Targeting** ($3/day): Book 1 product pages → Book 2. 2 exact match targets active, 2 expanded match paused
- **Deconstruction Targeting** ($12/day): 13 competitor book ASINs in faith deconstruction/progressive Christianity space, all on expanded match. Authors: Richard Rohr, Rob Bell, Rachel Held Evans, Barbara Brown Taylor, Peter Enns, Cynthia Bourgeault

All campaign names are prefixed "Ascension Book2 - " in Amazon's system.

### Config Schema Notes
- `campaigns.yaml` uses `targets` for active targets and `paused_targets` for paused ones. Analysis code only reads `targets`, so paused entries won't trigger false "zero activity" flags.
- **No bid fields in config.** Bids are sourced from weekly targeting report CSV exports. The config defines structure only (which targets, match types, active/paused).
- Keyword campaign uses `keywords` / `paused_keywords` lists. Keyword bids come from targeting reports, not config.
- ASIN targets include per-target `match_type` (exact/expanded) since the ASIN Targeting campaign uses mixed match types.

## Data Sources & Formats

6 files are ingested weekly: 1-2 search term reports (XLSX), 4 targeting reports (CSV), 1 KDP report (XLSX).

### Amazon Ads — Search Term Reports (XLSX)
- Exported from Amazon Advertising console, possibly split across multiple files by date range
- Uses 14-day attribution window (columns: "14 Day Total Sales", "14 Day Total Orders (#)")
- Targeting format: `asin-expanded="0997935502"` (tool normalizes to just the ASIN)
- One row per search term per targeting expression per day
- Primary source for **weekly performance metrics** per target

### Amazon Ads — Targeting Reports (CSV, 1 per campaign)
- Exported from Amazon Advertising console → Campaign → Targeting tab → Export
- 4 files per week (one per campaign). Filename pattern: `Sponsored_Products_Target*.csv`
- **Lifetime cumulative** performance (not weekly) — only bid data is extracted
- Two column variants: "Categories & products" (ASIN campaigns) or "Keyword" (keyword campaign)
- Key columns not in search term report:
  - **Bid (USD)**: actual current bid per target
  - **Suggested bid (low/median/high)(USD)**: Amazon's recommended bid range
  - **State**: ENABLED/PAUSED per target
  - **Top-of-search impression share**: competitive position metric
- The tool extracts bid + suggested bid data, enriches the targeting DataFrame, and stores in SQLite for Phase 3

### KDP Reports (XLSX Workbooks)

There are **two types** of KDP exports, both XLSX with the same sheet names but different granularity:

#### KDP Dashboard Report (preferred for weekly analysis)
- Exported from KDP Dashboard → Download. Date options: Today, Yesterday, **This Month** (use this one)
- Filename pattern: `KDP_Dashboard-*.xlsx`
- **Combined Sales** sheet: **DAILY** dates, ALL formats, with royalty — the primary data source
- **Orders Processed** sheet: **DAILY** dates, all formats, with ASIN
- **Paperback Royalty** sheet: **DAILY** royalty date + order date
- **eBook Orders Placed** sheet: **DAILY** ebook orders (last 90 days only)
- The tool reads Combined Sales first when daily data is detected
- Only covers the selected period (e.g., current month), not lifetime

#### KDP Orders Report (for historical/lifetime context)
- Exported from KDP Reports → Orders. Can select Lifetime or custom date range
- Filename pattern: `KDP_Orders-*.xlsx`
- **Combined Sales** sheet: **MONTHLY** dates (YYYY-MM)
- **Royalty sheets**: **MONTHLY**
- **eBook Orders Placed** sheet: **DAILY** (only ebooks, last 90 days)
- The tool falls back to individual royalty sheets when Combined Sales is monthly
- Contains full sales history — useful for ad-influenced analysis across the entire ad period

#### Auto-Detection Logic (`src/ingest/kdp.py`)
The tool auto-detects which report type by checking dates in Combined Sales:
- If dates have varying days → Dashboard report → use Combined Sales (daily, all formats)
- If all dates are 1st-of-month → Orders/Lifetime report → fall back to individual royalty sheets

#### Key Sheets Reference
| Sheet | Dashboard Report | Orders/Lifetime Report | What It Contains |
|-------|-----------------|----------------------|------------------|
| Combined Sales | DAILY, all formats | MONTHLY, all formats | Royalty date, title, ASIN/ISBN, units, royalty. Format inferred from Transaction Type: "Standard" = ebook, "Standard - Paperback" = paperback |
| Orders Processed | DAILY | MONTHLY | Date, title, ASIN, paid/free units. ASIN distinguishes format (B0... = ebook, 979... = paperback) |
| Paperback Royalty | DAILY (has Order Date) | MONTHLY | Royalty date, order date, ISBN, ASIN, units, royalty |
| eBook Orders Placed | DAILY | DAILY | Only ebooks, last 90 days. Used for paired purchase detection |
| eBook Royalty | May be empty | MONTHLY | Ebook royalties |

- Filter to Amazon.com marketplace using exact match (international sales on Amazon.com.au, .com.br, etc. are excluded)

### Attribution Gap & Ad-Influenced Analysis

Amazon ads target **Book 2 Kindle only**. Amazon only attributes a sale when the exact advertised ASIN is purchased after an ad click. But ads also drive:
- **Book 2 Paperback** — visitor sees Kindle ad, buys paperback instead
- **Book 1 (any format)** — halo/read-through effect from discovering Book 2
- **Paired purchases** — both books bought together after an ad click

The tool detects paired purchases from daily KDP data (same-day Book 1 + Book 2 orders) and calculates an "Ad-Influenced ROAS" using all KDP royalty since the ad start date, not just Amazon's attributed sales.

## Quick Start

```bash
conda activate ascension-ads
pip install -r requirements.txt

# Weekly report (wrapper script handles conda + file discovery)
# --week is the PULL DATE (the day you export data).
# The report covers the 7 days before it: pull_date-7 to pull_date-1.
# Example: 2026-02-16 → reports on Feb 9–15
bash run-report.sh 2026-02-23 --save

# Or run directly
python analyze.py report \
  --week 2026-02-23 \
  --search-terms "data/raw/Sponsored_Products_Search_term_report_2-23-26.xlsx" \
  --kdp "data/raw/KDP_Dashboard_2-23-26.xlsx" \
  --targeting data/raw/Sponsored_Products_Target*.csv \
  --save

# View trends (requires prior --save runs)
python analyze.py trends --metric acos --weeks 8

# Lifetime summary
python analyze.py lifetime
```

## Weekly Export Workflow

See [weekly-update-workflow.md](weekly-update-workflow.md) for the full step-by-step process.

Summary: Download 6 files (1-2 search term XLSX, 4 targeting CSVs, 1 KDP XLSX), archive old exports from `data/raw/` to `data/archive/`, move new files into `data/raw/`, then run `bash run-report.sh <pull-date> --save`.

## Architecture

```
analyze.py              CLI entry point (Click)
config/campaigns.yaml   Campaign config, book data, timeline milestones
data/asin_lookup.json   ASIN-to-title mapping for search term display names
src/ingest/
  search_terms.py       Parse Amazon Search Term Report (CSV or XLSX)
  targeting.py          Targeting report parser + bid lookup + build_targeting_from_search_terms()
  kdp.py                Parse KDP multi-sheet XLSX (auto-detects Dashboard vs Lifetime)
src/analysis/
  campaign_summary.py   Campaign-level rollup + WoW comparison
  asin_performance.py   ASIN target drilldown + flags
  keyword_performance.py Keyword drilldown + flags
  search_terms.py       Drift detection, broad match expansion, ASIN resolution
  kdp_reconciliation.py KDP reconciliation + paired purchase detection + ad-influenced ROAS
  bid_recommendations.py Max profitable bid calculator
src/utils/
  asin_resolver.py      ASIN-to-title lookup (JSON file + Amazon scraping fallback)
src/reports/
  terminal.py           Rich console output (tables, panels, color-coded flags)
  markdown.py           Markdown file writer (reports/week-YYYY-MM-DD.md)
src/storage/
  database.py           SQLite schema (6 tables), connection management
  snapshots.py          Save/retrieve weekly snapshots, trend queries, lifetime stats
src/models/             Phase 3 placeholder (Bayesian bid optimizer — not yet built)
```

## Key Design Decisions

- **Per-target metrics from search terms**: Weekly per-target metrics are derived from the search term report via `build_targeting_from_search_terms()`. Targeting reports supplement with bid/suggested bid data only (their performance metrics are lifetime cumulative, not weekly).
- **Multiple search term files**: CLI accepts `--search-terms` multiple times. Files are concatenated and then deduplicated on (campaign_name, targeting_raw, search_term, start_date, end_date) to prevent double-counting from overlapping exports. Uses `targeting_raw` (not normalized) so exact and expanded rows for the same ASIN are preserved.
- **Bid enrichment from targeting reports**: CLI accepts `--targeting` multiple times (4 per-campaign CSVs). `load_targeting_reports()` parses them, `build_bid_lookup()` creates a `{targeting → bid/suggested_bids}` lookup. ENABLED rows preferred; if multiple ENABLED rows for same target (e.g. Sophia Code with exact+expanded), the one with more impressions wins. Enrichment is optional — pipeline runs without targeting reports, just without bid data.
- **KDP auto-detection**: `load_kdp_report()` checks Combined Sales dates — daily = Dashboard report (use it directly), monthly = Lifetime report (fall back to individual royalty sheets). Format inferred from Transaction Type field.
- **Paired purchase detection**: `_detect_paired_purchases()` uses daily eBook Orders Placed data to find same-day Book 1 + Book 2 orders within the report's week window — strong signal of ad-driven halo sales.
- **Ad-influenced ROAS**: Compares total KDP royalty since ad start date against cumulative ad spend (sourced from saved snapshots + current week). On first run without prior snapshots, falls back to current week's spend only. Requires `--save` runs to build accurate cumulative spend history.
- **SQLite opt-in**: `--save` flag. Phase 1 works standalone without a database.
- **Analysis modules return dicts + DataFrames**: Decoupled from rendering. All analysis modules guard against empty/missing-column inputs with early returns. Phase 3 optimizer can consume same structures.
- **Drift flag persistence**: `save_weekly_snapshot` accepts `drift_flags` from search term analysis and marks matching rows with `is_drift=1` in the `search_term_metrics` table.
- **Column naming**: Internally uses `orders` and `sales` (not `orders_7d`/`sales_7d`) since attribution window varies (14-day in current exports).
- **Targeting report CSV format**: Two column variants — ASIN campaigns have "Categories & products" (with `asin="..."` / `asin-expanded="..."` values), keyword campaign has "Keyword". Match type is derived from the prefix for ASINs (exact/expanded) or the "Target match type" column for keywords. The CSVs don't contain campaign names — target identity is unambiguous across campaigns (each ASIN/keyword appears in only one campaign).
- **ASIN-to-title resolution**: Search terms that are ASINs (B0xx or 10-digit ISBNs) are resolved to book titles via `data/asin_lookup.json`. Unknown ASINs are scraped from Amazon product pages and cached to the JSON file. Controlled by `--resolve-asins/--no-resolve-asins` flag (on by default).
- **Pull-date convention**: `--week` is the pull date (day you export data). The report looks back 7 days: `week_start = pull_date - 7`, `week_end = pull_date - 1`. The pull date is used for filenames and display titles; the lookback window is passed to KDP reconciliation and snapshot storage.
- **KDP date filtering in snapshots**: `save_weekly_snapshot` filters KDP rows to `[week_start, week_end]` before storing to `kdp_daily_sales`. Since KDP "This Month" exports contain the full month, without filtering the same sales would be duplicated across snapshots. Boundary days (e.g., Feb 9 in both a Feb 4–10 and Feb 9–15 snapshot) may still appear twice — this is expected and harmless since analysis queries filter by date range, not by summing the raw table.

## Key Metrics & Formulas

- **ACoS** = spend / sales (target: <50%)
- **ROAS** = sales / spend
- **Max Profitable Bid** = blended_royalty x conversion_rate / target_acos
- **Blended royalty**: $5.00 default (configurable). Rough average across kindle/paperback for both books.

## Flags the Tool Generates

- `high_spend_no_orders`: Target with >$5 spend and 0 orders (warning)
- `underserving`: Target with <10 impressions (info)
- `bid_above_profitable`: Current bid exceeds max profitable bid at target ACoS (warning). Requires targeting report data for current bid.
- `bid_below_range`: Current bid is <50% of max profitable bid (info — room to increase). Requires targeting report data.
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
