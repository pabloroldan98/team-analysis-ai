#!/usr/bin/env python3
"""
Re-partition existing season caches into ``*_partN.json`` shards.

Why
---
Legacy caches were written as a single JSON blob
(``data/json/cache/season_data_<season>.json``). Once they grow past GitHub's
100 MB blob limit, ``git push`` starts to fail. This script re-saves every
existing cache through the shared writer
(``simulator.data_loader.save_season_cache_payload``), which automatically
splits payloads over 90 MB into ``season_data_<season>_part1.json``,
``season_data_<season>_part2.json``, … and leaves smaller caches untouched
as a single file.

Behaviour
---------
* Discovers every season on disk (single file OR already-sharded).
* Loads the merged payload via ``simulator.data_loader._load_raw_season_cache``.
* Writes it back via ``save_season_cache_payload`` — the writer removes
  the legacy single file / stale parts before writing the new layout.
* ``--dry-run`` prints the plan without touching anything.
* ``--season`` limits the operation to a single season (``2024-2025`` or
  ``today``); repeat the flag to process several.

Usage
-----
    python scripts/repartition_season_cache.py --dry-run
    python scripts/repartition_season_cache.py
    python scripts/repartition_season_cache.py --season 2025-2026 --season today
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tqdm import tqdm

from simulator.data_loader import (  # noqa: E402
    CACHE_DIR,
    CACHE_PREFIX,
    _MAX_CACHE_PART_BYTES,
    _cache_base_path,
    _cache_part_paths,
    _load_raw_season_cache,
    list_cached_seasons,
    save_season_cache_payload,
)


# ── Discovery ─────────────────────────────────────────────────────────────

def _discover_seasons(requested: Iterable[str] | None) -> List[str]:
    """Return the list of seasons to process, in deterministic order."""
    on_disk = set(list_cached_seasons(include_today=True))
    if not requested:
        return sorted(on_disk, reverse=True)

    unknown = [s for s in requested if s not in on_disk]
    if unknown:
        print(
            f"[WARN] No cache found for season(s): {', '.join(sorted(unknown))}",
            file=sys.stderr,
        )
    return sorted((s for s in requested if s in on_disk), reverse=True)


def _current_layout(season: str) -> Tuple[str, int, int]:
    """Return (layout, num_files, total_bytes) for a season on disk.

    ``layout`` is ``"single"``, ``"parts"`` or ``"none"``.
    """
    base = _cache_base_path(season)
    parts = _cache_part_paths(base)
    if not parts:
        return ("none", 0, 0)
    total = sum(p.stat().st_size for p in parts)
    if len(parts) == 1 and parts[0] == base:
        return ("single", 1, total)
    return ("parts", len(parts), total)


def _projected_parts(byte_size: int) -> int:
    """Mirror the split logic in ``save_season_cache_payload``."""
    if byte_size <= _MAX_CACHE_PART_BYTES:
        return 1
    return max(2, -(-byte_size // _MAX_CACHE_PART_BYTES))


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Re-partition data/json/cache/season_data_*.json into "
            "*_partN.json shards (skips files that already fit in 90 MB)."
        ),
    )
    parser.add_argument(
        "--season",
        action="append",
        metavar="SEASON",
        help="Limit to a specific season (can be passed multiple times).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would happen without writing to disk.",
    )
    args = parser.parse_args()

    if not CACHE_DIR.exists():
        print(f"[ERROR] Cache directory does not exist: {CACHE_DIR}", file=sys.stderr)
        sys.exit(1)

    seasons = _discover_seasons(args.season)
    if not seasons:
        print("Nothing to do — no cached seasons match the request.")
        return

    print(f"Cache directory : {CACHE_DIR}")
    print(f"Seasons to check: {len(seasons)}  ({', '.join(seasons)})")
    print(f"Part size limit : {_MAX_CACHE_PART_BYTES / 1e6:.0f} MB")
    if args.dry_run:
        print("Mode            : DRY RUN (no files will be touched)")
    print()

    plan: List[Tuple[str, str, int, int, int]] = []  # season, layout, files, bytes, projected
    for season in seasons:
        layout, num_files, total_bytes = _current_layout(season)
        if layout == "none":
            continue
        projected = _projected_parts(total_bytes)
        plan.append((season, layout, num_files, total_bytes, projected))

    if not plan:
        print("Nothing to do — no files were discoverable.")
        return

    # Report
    header = f"{'Season':<14} {'Current':<18} {'Total MB':>10} {'→ Parts':>10}"
    print(header)
    print("-" * len(header))
    for season, layout, num_files, total_bytes, projected in plan:
        current = f"{layout} ({num_files})"
        print(
            f"{season:<14} {current:<18} {total_bytes / 1e6:>10.1f} "
            f"{projected:>10}"
        )
    print()

    if args.dry_run:
        oversize = sum(1 for _, _, _, b, _ in plan if b > _MAX_CACHE_PART_BYTES)
        print(
            f"[DRY RUN] {oversize}/{len(plan)} season(s) exceed "
            f"{_MAX_CACHE_PART_BYTES / 1e6:.0f} MB and would be sharded."
        )
        return

    for season, *_ in tqdm(plan, desc="Repartitioning", unit="season"):
        try:
            payload = _load_raw_season_cache(season)
        except Exception as exc:  # pragma: no cover - defensive
            tqdm.write(f"  SKIP {season}: failed to load ({exc})")
            continue
        if payload is None:
            tqdm.write(f"  SKIP {season}: empty or malformed")
            continue

        try:
            written = save_season_cache_payload(payload, season)
        except Exception as exc:  # pragma: no cover - defensive
            tqdm.write(f"  FAIL {season}: {exc}")
            continue

        _, num_after, bytes_after = _current_layout(season)
        tqdm.write(
            f"  OK   {season}: wrote {num_after} file(s), "
            f"{bytes_after / 1e6:.1f} MB total → {written.name}"
        )

    print("\nDone.")


if __name__ == "__main__":
    main()
