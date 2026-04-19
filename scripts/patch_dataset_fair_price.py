"""
Patch existing training dataset to add the `fair_price` feature.

Loads all dataset parts as raw JSON dicts, loads all valuations,
computes fair_price per (player_id, cutoff_date) using linear
extrapolation, and rewrites the full dataset as fresh parts.

Usage:
    python scripts/patch_dataset_fair_price.py
    python scripts/patch_dataset_fair_price.py --dry-run
    python scripts/patch_dataset_fair_price.py --cutoff-months 6
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tqdm import tqdm

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scraping.utils.helpers import list_json_bases, load_json, parse_date
from ml.feature_engineering import (
    DATASETS_DIR, _MAX_PART_BYTES, FAIR_PRICE_CAP,
)
from entities.valuation import Valuation


# ---------------------------------------------------------------------------
# Valuation loading & fair-price computation
# ---------------------------------------------------------------------------

def _load_all_valuations() -> Dict[str, List[Valuation]]:
    """Load all valuations grouped by player_id."""
    bases = list_json_bases("valuations_all_*.json")
    by_player: Dict[str, List[Valuation]] = {}
    for base in tqdm(bases, desc="Loading valuation files"):
        data = load_json(base)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    v = Valuation.from_dict(item)
                    by_player.setdefault(v.player_id, []).append(v)
    return by_player


def _compute_fair_prices_for_cutoff(
    by_player: Dict[str, List[Valuation]],
    cutoff_date: datetime,
) -> Dict[str, float]:
    """Fair price via linear extrapolation from the last 2 unique valuations <= cutoff.

    Deduplicates valuations by (date, amount) before extrapolating.
    Mirrors compute_fair_prices() from feature_engineering.py.
    """
    result: Dict[str, float] = {}
    for pid, vals in by_player.items():
        seen: set = set()
        pts: List[Tuple[datetime, float]] = []
        for v in vals:
            if v.valuation_amount is None:
                continue
            d = parse_date(v.valuation_date or "")
            if d is None or d > cutoff_date:
                continue
            key = (d, v.valuation_amount)
            if key not in seen:
                seen.add(key)
                pts.append(key)
        if not pts:
            continue
        pts.sort(key=lambda x: x[0])
        if len(pts) == 1:
            result[pid] = max(0.0, min(FAIR_PRICE_CAP, pts[0][1]))
            continue
        (d1, v1), (d2, v2) = pts[-2], pts[-1]
        span = (d2 - d1).total_seconds()
        if span == 0:
            result[pid] = max(0.0, min(FAIR_PRICE_CAP, v2))
            continue
        dt = (cutoff_date - d1).total_seconds()
        slope = (v2 - v1) / span
        result[pid] = max(0.0, min(FAIR_PRICE_CAP, v1 + slope * dt))
    return result


# ---------------------------------------------------------------------------
# Raw-dict dataset I/O (fast – no PlayerFeatures conversion)
# ---------------------------------------------------------------------------

def _get_part_paths(cutoff_months: int) -> List[Path]:
    stem = f"training_dataset_{cutoff_months}m"
    parts = sorted(DATASETS_DIR.glob(f"{stem}_part*.json"))
    if parts:
        return parts
    single = DATASETS_DIR / f"{stem}.json"
    if single.exists():
        return [single]
    return []


def _load_all_raw(cutoff_months: int) -> Tuple[dict, List[dict]]:
    """Load every part file and return (metadata, flat list of sample dicts)."""
    paths = _get_part_paths(cutoff_months)
    if not paths:
        return {}, []
    metadata: dict = {}
    samples: List[dict] = []
    for pp in tqdm(paths, desc="Loading dataset parts"):
        with open(pp, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not metadata:
            metadata = data.get("metadata", {})
        samples.extend(data.get("samples", []))
    return metadata, samples


def _save_raw_parts(
    metadata: dict,
    samples: List[dict],
    cutoff_months: int,
) -> None:
    """Write samples back into <=90 MB parts."""
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"training_dataset_{cutoff_months}m"
    base_path = DATASETS_DIR / f"{stem}.json"

    if base_path.exists():
        base_path.unlink()
    for old in DATASETS_DIR.glob(f"{stem}_part*.json"):
        old.unlink()

    metadata["num_samples"] = len(samples)
    metadata["created_at"] = datetime.now().isoformat()

    full_output = {"metadata": metadata, "samples": samples}
    full_blob = json.dumps(full_output, indent=2, default=str).encode("utf-8")

    if len(full_blob) <= _MAX_PART_BYTES:
        with open(base_path, "wb") as f:
            f.write(full_blob)
        print(f"  Saved single file: {base_path.name} ({len(full_blob)/1e6:.1f} MB)")
        return

    del full_blob
    num_parts = max(2, -(-len(samples) // 30_000))
    chunk_size = -(-len(samples) // num_parts)

    written = 0
    for i in tqdm(range(num_parts), desc="Writing parts"):
        chunk = samples[i * chunk_size : (i + 1) * chunk_size]
        if not chunk:
            break
        part_meta = {**metadata, "part": i + 1, "total_parts": num_parts}
        part_path = DATASETS_DIR / f"{stem}_part{i + 1}.json"
        with open(part_path, "w", encoding="utf-8") as f:
            json.dump({"metadata": part_meta, "samples": chunk}, f, indent=2, default=str)
        written += 1

    print(f"  Saved {written} part files")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _season_to_cutoff(season: str) -> Optional[datetime]:
    try:
        y = int(season.split("-")[0])
        return datetime(y, 7, 1)
    except (ValueError, IndexError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Patch training dataset with fair_price")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cutoff-months", type=int, default=12)
    args = parser.parse_args()
    cm: int = args.cutoff_months

    metadata, samples = _load_all_raw(cm)
    if not samples:
        print("No dataset found.")
        return
    print(f"  {len(samples)} samples loaded")

    # Collect unique cutoff dates
    season_set = {s.get("cutoff_season", "") for s in samples} - {""}
    s2c: Dict[str, datetime] = {}
    for s in sorted(season_set):
        cd = _season_to_cutoff(s)
        if cd:
            s2c[s] = cd
    print(f"  {len(s2c)} cutoff dates: {sorted(s2c.keys())}")

    # Load all valuations grouped by player
    print("\nLoading valuations...")
    by_player = _load_all_valuations()
    total_players = len(by_player)
    total_vals = sum(len(v) for v in by_player.values())
    print(f"  {total_players} players, {total_vals} valuations")

    # Compute fair_price for each cutoff
    print("\nComputing fair prices per cutoff...")
    fp_maps: Dict[datetime, Dict[str, float]] = {}
    for season, cutoff in tqdm(sorted(s2c.items()), desc="Fair prices per cutoff"):
        fp_maps[cutoff] = _compute_fair_prices_for_cutoff(by_player, cutoff)

    del by_player

    # Assign fair_price to each sample
    set_count = 0
    nan_count = 0
    for s in tqdm(samples, desc="Setting fair_price"):
        cutoff = s2c.get(s.get("cutoff_season", ""))
        pid = s.get("player_id", "")
        if cutoff and pid:
            fp = fp_maps.get(cutoff, {}).get(pid)
            if fp is not None:
                s["fair_price"] = fp
                set_count += 1
            else:
                s["fair_price"] = None
                nan_count += 1
        else:
            s["fair_price"] = None
            nan_count += 1

    pct = 100 * set_count / max(len(samples), 1)
    print(f"\n  fair_price set: {set_count} / {len(samples)} ({pct:.1f}%)")
    print(f"  fair_price NaN: {nan_count} / {len(samples)} ({100-pct:.1f}%)")

    if args.dry_run:
        print("  DRY RUN — not saved.")
    else:
        _save_raw_parts(metadata, samples, cm)
        print("  Done.")


if __name__ == "__main__":
    main()
