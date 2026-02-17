#!/usr/bin/env python
r"""
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
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import requests

# Ensure project root is on sys.path so helpers can be imported
_ROOT = Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scraping.utils.helpers import DATA_DIR, list_json_bases, load_json, parse_date

# ── Configuration ────────────────────────────────────────────────────────────
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
    "teams": [
        ("name", "team_id"),
    ],
}

# Type alias for pre-loaded file records: (filepath_str, prefix, records_list)
FileRecord = Tuple[str, str, list]


# ── File loading ─────────────────────────────────────────────────────────────

def _file_prefix(filename: str) -> Optional[str]:
    """Return the category prefix (transfers, valuations, players) or None."""
    for prefix in FILE_KEY_MAP:
        if filename.startswith(prefix):
            return prefix
    return None


def load_all_json_files(data_dir: Path) -> List[FileRecord]:
    """Load every relevant JSON file from *data_dir* exactly once.

    Returns a list of ``(filepath_str, prefix, records)`` tuples.
    Only files whose name starts with a known prefix (transfers, valuations,
    players, teams) are included. Uses load_json from utils (supports multi-part).
    """
    result: List[FileRecord] = []
    # bases = list_json_bases("*.json")
    bases = list_json_bases("*_all_*.json")
    print(f"Loading JSON files from {data_dir} …")

    for base in bases:
        prefix = _file_prefix(base + ".json")
        if prefix is None:
            continue
        try:
            raw = load_json(base)
        except Exception as exc:
            print(f"  SKIP {base}: {exc}")
            continue
        if raw is None:
            continue
        records = raw["items"] if isinstance(raw, dict) and "items" in raw else raw
        if not isinstance(records, list):
            continue
        result.append((str(data_dir / f"{base}.json"), prefix, records))

    print(f"  Loaded {len(result)} files into memory.\n")
    return result


# ── Local name map (fallback) ────────────────────────────────────────────────

def build_local_name_map(file_records: List[FileRecord]) -> Dict[str, str]:
    """Build a ``{club_id: club_name}`` dict from all existing data.

    Iterates every record in every loaded file and collects non-empty
    name↔id pairs.  This serves as a **last-resort fallback** when the
    Transfermarkt API is unreachable.
    """
    name_map: Dict[str, str] = {}

    for _filepath, prefix, records in file_records:
        key_pairs = FILE_KEY_MAP.get(prefix, [])
        for rec in records:
            for name_key, id_key in key_pairs:
                club_id = rec.get(id_key)
                club_name = rec.get(name_key)
                if club_id and club_name:
                    name_map[str(club_id)] = club_name

    return name_map


# ── Fix empty valuation dates ────────────────────────────────────────────────

def fix_empty_valuation_dates(
    file_records: List[FileRecord],
) -> Tuple[int, Set[str]]:
    """Fill empty ``valuation_date`` using neighbouring valuations.

    For each valuation record with an empty date:

    1. Use the **next** valuation's date **− 1 day** (same player, by
       list order).
    2. If there is no next, use the **previous** valuation's date
       **+ 1 day**.
    3. If neither exists, fall back to ``01/06/{season_start_year}``
       extracted from the filename; otherwise skip.

    Records are modified **in-place**.

    Returns ``(fixed_count, modified_file_paths)``.
    """
    from datetime import timedelta

    fixed = 0
    modified_files: Set[str] = set()

    for filepath, prefix, records in file_records:
        if prefix != "valuations":
            continue

        # Extract season year from filename (e.g. valuations_seriea_2017-2018)
        season_year: Optional[int] = None
        for part in Path(filepath).stem.split("_"):
            if "-" in part:
                try:
                    season_year = int(part.split("-")[0])
                    break
                except (ValueError, IndexError):
                    pass

        # Group by player_id, preserving original list order
        by_player: Dict[str, List[dict]] = {}
        for rec in records:
            pid = rec.get("player_id")
            if pid:
                by_player.setdefault(pid, []).append(rec)

        for _pid, pvs in by_player.items():
            for i, rec in enumerate(pvs):
                if rec.get("valuation_date"):
                    continue

                # 1. Next → date − 1 day
                filled = False
                for j in range(i + 1, len(pvs)):
                    nd = parse_date(pvs[j].get("valuation_date", ""))
                    if nd:
                        rec["valuation_date"] = (nd - timedelta(days=1)).strftime("%d/%m/%Y")
                        fixed += 1
                        filled = True
                        modified_files.add(filepath)
                        break

                if filled:
                    continue

                # 2. Previous → date + 1 day
                for j in range(i - 1, -1, -1):
                    pd = parse_date(pvs[j].get("valuation_date", ""))
                    if pd:
                        rec["valuation_date"] = (pd + timedelta(days=1)).strftime("%d/%m/%Y")
                        fixed += 1
                        filled = True
                        modified_files.add(filepath)
                        break

                if filled:
                    continue

                # 3. Season fallback
                if season_year:
                    rec["valuation_date"] = f"01/06/{season_year}"
                    fixed += 1
                    modified_files.add(filepath)

    return fixed, modified_files


# ── Transfer-based club fix for valuations ───────────────────────────────────

def build_transfer_index(
    file_records: List[FileRecord],
) -> Dict[str, List[Tuple[datetime, dict]]]:
    """Build ``{player_id: [(date, transfer_record), …]}`` from transfer files.

    The list for each player is sorted by date ascending.
    """
    index: Dict[str, List[Tuple[datetime, dict]]] = {}

    for _filepath, prefix, records in file_records:
        if prefix != "transfers":
            continue
        for rec in records:
            pid = rec.get("player_id")
            date_str = rec.get("transfer_date", "")
            if not pid or not date_str:
                continue
            td = parse_date(date_str)
            if td is None:
                continue
            index.setdefault(pid, []).append((td, rec))

    for pid in index:
        index[pid].sort(key=lambda x: x[0])

    return index


def fix_valuations_from_transfers(
    file_records: List[FileRecord],
    transfer_index: Dict[str, List[Tuple[datetime, dict]]],
) -> Tuple[int, Set[str]]:
    """Fix empty ``club_name_at_valuation`` using transfer history.

    For each valuation record with no club name (or ``club_id == "0"``):

    1. Find the latest transfer with ``date <= valuation_date`` → use
       ``to_club_name`` / ``to_club_id``.
    2. If none exists before that date, take the closest transfer overall
       and use ``from_club_name`` / ``from_club_id``.

    Records are modified **in-place**.

    Returns ``(fixed_count, modified_file_paths)``.
    """
    fixed = 0
    modified_files: Set[str] = set()

    for filepath, prefix, records in file_records:
        if prefix != "valuations":
            continue
        for rec in records:
            club_name = rec.get("club_name_at_valuation")
            club_id = rec.get("club_id_at_valuation")
            if club_name and club_id != "0":
                continue

            pid = rec.get("player_id")
            if not pid:
                continue

            player_transfers = transfer_index.get(pid)
            if not player_transfers:
                continue

            val_date = parse_date(rec.get("valuation_date", ""))
            if not val_date:
                continue

            # Latest transfer with date <= valuation_date
            best_before = None
            for t_date, t in player_transfers:
                if t_date <= val_date:
                    best_before = (t_date, t)
                    # List is sorted, so last match = latest before

            if best_before:
                t = best_before[1]
                name = t.get("to_club_name")
                if name:
                    rec["club_name_at_valuation"] = name
                    tid = t.get("to_club_id")
                    if tid:
                        rec["club_id_at_valuation"] = tid
                    fixed += 1
                    modified_files.add(filepath)
                    continue

            # No transfer before → earliest transfer, use from_club_name
            _first_date, closest = player_transfers[0]

            if closest:
                name = closest.get("from_club_name")
                if name:
                    rec["club_name_at_valuation"] = name
                    fid = closest.get("from_club_id")
                    if fid:
                        rec["club_id_at_valuation"] = fid
                    fixed += 1
                    modified_files.add(filepath)

    return fixed, modified_files


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

def scan_missing_ids(
    file_records: List[FileRecord],
) -> Tuple[Set[str], Dict[str, list]]:
    """
    From pre-loaded file records, collect club IDs whose corresponding
    name is empty.

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

    for filepath, prefix, records in file_records:
        key_pairs = FILE_KEY_MAP.get(prefix, [])
        file_missing = False

        for rec in records:
            for name_key, id_key in key_pairs:
                club_id = rec.get(id_key)
                club_name = rec.get(name_key)
                if club_id and not club_name:
                    missing_ids.add(str(club_id))
                    file_missing = True

        if file_missing:
            files_to_patch[filepath] = key_pairs

    print(f"  Missing names found for {len(missing_ids)} unique club IDs")
    print(f"  Files that need patching: {len(files_to_patch)}")
    return missing_ids, files_to_patch


def patch_files(
    file_records: List[FileRecord],
    files_to_patch: Dict[str, list],
    name_map: Dict[str, str],
    force_write: Optional[Set[str]] = None,
) -> None:
    """Fill empty names from *name_map* and write modified files to disk.

    Uses the already-loaded *file_records* so files are NOT re-read.

    Parameters
    ----------
    force_write : set[str] | None
        File paths that must be written even if *name_map* didn't fill
        anything (e.g. because a prior step already modified them
        in-place).
    """
    force_write = force_write or set()

    # Merge force-write paths into files_to_patch so they are iterated
    all_paths = dict(files_to_patch)
    for fp in force_write:
        if fp not in all_paths:
            # We don't need key_pairs for these – just need them written
            all_paths[fp] = []

    if not all_paths:
        print("\nNo files to patch.")
        return

    # Index records by filepath for quick lookup
    records_by_path = {fp: recs for fp, _pfx, recs in file_records}

    total_filled = 0

    for filepath, key_pairs in sorted(all_paths.items()):
        records = records_by_path.get(filepath)
        if records is None:
            continue

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

        needs_write = file_filled > 0 or filepath in force_write
        if needs_write:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            total_filled += file_filled
            if file_filled and filepath in force_write:
                print(f"  {Path(filepath).name}: filled {file_filled} names "
                      f"(+ earlier in-place fixes)")
            elif file_filled:
                print(f"  {Path(filepath).name}: filled {file_filled} names")
            else:
                print(f"  {Path(filepath).name}: saved (modified by earlier fixes)")
        else:
            print(f"  {Path(filepath).name}: nothing to fill (IDs not resolved)")

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

    # 1. Load all JSON files once
    file_records = load_all_json_files(DATA_DIR)

    # 2. Scan for missing names
    missing_ids, files_to_patch = scan_missing_ids(file_records)

    if not missing_ids:
        print("\n✓ All club names are already filled – nothing to do!")
        return

    # 3. Fetch from API
    name_map = fetch_club_names(missing_ids)

    # 4. Fallback: fill remaining gaps from existing data in the files
    still_missing = missing_ids - set(name_map.keys())
    if still_missing:
        print(f"\n{len(still_missing)} IDs still unresolved – "
              f"trying local fallback from existing files …")
        local_map = build_local_name_map(file_records)
        found_locally = 0
        for mid in still_missing:
            if mid in local_map:
                name_map[mid] = local_map[mid]
                found_locally += 1
        print(f"  Resolved {found_locally} more IDs from local data")

    resolved = sum(1 for mid in missing_ids if mid in name_map)
    print(f"\nTotal resolved: {resolved}/{len(missing_ids)} IDs")

    # 5. Fix empty valuation dates (must happen before transfer-based fix)
    print("\nFixing empty valuation dates …")
    dates_fixed, date_modified_files = fix_empty_valuation_dates(file_records)
    if dates_fixed:
        print(f"  Fixed {dates_fixed} empty valuation dates")
    else:
        print("  No empty dates found")

    # 6. Fix valuation club names from transfer history
    #    (handles club_id "0" and names the API couldn't resolve)
    print("\nFixing valuation club names from transfer history …")
    transfer_index = build_transfer_index(file_records)
    transfer_fixed, transfer_modified_files = (0, set())
    # Merge date-modified files so they get written
    transfer_modified_files = set(date_modified_files)
    if transfer_index:
        transfer_fixed, transfer_modified_files = fix_valuations_from_transfers(
            file_records, transfer_index,
        )
        print(f"  Fixed {transfer_fixed} valuation club names from transfers")
    else:
        print("  No transfer data available – skipping")

    if args.dry_run:
        print("\n[DRY RUN] – no files were modified.")
        for cid, cname in list(name_map.items())[:20]:
            print(f"  {cid} → {cname}")
        if len(name_map) > 20:
            print(f"  … and {len(name_map) - 20} more")
        return

    # 7. Patch & write
    print(f"\nPatching {len(files_to_patch)} files …\n")
    patch_files(file_records, files_to_patch, name_map,
                force_write=transfer_modified_files)
    print("\n✓ Done!")


if __name__ == "__main__":
    main()
