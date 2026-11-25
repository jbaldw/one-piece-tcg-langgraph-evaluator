"""Download the card lists from optcgapi.com (https://optcgapi.com/documentation).

The API asks users to keep call volume low, so `seed` reads these cached files and only
`fetch-cards` touches the network.
"""

import json
import urllib.request
from pathlib import Path

BASE_URL = "https://optcgapi.com/api"

# Maps the cache file stem (also stored as card_printings.source) to its endpoint.
# /api/allPromoCards/ is listed in the docs but returned 404 as of 2026-11-25; promo IDs
# (P-xxx) that were reprinted in sets still arrive through allSetCards.
ENDPOINTS = {
    "set": "allSetCards",
    "starter": "allSTCards",
}

USER_AGENT = "op-tcg-evaluator"


def cache_dir(db_path: Path) -> Path:
    return db_path.parent / "optcgapi"


def fetch_all(dest: Path, timeout: float = 60) -> dict[str, int]:
    """Fetch every endpoint into `dest/<source>.json`. Returns the row count per source."""
    dest.mkdir(parents=True, exist_ok=True)
    counts = {}
    for source, endpoint in ENDPOINTS.items():
        request = urllib.request.Request(
            f"{BASE_URL}/{endpoint}/", headers={"User-Agent": USER_AGENT}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            rows = json.load(response)
        if not isinstance(rows, list):
            raise ValueError(f"{endpoint}: expected a JSON list, got {type(rows).__name__}")
        # Write to a temp file first so a failed run never leaves a truncated cache behind.
        tmp = dest / f"{source}.json.tmp"
        tmp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        tmp.replace(dest / f"{source}.json")
        counts[source] = len(rows)
    return counts


def load_cached(src: Path) -> dict[str, list[dict]]:
    """Read the cached files written by `fetch_all`, keyed by source."""
    missing = [s for s in ENDPOINTS if not (src / f"{s}.json").exists()]
    if missing:
        raise FileNotFoundError(
            f"no cached card data for {', '.join(missing)} in {src}; run `op-eval fetch-cards`"
        )
    return {s: json.loads((src / f"{s}.json").read_text(encoding="utf-8")) for s in ENDPOINTS}
