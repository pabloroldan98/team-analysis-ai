#!/usr/bin/env python
r"""
fill_parent_team_id.py
======================
Standalone script that backfills the ``parent_team_id`` field on every
``teams_all_*.json`` file under ``data/json/``.

Resolution logic (per team_id)
------------------------------
1. Call ``GET /clubs?ids[]=...`` on the Transfermarkt alpha API in **batches**
   (with adaptive halving on 414/429/5xx), reading each club's
   ``baseDetails.mainClubId``.
2. If ``baseDetails`` is missing from the batch response for a given id,
   fall back to the single-club endpoint ``GET /club/<id>``.
3. ``mainClubId == "0"`` or ``mainClubId == own_id`` ⇒ *no parent*
   (``parent_team_id`` is written as ``null``).

All API results are stored in the shared on-disk cache at
``data/cache/tm_club_api_cache.json`` (see
``scraping/utils/tm_club_api_cache.py``) so repeated runs of this script —
and other scripts that need the same metadata (e.g. ``fill_club_names.py``
once migrated to the shared cache) — do not hit the API twice for the
same club id.

Parent-team mapping is stable across seasons, so the same
``team_id → parent_team_id`` value is applied to every ``teams_all_*.json``
file in which that team appears.  ``teams_all_YYYY-YYYY_OLD.json`` files
are treated as independent bases (never merged with the non-OLD ones),
matching the convention used throughout the project.

Usage::

    python scripts/fill_parent_team_id.py               # fill + write
    python scripts/fill_parent_team_id.py --dry-run     # fetch only, don't write
    python scripts/fill_parent_team_id.py --force       # re-query every team_id
    python scripts/fill_parent_team_id.py --limit 50    # stop after 50 API lookups
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from tqdm import tqdm

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scraping.utils.helpers import DATA_DIR, list_json_bases, load_json, save_json_with_parts
from scraping.utils.tm_club_api_cache import TmClubApiCache


FileRecord = Tuple[str, list]  # (base_name, records)


# ── File loading ─────────────────────────────────────────────────────────────

def load_all_teams_files() -> List[FileRecord]:
    """Load every ``teams_all_*.json`` base (including ``_OLD`` ones)."""
    bases = list_json_bases("teams_all_*.json")
    result: List[FileRecord] = []
    for base in tqdm(bases, desc="Loading teams files", unit="file"):
        try:
            raw = load_json(base)
        except Exception as exc:
            tqdm.write(f"  SKIP {base}: {exc}")
            continue
        if raw is None:
            continue
        records = raw["items"] if isinstance(raw, dict) and "items" in raw else raw
        if not isinstance(records, list):
            continue
        result.append((base, records))
    print(f"  Loaded {len(result)} teams files into memory.\n")
    return result


# ── Scanning ─────────────────────────────────────────────────────────────────

def collect_team_ids(files: List[FileRecord], *, force: bool) -> Set[str]:
    """Return the set of unique team_ids that still need resolving.

    With ``force=True`` every team_id is returned. Otherwise only those
    whose ``parent_team_id`` key is missing from the record (``None``
    values are considered already resolved and skipped).
    """
    ids: Set[str] = set()
    for _base, records in files:
        for rec in records:
            tid = rec.get("team_id")
            if not tid:
                continue
            if force or "parent_team_id" not in rec:
                ids.add(str(tid))
    return ids


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill parent_team_id on every teams_all_*.json file."
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch but don't write files.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-query every team_id even if parent_team_id is already set.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of NEW API lookups (for debugging).",
    )
    args = parser.parse_args()

    if not DATA_DIR.exists():
        print(f"ERROR: {DATA_DIR} not found. Run from the project root.")
        return

    files = load_all_teams_files()
    if not files:
        print("No teams_all_*.json files found.")
        return

    team_ids = collect_team_ids(files, force=args.force)
    if not team_ids:
        print("\n✓ Every team already has parent_team_id resolved – nothing to do!")
        return

    print(f"  Unique team_ids needing resolution: {len(team_ids)}")

    cache = TmClubApiCache.load()

    # Honour --limit by trimming the set of ids we ask the cache to resolve.
    if args.limit is not None and args.limit < len(team_ids):
        missing_before = set(cache.missing(team_ids, need=("main_club_id",)))
        already_cached = team_ids - missing_before
        to_fetch = set(list(sorted(missing_before))[: args.limit])
        ids_for_cache = already_cached | to_fetch
        print(
            f"  --limit {args.limit}: {len(to_fetch)} new fetches "
            f"(plus {len(already_cached)} cached)"
        )
    else:
        ids_for_cache = team_ids

    resolved = cache.fetch(
        ids_for_cache,
        need=("main_club_id",),
        pbar_desc="Fetching parent_team_id",
    )
    cache.save()

    # Build final mapping team_id -> parent_team_id (or None if unresolved/no-parent).
    parents: Dict[str, Optional[str]] = {}
    for tid in team_ids:
        entry = resolved.get(tid) or cache.get(tid)
        if entry is None or not entry.has_base_details:
            continue
        parents[tid] = entry.main_club_id

    print(f"\n  Resolved parent info for {len(parents)}/{len(team_ids)} team ids")

    if args.dry_run:
        print("\n[DRY RUN] – no files were modified.")
        sample = list(parents.items())[:20]
        for tid, pid in sample:
            print(f"  {tid} → {pid}")
        if len(parents) > 20:
            print(f"  … and {len(parents) - 20} more")
        return

    # Apply to every record in every file.
    # Rule: only touch records whose team_id we actually resolved via the API;
    # unresolved ids keep whatever was already on disk (None for fresh files,
    # a previously-set value otherwise).
    total_updated = 0
    files_to_write: List[FileRecord] = []
    for base, records in files:
        changed = 0
        for rec in records:
            tid = rec.get("team_id")
            if not tid or str(tid) not in parents:
                continue
            new_val = parents[str(tid)]
            if rec.get("parent_team_id") != new_val or "parent_team_id" not in rec:
                rec["parent_team_id"] = new_val
                changed += 1
        if changed:
            total_updated += changed
            files_to_write.append((base, records))

    print(f"  Updated {total_updated} records across {len(files_to_write)} files.")

    for base, records in tqdm(files_to_write, desc="Writing files", unit="file"):
        save_json_with_parts(records, base)

    print("\n✓ Done!")


if __name__ == "__main__":
    main()
