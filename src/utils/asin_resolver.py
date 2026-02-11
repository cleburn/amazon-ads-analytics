"""ASIN-to-title resolver for search term display names.

Resolves raw ASINs (e.g., "b0fkp8tnds", "0063426285") to human-readable
book titles using a local JSON lookup file and optional Amazon scraping.
"""

import json
import os
import re
import time
import urllib.request
import urllib.error


# ASIN pattern: 10-char starting with B0 (Kindle) or 10-digit ISBN
_ASIN_RE = re.compile(r"^[Bb]0[A-Za-z0-9]{8}$")
_ISBN_RE = re.compile(r"^\d{10}$")

_DEFAULT_LOOKUP_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "asin_lookup.json"
)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_SCRAPE_DELAY = 1.0  # seconds between Amazon requests


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


def _scrape_amazon_title(asin: str) -> str | None:
    """Attempt to scrape the product title from Amazon's product page.

    Returns the title string if successful, None if blocked/failed.
    """
    url = f"https://www.amazon.com/dp/{asin.upper()}"
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        # Try the <title> tag first — Amazon titles are like:
        # "Amazon.com: Book Title: Author: Books"
        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL)
        if title_match:
            raw = title_match.group(1).strip()
            # Strip "Amazon.com: " prefix and trailing ": Books" etc.
            raw = re.sub(r"^Amazon\.com:\s*", "", raw)
            raw = re.sub(r"\s*:\s*Books\s*$", "", raw)
            # Also strip author suffix after last colon if it's short
            # e.g. "Book Title: Author Name" — keep it, it's useful context
            if raw and len(raw) < 200:
                return raw
        # Fallback: productTitle span
        pt_match = re.search(r'id="productTitle"[^>]*>(.*?)</span>', html, re.DOTALL)
        if pt_match:
            return pt_match.group(1).strip()
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        pass
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
        for i, asin in enumerate(unknown_asins):
            if i > 0:
                time.sleep(_SCRAPE_DELAY)
            title = _scrape_amazon_title(asin)
            if title:
                result[asin] = f"{title} ({asin})"
                # Cache with uppercase canonical ASIN
                canonical = asin.upper() if asin[0].lower() == "b" else asin
                newly_resolved[canonical] = title
            else:
                result[asin] = f"{asin} (unknown)"

    # Persist newly scraped titles
    if newly_resolved:
        lookup.update(newly_resolved)
        _save_lookup(lookup, lookup_path)

    return result
