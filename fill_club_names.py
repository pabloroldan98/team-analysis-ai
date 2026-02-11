#!/usr/bin/env python
"""
fill_club_names.py
==================
Standalone script that scans every JSON file under ``data/json/`` and fills in
missing club/team names by querying the Transfermarkt API.

Supported name↔id pairs
------------------------
* **transfers_\*.json** – ``from_club_name`` / ``from_club_id``,
  ``to_club_name`` / ``to_club_id``
* **valuations_\*.json** – ``club_name_at_valuation`` / ``club_id_at_valuation``
* **players_\*.json** – ``team`` / ``team_id``,
  ``loaning_team`` / ``loaning_team_id``

Usage::

    python fill_club_names.py            # scan + fill all files
    python fill_club_names.py --dry-run  # scan only, don't write
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import requests

# ── Configuration ────────────────────────────────────────────────────────────
DATA_DIR = Path("data/json")
TM_API_URL = "https://tmapi-alpha.transfermarkt.technology"

MAX_RETRIES = 50
RETRY_PAUSE = 10  # seconds
REQUEST_DELAY = 0.3  # polite delay between requests

# Name-key → ID-key mappings per file prefix.
# Each tuple is (name_key, id_key).
FILE_KEY_MAP: Dict[str, List[Tuple[str, str]]] = {
    "transfers": [
        ("from_club_name", "from_club_id"),
        ("to_club_name", "to_club_id"),
    ],
    "valuations": [
        ("club_name_at_valuation", "club_id_at_valuation"),
    ],
    "players": [
        ("team", "team_id"),
        ("loaning_team", "loaning_team_id"),
    ],
}


# ── API helpers ──────────────────────────────────────────────────────────────

def _api_get(url: str, timeout: int = 60) -> Optional[dict]:
    """GET with retry logic.  Returns parsed JSON, ``{"_status": code}`` on
    persistent transient errors (414/429/5xx), or ``None`` on hard failure."""

    last_transient_code = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(REQUEST_DELAY)
            resp = requests.get(url, timeout=timeout)

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code == 414:
                return {"_status": 414}

            if resp.status_code in (429, 500, 502, 503, 504):
                last_transient_code = resp.status_code
                print(f"    Attempt {attempt}/{MAX_RETRIES}: HTTP {resp.status_code}")
            else:
                print(f"    HTTP {resp.status_code} – giving up")
                return None

        except Exception as exc:
            last_transient_code = last_transient_code or 429
            print(f"    Attempt {attempt}/{MAX_RETRIES}: {exc!r}")

        if attempt < MAX_RETRIES:
            print(f"    Retrying in {RETRY_PAUSE}s …")
            time.sleep(RETRY_PAUSE)

    print(f"    All {MAX_RETRIES} attempts failed for {url}")
    if last_transient_code is not None:
        return {"_status": last_transient_code}
    return None


def fetch_club_names(club_ids: Set[str]) -> Dict[str, str]:
    """Fetch club names from the API, splitting adaptively on errors."""
    if not club_ids:
        return {}

    cache: Dict[str, str] = {}
    ids_list = sorted(cid for cid in club_ids if cid)

    print(f"\n{'='*60}")
    print(f"Fetching names for {len(ids_list)} club IDs via API …")
    print(f"{'='*60}")

    def _fetch_batch(batch: list) -> None:
        if not batch:
            return

        params = "&".join(f"ids[]={cid}" for cid in batch)
        api_url = f"{TM_API_URL}/clubs?{params}"
        data = _api_get(api_url)

        if data is None:
            print(f"    FAILED to fetch batch of {len(batch)} – skipping")
            return

        # Splittable error → halve and retry
        error_status = data.get("_status")
        if error_status is not None:
            if len(batch) <= 1:
                print(f"    Cannot split further, skipping ID: {batch[0]}")
                return
            mid = len(batch) // 2
            print(f"    HTTP {error_status} with {len(batch)} IDs → splitting in half")
            _fetch_batch(batch[:mid])
            _fetch_batch(batch[mid:])
            return

        if data.get("success"):
            clubs_data = data.get("data", [])
            for club in clubs_data:
                cid = str(club.get("id", ""))
                cname = club.get("name", "")
                if cid:
                    cache[cid] = cname
            print(f"    ✓ Fetched {len(clubs_data)} names (batch of {len(batch)})")

    _fetch_batch(ids_list)
    print(f"    Total names resolved: {len(cache)}")
    return cache


# ── Scanning & filling ───────────────────────────────────────────────────────

def _file_prefix(filename: str) -> Optional[str]:
    """Return the category prefix (transfers, valuations, players) or None."""
    for prefix in FILE_KEY_MAP:
        if filename.startswith(prefix):
            return prefix
    return None


def scan_missing_ids(data_dir: Path) -> Tuple[Set[str], Dict[str, list]]:
    """
    Walk every JSON file and collect club IDs whose corresponding name is
    empty.

    Returns
    -------
    missing_ids : set[str]
        All unique club IDs that need resolving.
    files_to_patch : dict[str, list[tuple[str, str]]]
        Mapping of *file path* → list of (name_key, id_key) pairs that
        contain at least one gap.
    """
    missing_ids: Set[str] = set()
    files_to_patch: Dict[str, list] = {}

    json_files = sorted(data_dir.glob("*.json"))
    print(f"Scanning {len(json_files)} JSON files …\n")

    for fp in json_files:
        prefix = _file_prefix(fp.name)
        if prefix is None:
            continue

        key_pairs = FILE_KEY_MAP[prefix]
        file_missing = False

        try:
            with open(fp, "r", encoding="utf-8") as f:
                records = json.load(f)
        except Exception as exc:
            print(f"  SKIP {fp.name}: {exc}")
            continue

        if not isinstance(records, list):
            continue

        for rec in records:
            for name_key, id_key in key_pairs:
                club_id = rec.get(id_key)
                club_name = rec.get(name_key)
                if club_id and not club_name:
                    missing_ids.add(str(club_id))
                    file_missing = True

        if file_missing:
            files_to_patch[str(fp)] = key_pairs

    print(f"  Missing names found for {len(missing_ids)} unique club IDs")
    print(f"  Files that need patching: {len(files_to_patch)}")
    return missing_ids, files_to_patch


def patch_files(
    files_to_patch: Dict[str, list],
    name_map: Dict[str, str],
) -> None:
    """Rewrite each JSON file, filling empty names from *name_map*."""
    if not files_to_patch:
        print("\nNo files to patch.")
        return

    total_filled = 0

    for filepath, key_pairs in sorted(files_to_patch.items()):
        fp = Path(filepath)
        with open(fp, "r", encoding="utf-8") as f:
            records = json.load(f)

        file_filled = 0
        for rec in records:
            for name_key, id_key in key_pairs:
                club_id = rec.get(id_key)
                club_name = rec.get(name_key)
                if club_id and not club_name:
                    resolved = name_map.get(str(club_id))
                    if resolved:
                        rec[name_key] = resolved
                        file_filled += 1

        if file_filled:
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            print(f"  {fp.name}: filled {file_filled} names")
            total_filled += file_filled
        else:
            print(f"  {fp.name}: nothing to fill (IDs not resolved)")

    print(f"\nTotal names filled across all files: {total_filled}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fill missing club/team names in data/json/ files."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and fetch names but don't write changes to disk.",
    )
    args = parser.parse_args()

    if not DATA_DIR.exists():
        print(f"ERROR: {DATA_DIR} not found. Run from the project root.")
        return

    # 1. Scan
    missing_ids, files_to_patch = scan_missing_ids(DATA_DIR)

    if not missing_ids:
        print("\n✓ All club names are already filled – nothing to do!")
        return

    # 2. Fetch
    name_map = fetch_club_names(missing_ids)

    resolved = sum(1 for mid in missing_ids if mid in name_map)
    print(f"\nResolved {resolved}/{len(missing_ids)} IDs")

    if args.dry_run:
        print("\n[DRY RUN] – no files were modified.")
        # Show a sample of resolved names
        for cid, cname in list(name_map.items())[:20]:
            print(f"  {cid} → {cname}")
        if len(name_map) > 20:
            print(f"  … and {len(name_map) - 20} more")
        return

    # 3. Patch
    print(f"\nPatching {len(files_to_patch)} files …\n")
    patch_files(files_to_patch, name_map)
    print("\n✓ Done!")


if __name__ == "__main__":
    main()
