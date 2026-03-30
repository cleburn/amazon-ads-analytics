"""ASIN-to-title resolver for search term display names.

Resolves raw ASINs (e.g., "b0fkp8tnds", "0063426285") to human-readable
book titles using a local JSON lookup file and optional Amazon scraping.
"""

import html
import json
import os
import random
import re
import signal
import time
import urllib.request
import urllib.error
import urllib.parse


# ASIN pattern: 10-char starting with B0 (Kindle) or 10-digit ISBN
_ASIN_RE = re.compile(r"^[Bb]0[A-Za-z0-9]{8}$")
_ISBN_RE = re.compile(r"^\d{10}$")

_DEFAULT_LOOKUP_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "asin_lookup.json"
)

# Pool of realistic User-Agent strings for rotation
_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]

# Delay range between requests (seconds) — randomized jitter
_DELAY_MIN = 2.0
_DELAY_MAX = 5.0

# Exponential backoff on consecutive failures
_BACKOFF_BASE = 10.0  # seconds after 1st failure
_BACKOFF_MAX = 60.0   # cap per-request backoff
_TOTAL_BACKOFF_BUDGET = 180.0  # stop retrying after this much total backoff time


def is_asin(term: str) -> bool:
    """Check if a search term looks like an ASIN or 10-digit ISBN."""
    term = term.strip()
    return bool(_ASIN_RE.match(term) or _ISBN_RE.match(term))


def _load_lookup(path: str) -> dict:
    """Load ASIN lookup from JSON file. Returns empty dict if missing."""
    path = os.path.normpath(path)
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)


def _save_lookup(lookup: dict, path: str) -> None:
    """Save updated lookup back to JSON file."""
    path = os.path.normpath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(lookup, f, indent=2)
        f.write("\n")


def _clean_title(raw: str) -> str | None:
    """Clean a raw scraped title. Returns None if the title is junk."""
    # Decode HTML entities (&#x27; → ', &amp; → &, etc.)
    raw = html.unescape(raw)
    # Strip "Amazon.com: " prefix
    raw = re.sub(r"^Amazon\.com:\s*", "", raw)
    # Reject if nothing left but "Amazon.com" (CAPTCHA / bot block page)
    if not raw or raw.strip().lower() in ("amazon.com", "page not found"):
        return None
    # Strip trailing ": Books" or ": Kindle Store" etc.
    raw = re.sub(r"\s*:\s*(Books|Kindle Store)\s*$", "", raw)
    # Strip "Author, Name: ISBN: Amazon.com" suffix from <title> tags
    # Pattern: ": Author: 978...: Amazon.com" at end
    raw = re.sub(r":\s*\d{13,}:\s*Amazon\.com\s*$", "", raw)
    raw = re.sub(r"\s*:\s*Amazon\.com\s*$", "", raw)
    # Strip "eBook : Author" suffix (Kindle titles)
    raw = re.sub(r"\s*eBook\s*:\s*.+$", "", raw)
    # Strip author after last ": Author, Name" if it follows an ISBN-like pattern
    # But keep subtitles — only strip if what follows looks like "Lastname, First"
    raw = re.sub(r":\s*[A-Z][a-z]+,\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s*$", "", raw)
    raw = raw.strip().rstrip(":")
    if not raw or raw.strip().lower() == "amazon.com":
        return None
    return raw


class _Timeout(Exception):
    pass


def _timeout_handler(signum, frame):
    raise _Timeout()


def _scrape_amazon_title(asin: str) -> str | None:
    """Attempt to scrape the product title from Amazon's product page.

    Returns the cleaned title string if successful, None if blocked/failed.
    Uses a hard 15-second total timeout (SIGALRM) to prevent indefinite hangs
    from slow responses, redirect chains, or CAPTCHA pages.
    """
    url = f"https://www.amazon.com/dp/{asin.upper()}"
    ua = random.choice(_USER_AGENTS)
    req = urllib.request.Request(url, headers={"User-Agent": ua})

    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(15)  # hard 15-second total timeout
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            page = resp.read().decode("utf-8", errors="replace")
        signal.alarm(0)
        # Try productTitle span first (most reliable when present)
        pt_match = re.search(r'id="productTitle"[^>]*>(.*?)</span>', page, re.DOTALL)
        if pt_match:
            return _clean_title(pt_match.group(1).strip())
        # Fallback: <title> tag
        title_match = re.search(r"<title[^>]*>(.*?)</title>", page, re.DOTALL)
        if title_match:
            return _clean_title(title_match.group(1).strip())
    except (_Timeout, urllib.error.URLError, urllib.error.HTTPError, OSError):
        pass
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
    return None


def _google_fallback_title(asin: str) -> str | None:
    """Fall back to Google search to find an Amazon product title.

    Searches for 'amazon.com/dp/{ASIN}' and extracts the title from the
    search result snippet. Less likely to be blocked than direct Amazon scraping.
    """
    query = urllib.parse.quote(f"amazon.com/dp/{asin.upper()}")
    url = f"https://www.google.com/search?q={query}"
    ua = random.choice(_USER_AGENTS)
    req = urllib.request.Request(url, headers={"User-Agent": ua})

    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(15)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            page = resp.read().decode("utf-8", errors="replace")
        signal.alarm(0)

        # Google wraps result titles in <h3> tags; the first one matching
        # an Amazon-like pattern is our best bet
        h3_matches = re.findall(r"<h3[^>]*>(.*?)</h3>", page, re.DOTALL)
        for h3 in h3_matches:
            # Strip HTML tags from the h3 content
            text = re.sub(r"<[^>]+>", "", h3).strip()
            text = html.unescape(text)
            # Skip results that are clearly not product titles
            if not text or "amazon" in text.lower() and len(text) < 15:
                continue
            cleaned = _clean_title(text)
            if cleaned:
                return cleaned

        # Fallback: try <title>-style patterns in result snippets
        # Google sometimes puts the title in span/div with specific classes
        snippet_matches = re.findall(
            r'(?:aria-level="3"|role="heading")[^>]*>(.*?)</(?:span|div|h3)',
            page, re.DOTALL,
        )
        for snippet in snippet_matches:
            text = re.sub(r"<[^>]+>", "", snippet).strip()
            text = html.unescape(text)
            cleaned = _clean_title(text)
            if cleaned:
                return cleaned
    except (_Timeout, urllib.error.URLError, urllib.error.HTTPError, OSError):
        pass
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)
    return None


def resolve_asins(
    terms: list[str],
    lookup_path: str | None = None,
    scrape: bool = True,
) -> dict[str, str]:
    """Resolve a list of search terms, returning a mapping for ASIN terms.

    Args:
        terms: List of raw search term strings.
        lookup_path: Path to asin_lookup.json. Uses default if None.
        scrape: Whether to attempt Amazon scraping for unknown ASINs.

    Returns:
        Dict mapping original search term → display name.
        Only includes entries for terms that are ASINs.
        Format: "Book Title (ASIN)" or "ASIN (unknown)" if unresolved.
    """
    if lookup_path is None:
        lookup_path = _DEFAULT_LOOKUP_PATH

    lookup = _load_lookup(lookup_path)
    # Build case-insensitive index: lowercase ASIN → (canonical ASIN, title)
    lookup_lower = {k.lower(): (k, v) for k, v in lookup.items()}

    result = {}
    newly_resolved = {}
    unknown_asins = []

    for term in terms:
        if not is_asin(term):
            continue

        term_lower = term.strip().lower()
        if term_lower in lookup_lower:
            canonical, title = lookup_lower[term_lower]
            result[term] = f"{title} ({term})"
        else:
            unknown_asins.append(term)

    # Scrape unknown ASINs
    if scrape and unknown_asins:
        import sys
        total = len(unknown_asins)
        consecutive_failures = 0
        total_backoff_used = 0.0
        print(f"  Resolving {total} unknown ASINs...", file=sys.stderr)
        for i, asin in enumerate(unknown_asins):
            if i > 0:
                delay = random.uniform(_DELAY_MIN, _DELAY_MAX)
                time.sleep(delay)
            print(f"    [{i+1}/{total}] {asin}...", end="", file=sys.stderr, flush=True)

            # Try Amazon direct scrape first
            title = _scrape_amazon_title(asin)
            source = "amazon"

            # Fall back to Google if Amazon failed
            if not title:
                time.sleep(random.uniform(1.0, 2.0))
                title = _google_fallback_title(asin)
                source = "google"

            if title:
                result[asin] = f"{title} ({asin})"
                canonical = asin.upper() if asin[0].lower() == "b" else asin
                newly_resolved[canonical] = title
                consecutive_failures = 0
                label = " OK" if source == "amazon" else " OK (google)"
                print(label, file=sys.stderr)
            else:
                result[asin] = f"{asin} (unknown)"
                consecutive_failures += 1
                print(f" failed", file=sys.stderr)

                # Exponential backoff on consecutive failures
                if consecutive_failures > 0:
                    backoff = min(
                        _BACKOFF_BASE * (2 ** (consecutive_failures - 1)),
                        _BACKOFF_MAX,
                    )
                    total_backoff_used += backoff
                    if total_backoff_used > _TOTAL_BACKOFF_BUDGET:
                        remaining = total - i - 1
                        print(
                            f"  Stopping — backoff budget exhausted "
                            f"({remaining} ASINs skipped)",
                            file=sys.stderr,
                        )
                        for remaining_asin in unknown_asins[i + 1:]:
                            result[remaining_asin] = f"{remaining_asin} (unknown)"
                        break
                    print(
                        f"    Backing off {backoff:.0f}s "
                        f"({consecutive_failures} consecutive failures)...",
                        file=sys.stderr,
                    )
                    time.sleep(backoff)

    # Persist newly scraped titles
    if newly_resolved:
        lookup.update(newly_resolved)
        _save_lookup(lookup, lookup_path)

    return result


def retry_unknown_asins(
    unknown_asins: list[str],
    lookup_path: str | None = None,
) -> dict[str, str]:
    """Retry resolution for a list of ASINs not yet in the lookup file.

    Returns dict of {ASIN: title} for newly resolved entries.
    """
    if lookup_path is None:
        lookup_path = _DEFAULT_LOOKUP_PATH

    resolved = resolve_asins(
        terms=unknown_asins,
        lookup_path=lookup_path,
        scrape=True,
    )
    # Return only the ones that resolved to actual titles (not "unknown")
    return {
        asin: display for asin, display in resolved.items()
        if "(unknown)" not in display
    }
