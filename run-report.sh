#!/bin/bash
# Usage: ./run-report.sh <pull-date> [--save]
# The pull date is the day you export data. The report covers the 7 days before it.
#   Example: ./run-report.sh 2026-02-23 --save  →  reports on Feb 16–22

set -e

WEEK="$1"
if [ -z "$WEEK" ]; then
    echo "Usage: ./run-report.sh <pull-date> [--save]"
    echo "  pull-date: the day you export data (report covers 7 days before it)"
    echo "  Example: ./run-report.sh 2026-02-23 --save"
    exit 1
fi

SAVE_FLAG=""
if [ "$2" = "--save" ]; then
    SAVE_FLAG="--save"
fi

# Activate conda environment
source /opt/homebrew/anaconda3/etc/profile.d/conda.sh
conda activate ascension-ads

# Auto-discover files in data/raw/
# 1. Search term reports (XLSX, required)
SEARCH_TERM_ARGS=""
for f in data/raw/Sponsored_Products_Search_term_report*.xlsx; do
    [ -f "$f" ] && SEARCH_TERM_ARGS="$SEARCH_TERM_ARGS --search-terms \"$f\""
done

# 2. KDP reports (XLSX, required — may be multiple for cross-month boundaries)
KDP_ARGS=""
for f in data/raw/KDP_*.xlsx; do
    [ -f "$f" ] && KDP_ARGS="$KDP_ARGS --kdp \"$f\""
done

# 3. Targeting reports (CSV, optional — 1 per campaign)
TARGETING_ARGS=""
for f in data/raw/Sponsored_Products_Target*.csv; do
    [ -f "$f" ] && TARGETING_ARGS="$TARGETING_ARGS --targeting \"$f\""
done

if [ -z "$SEARCH_TERM_ARGS" ]; then
    echo "Error: No search term files found in data/raw/"
    exit 1
fi

if [ -z "$KDP_ARGS" ]; then
    echo "Error: No KDP file(s) found in data/raw/"
    exit 1
fi

echo "Pull date: $WEEK"
echo "KDP args: $KDP_ARGS"
if [ -n "$TARGETING_ARGS" ]; then
    echo "Targeting reports found"
else
    echo "No targeting reports found (bid enrichment will be skipped)"
fi
echo ""

eval python analyze.py report --week "$WEEK" $SEARCH_TERM_ARGS $KDP_ARGS $TARGETING_ARGS $SAVE_FLAG
