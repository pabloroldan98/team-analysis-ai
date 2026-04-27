#!/usr/bin/env python3
"""
Migrate data into the functional layout (see ``common/data_paths.py``).

Moves / merges:

  - ``data/*.json`` (scraped entities) → ``data/datasets/<entity>/``
  - ``data/<entity>/`` (legacy folder at data root, e.g. ``data/players/``) →
    ``data/datasets/<entity>/``
  - ``data/dataset/`` (singular typo) → merge into ``data/datasets/``
  - ``data/cache/*.json`` at cache root → ``data/cache/seasons/`` or
    ``data/cache/clubs/`` (by filename)
  - ``data/discovered_leagues.json`` → ``data/datasets/metadata/``

Run with ``--dry-run`` first. Safe to run multiple times (skips if dest exists).

Usage::
    python scripts/migrate_data_layout_functional.py --dry-run
    python scripts/migrate_data_layout_functional.py
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.data_paths import (  # noqa: E402
    CACHE_CLUBS,
    CACHE_SEASONS,
    DATA_DIR,
    DATASET_ENTITY_DIRS,
    DATASETS_ROOT,
    DS_METADATA,
    KNOWN_ENTITY_PREFIXES,
    ensure_data_tree,
)


def _dest_for_root_json(name: str) -> Path | None:
    stem = Path(name).stem.lower()
    if stem.startswith("discovered_leagues"):
        return DS_METADATA / name
    for ent in KNOWN_ENTITY_PREFIXES:
        if stem == ent or stem.startswith(f"{ent}_"):
            return DATASET_ENTITY_DIRS[ent] / name
    return None


def _plan_move(src: Path, dst: Path, moves: list[tuple[Path, Path]]) -> None:
    if not src.exists():
        return
    if dst.resolve() == src.resolve():
        return
    moves.append((src, dst))


def _merge_directory_into(src: Path, dst: Path, moves: list[tuple[Path, Path]]) -> None:
    """Move every child of *src* into *dst* (planned as individual moves)."""
    if not src.is_dir():
        return
    for child in src.iterdir():
        _plan_move(child, dst / child.name, moves)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate data/ to functional layout.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    ensure_data_tree()
    moves: list[tuple[Path, Path]] = []

    # Singular typo: data/dataset/ → data/datasets/
    wrong_datasets = DATA_DIR / "dataset"
    if wrong_datasets.is_dir():
        _merge_directory_into(wrong_datasets, DATASETS_ROOT, moves)

    # Legacy: data/<entity>/ (directory) → data/datasets/<entity>/
    for ent in KNOWN_ENTITY_PREFIXES:
        legacy = DATA_DIR / ent
        if not legacy.is_dir():
            continue
        # Skip if already the canonical path
        if legacy.resolve() == DATASET_ENTITY_DIRS[ent].resolve():
            continue
        _merge_directory_into(legacy, DATASET_ENTITY_DIRS[ent], moves)

    # Root-level JSON → datasets/
    if DATA_DIR.is_dir():
        for p in DATA_DIR.iterdir():
            if not p.is_file() or p.suffix.lower() != ".json":
                continue
            dest = _dest_for_root_json(p.name)
            if dest is None:
                continue
            _plan_move(p, dest, moves)

    # Cache root JSON → seasons / clubs
    old_cache = DATA_DIR / "cache"
    if old_cache.is_dir():
        for p in old_cache.iterdir():
            if not p.is_file() or p.suffix.lower() != ".json":
                continue
            if p.name.startswith("season_data"):
                _plan_move(p, CACHE_SEASONS / p.name, moves)
            elif p.name.startswith("tm_club"):
                _plan_move(p, CACHE_CLUBS / p.name, moves)

    # De-duplicate planned moves (same src)
    seen_src: set[Path] = set()
    deduped: list[tuple[Path, Path]] = []
    for s, d in moves:
        rp = s.resolve()
        if rp in seen_src:
            continue
        seen_src.add(rp)
        deduped.append((s, d))
    moves = deduped

    if not moves:
        print("Nothing to migrate - layout already matches common/data_paths.py.")
        return

    print(f"Planned moves: {len(moves)}")
    for src, dst in moves:
        print(f"  {src.relative_to(ROOT)} -> {dst.relative_to(ROOT)}")

    if args.dry_run:
        print("\nDry run — no changes.")
        return

    for src, dst in moves:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            print(f"  SKIP (dest exists): {dst.relative_to(ROOT)}")
            continue
        shutil.move(str(src), str(dst))

    # Remove empty legacy dirs
    if wrong_datasets.is_dir() and not any(wrong_datasets.iterdir()):
        wrong_datasets.rmdir()
        print(f"  Removed empty {wrong_datasets.relative_to(ROOT)}")
    for ent in KNOWN_ENTITY_PREFIXES:
        legacy = DATA_DIR / ent
        if legacy.is_dir() and legacy.resolve() != DATASET_ENTITY_DIRS[ent].resolve():
            try:
                if not any(legacy.iterdir()):
                    legacy.rmdir()
                    print(f"  Removed empty {legacy.relative_to(ROOT)}")
            except OSError:
                pass

    print("\nDone.")


if __name__ == "__main__":
    main()
