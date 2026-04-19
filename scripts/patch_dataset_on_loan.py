"""
Patch existing training dataset to add the `on_loan` feature.

Loads all dataset parts as raw JSON dicts (avoids expensive PlayerFeatures
roundtrip), determines loan status per (player_id, cutoff) from transfer
files, sets `on_loan`, and rewrites the full dataset as fresh parts.

Usage:
    python scripts/patch_dataset_on_loan.py
    python scripts/patch_dataset_on_loan.py --dry-run
    python scripts/patch_dataset_on_loan.py --cutoff-months 6
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tqdm import tqdm

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scraping.utils.helpers import list_json_bases, load_json, parse_date
from ml.feature_engineering import DATASETS_DIR, _MAX_PART_BYTES


# ---------------------------------------------------------------------------
# Transfer loading & loan-map building
# ---------------------------------------------------------------------------

def _load_and_parse_transfers() -> List[Tuple[datetime, str, bool, str]]:
    """Load all transfers, return sorted list of (date, player_id, is_loan, type)."""
    bases = list_json_bases("transfers_all_*.json")
    raw: List[dict] = []
    for base in tqdm(bases, desc="Loading transfer files"):
        data = load_json(base)
        if isinstance(data, list):
            raw.extend(item for item in data if isinstance(item, dict))

    parsed: List[Tuple[datetime, str, bool, str]] = []
    for t in tqdm(raw, desc="Parsing transfers"):
        td = parse_date(t.get("transfer_date", ""))
        if td is None:
            continue
        pid = str(t.get("player_id", ""))
        if not pid:
            continue
        parsed.append((td, pid, bool(t.get("is_loan", False)), t.get("transfer_type", "")))
    del raw
    parsed.sort(key=lambda x: x[0])
    return parsed


def _build_loan_maps(
    transfers: List[Tuple[datetime, str, bool, str]],
    cutoffs: List[datetime],
) -> Dict[datetime, Dict[str, bool]]:
    """Single-pass: for each cutoff → {player_id: True} if on loan."""
    sorted_cutoffs = sorted(cutoffs)
    result: Dict[datetime, Dict[str, bool]] = {}
    best: Dict[str, Tuple[datetime, bool, str]] = {}
    t_idx = 0
    for cutoff in tqdm(sorted_cutoffs, desc="Building loan maps"):
        while t_idx < len(transfers) and transfers[t_idx][0] <= cutoff:
            td, pid, is_loan, ttype = transfers[t_idx]
            prev = best.get(pid)
            if prev is None or td >= prev[0]:
                best[pid] = (td, is_loan, ttype)
            t_idx += 1
        result[cutoff] = {
            pid: True
            for pid, (_, il, tt) in best.items()
            if il and tt == "loan_out"
        }
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
    """Write samples back into ≤90 MB parts (mirrors save_training_dataset)."""
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    stem = f"training_dataset_{cutoff_months}m"
    base_path = DATASETS_DIR / f"{stem}.json"

    # Clean old files
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
    parser = argparse.ArgumentParser(description="Patch training dataset with on_loan")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cutoff-months", type=int, default=12)
    args = parser.parse_args()
    cm: int = args.cutoff_months

    metadata, samples = _load_all_raw(cm)
    if not samples:
        print("No dataset found.")
        return
    print(f"  {len(samples)} samples loaded")

    season_set = {s.get("cutoff_season", "") for s in samples} - {""}
    s2c: Dict[str, datetime] = {}
    for s in sorted(season_set):
        cd = _season_to_cutoff(s)
        if cd:
            s2c[s] = cd
    print(f"  {len(s2c)} cutoff dates")

    transfers = _load_and_parse_transfers()
    loan_maps = _build_loan_maps(transfers, list(s2c.values()))
    del transfers

    on_loan_count = 0
    for s in tqdm(samples, desc="Setting on_loan"):
        cutoff = s2c.get(s.get("cutoff_season", ""))
        pid = s.get("player_id", "")
        is_on = bool(cutoff and pid and loan_maps.get(cutoff, {}).get(pid, False))
        s["on_loan"] = is_on
        if is_on:
            on_loan_count += 1

    pct = 100 * on_loan_count / max(len(samples), 1)
    print(f"\n  on_loan: {on_loan_count} / {len(samples)} ({pct:.1f}%)")

    if args.dry_run:
        print("  DRY RUN — not saved.")
    else:
        _save_raw_parts(metadata, samples, cm)
        print("  Done.")


if __name__ == "__main__":
    main()
