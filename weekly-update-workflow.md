# Weekly Update Workflow

Run every Monday (or whenever you want a fresh snapshot of the prior week).

---

## 1. Pull Fresh Exports

You need **6 files** each week: 1 search term report, 1 KDP report, and 4 targeting reports.

### Amazon Ads — Search Term Report
1. Go to **Amazon Advertising Console** → Reports → Search Term
2. Set the date range covering the week you're reporting on
3. Download the XLSX file(s)

### Amazon Ads — Targeting Reports (4 files)
1. Go to **Amazon Advertising Console** → Campaign Manager
2. For **each campaign**, open the campaign → Targeting tab → Export
3. Download the CSV for each:
   - ASIN Targeting
   - Keyword Targeting
   - Self Targeting
   - Deconstruction Targeting
4. These provide actual bids, Amazon's suggested bid ranges, and per-target state

> **Note:** Targeting reports are lifetime cumulative. The pipeline extracts bid/suggested bid data only — weekly performance comes from the search term report.

### KDP Dashboard Report
1. Go to **KDP Dashboard** → select **This Month** → Download
2. This gives daily granularity for all formats (Kindle + paperback)

### Move Files into the Project

Archive last week's exports, then move new files into `data/raw/`:

```bash
# Archive last week's exports
mv data/raw/* data/archive/

# Move new files in
mv ~/Downloads/* data/raw/
```

> **Archive**: `data/archive/` keeps all past raw exports for potential re-ingestion or Phase 3 training data. The SQLite database stores structured weekly snapshots; the archive preserves the original files.

### Expected Files in data/raw/

| # | File Pattern | Format | Source |
|---|-------------|--------|--------|
| 1 | `Sponsored_Products_Search_term_report*.xlsx` | XLSX | Amazon Ads Console |
| 2 | `KDP_Dashboard-*.xlsx` | XLSX | KDP Dashboard |
| 3-6 | `Sponsored_Products_Target*.csv` | CSV | Amazon Ads Console (1 per campaign) |

---

## 2. Run the Report

```bash
cd ~/repos/amazon-ads-analytics
bash run-report.sh 2026-02-23 --save
```

Replace the date with today's date (the pull date). The report automatically covers the 7 days before it (e.g., `2026-02-23` → reports on Feb 16–22).

- The script auto-discovers all files in `data/raw/` by pattern
- Targeting reports are optional — if absent, bid enrichment is skipped
- `--save` stores the snapshot in SQLite for trend tracking
- The markdown report saves to `reports/week-YYYY-MM-DD.md`

---

## 3. Review

The report prints to Terminal and also saves a markdown file in `reports/`.

**Key things to check each week:**
- **Impressions & Clicks** — primary optimization targets. More exposure = more sales
- **Ad-Influenced ROAS** — the full picture (KDP royalty vs ad spend). Over 1.0x = profitable
- **Bid Recommendations** — three-column comparison:
  - **Current Bid**: your actual bid (from targeting report)
  - **Suggested Bid**: Amazon's recommended median bid
  - **Max Profitable Bid**: calculated ceiling based on conversion data
- **Flags** — high-spend/zero-order targets are candidates for bid reduction or pausing
- **Search Term Drift** — broad match expanding to irrelevant ASINs = wasted spend
- **ASIN Placements** — search terms that are ASINs are resolved to book titles automatically

> **ASIN Resolution**: The tool resolves ASIN search terms to book titles using `data/asin_lookup.json`. Unknown ASINs are scraped from Amazon and cached automatically. Pass `--no-resolve-asins` to disable.

---

## 4. Take Action in Amazon Ads Console

Based on what the report flags:
- **Adjust bids** using Amazon's suggested bid range as primary guidance
- **Pause targets** that have accumulated spend with zero conversions
- **Add negative targets** for drifted search terms burning budget
- **Increase bids** on targets flagged as underserving (too few impressions)
