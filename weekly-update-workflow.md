# Weekly Update Workflow

Run every Monday (or whenever you want a fresh snapshot of the prior week).

---

## 1. Pull Fresh Exports

### Amazon Ads — Search Term Report
1. Go to **Amazon Advertising Console** → Reports → Search Term
2. Set the date range covering the week you're reporting on
3. Download the XLSX file(s)

### KDP Dashboard Report
1. Go to **KDP Dashboard** → select **This Month** → Download
2. This gives daily granularity for all formats (Kindle + paperback)

### Move Files into the Project
Move downloaded files into `data/raw/`:

```
mv ~/Downloads/Sponsored_Products_Search_term_report*.xlsx data/raw/
mv ~/Downloads/KDP_Dashboard-*.xlsx data/raw/
```

> **Tip:** Before moving new files in, delete or archive the old ones from `data/raw/` so the tool doesn't pick up stale data.

---

## 2. Run the Report

From Terminal, `cd` into the project folder and run:

```
cd ~/repos/amazon-ads-analytics
bash run-report.sh 2026-02-11 --save
```

Replace `2026-02-11` with the Monday of the week you're reporting on.

- The script auto-discovers your search term and KDP files in `data/raw/`
- `--save` stores the snapshot in SQLite for trend tracking (optional but recommended)
- The markdown report saves to `reports/week-YYYY-MM-DD.md`

---

## 3. Review

The report prints to Terminal and also saves a markdown file in `reports/`.

**Key things to check each week:**
- **ACoS** — target is under 50%. Over 100% means you're losing money on attributed sales
- **Ad-Influenced ROAS** — the fuller picture (KDP royalty vs ad spend). Over 1.0x = profitable
- **Flags** — high-spend/zero-order targets are candidates for bid reduction or pausing
- **Bid Recommendations** — if current bid exceeds max profitable bid, lower it
- **Search Term Drift** — broad match expanding to irrelevant ASINs = wasted spend
- **ASIN Placements** — search terms that are ASINs are resolved to book titles automatically. Check that your ads are appearing on relevant competitor books. Any "(unknown)" entries were ASINs that couldn't be looked up — you can manually add them to `data/asin_lookup.json`

> **ASIN Resolution**: The tool resolves ASIN search terms to book titles using `data/asin_lookup.json`. Unknown ASINs are scraped from Amazon and cached automatically. If scraping causes issues, pass `--no-resolve-asins` to disable.

---

## 4. Take Action in Amazon Ads Console

Based on what the report flags:
- **Lower bids** on targets where current bid exceeds max profitable bid
- **Pause targets** that have accumulated spend with zero conversions
- **Add negative targets** for drifted search terms burning budget
- **Increase bids** on targets flagged as underserving (too few impressions)
