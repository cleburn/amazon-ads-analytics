#!/bin/bash
# Usage: ./run-report.sh <pull-date> [--save]
# The pull date is the day you export data. The report covers the 7 days before it.
#   Example: ./run-report.sh 2026-02-16 --save  →  reports on Feb 9–15

set -e

WEEK="$1"
if [ -z "$WEEK" ]; then
    echo "Usage: ./run-report.sh <pull-date> [--save]"
    echo "  pull-date: the day you export data (report covers 7 days before it)"
    echo "  Example: ./run-report.sh 2026-02-16 --save"
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
SEARCH_TERM_ARGS=""
for f in data/raw/Sponsored_Products_Search_term_report*.xlsx; do
    [ -f "$f" ] && SEARCH_TERM_ARGS="$SEARCH_TERM_ARGS --search-terms \"$f\""
done

KDP_FILE=""
for f in data/raw/KDP_Dash*.xlsx; do
    [ -f "$f" ] && KDP_FILE="$f"
done

if [ -z "$SEARCH_TERM_ARGS" ]; then
    echo "Error: No search term files found in data/raw/"
    exit 1
fi

if [ -z "$KDP_FILE" ]; then
    echo "Error: No KDP Dashboard file found in data/raw/"
    exit 1
fi

echo "Pull date: $WEEK"
echo "KDP:  $KDP_FILE"
echo ""

eval python analyze.py report --week "$WEEK" $SEARCH_TERM_ARGS --kdp \"$KDP_FILE\" $SAVE_FLAG
