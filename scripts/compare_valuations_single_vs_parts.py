#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from tqdm import tqdm

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "json"


def _load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _normalize_to_items(data: Any, source: str) -> list[dict]:
    """
    Normalize supported JSON payloads into a flat list of dict items.

    Supported:
      - list[dict]
      - {"items": list[dict]}
      - {"metadata": ..., "items": list[dict]}
      - single dict record -> [dict]
    """
    if data is None:
        raise ValueError(f"{source}: data is None")

    if isinstance(data, dict):
        if "items" in data:
            items = data["items"]
            if not isinstance(items, list):
                raise ValueError(f"{source}: 'items' exists but is not a list")
        else:
            items = [data]
    elif isinstance(data, list):
        items = data
    else:
        raise ValueError(f"{source}: unsupported JSON root type: {type(data).__name__}")

    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(
                f"{source}: item at index {i} is not an object/dict "
                f"(got {type(item).__name__})"
            )

    return items


def _load_single(base_path: Path) -> list[dict] | None:
    if not base_path.exists():
        return None
    raw = _load_json(base_path)
    return _normalize_to_items(raw, str(base_path))


def _extract_part_number(path: Path, stem: str) -> int:
    match = re.fullmatch(rf"{re.escape(stem)}_part(\d+)\.json", path.name)
    if not match:
        raise ValueError(f"Unexpected part filename: {path.name}")
    return int(match.group(1))


def _load_parts(stem: str, dir_path: Path) -> list[dict] | None:
    parts = list(dir_path.glob(f"{stem}_part*.json"))
    if not parts:
        return None

    parts = sorted(parts, key=lambda p: _extract_part_number(p, stem))

    all_items: list[dict] = []
    for p in parts:
        raw = _load_json(p)
        items = _normalize_to_items(raw, str(p))
        all_items.extend(items)

    return all_items


def _record_signature(item: dict) -> str:
    """
    Canonical representation of the full record.
    Identical records -> identical signature.
    """
    return json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _short_label(item: dict | None) -> str:
    if item is None:
        return "MISSING"
    valuation_id = item.get("valuation_id", "N/A")
    player_id = item.get("player_id", "N/A")
    valuation_date = item.get("valuation_date") or item.get("date") or "N/A"
    return f"valuation_id={valuation_id}, player_id={player_id}, date={valuation_date}"


def _print_first_diff(s_item: dict | None, p_item: dict | None, reason: str) -> None:
    print("\nFirst difference found")
    print(f"Reason: {reason}")
    print(f"Single: {_short_label(s_item)}")
    print(f"Parts : {_short_label(p_item)}")

    print("\nSingle record:")
    if s_item is None:
        print("MISSING")
    else:
        print(json.dumps(s_item, ensure_ascii=False, indent=2, sort_keys=True))

    print("\nParts record:")
    if p_item is None:
        print("MISSING")
    else:
        print(json.dumps(p_item, ensure_ascii=False, indent=2, sort_keys=True))

    print()


def _dedupe_exact(items: list[dict], source_name: str) -> tuple[list[dict], int]:
    """
    Drop duplicates only when the whole record is exactly identical.
    Keeps first occurrence.
    Returns (deduped_items, num_removed).
    """
    seen: set[str] = set()
    deduped: list[dict] = []
    removed = 0

    for item in items:
        sig = _record_signature(item)
        if sig in seen:
            removed += 1
            continue
        seen.add(sig)
        deduped.append(item)

    if removed:
        print(f"{source_name}: removed {removed} exact duplicate records")

    return deduped, removed


def _build_signature_counts(items: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        sig = _record_signature(item)
        counts[sig] = counts.get(sig, 0) + 1
    return counts


def _build_signature_to_item(items: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for item in items:
        sig = _record_signature(item)
        if sig not in out:
            out[sig] = item
    return out


def compare(base: str, dir_a: Path, dir_b: Path) -> tuple[bool, str]:
    """
    Compare single-file data in dir_a with part-file data in dir_b.

    Logic:
      - load both
      - drop exact duplicate records (same full content)
      - compare remaining records by full-record signature
      - order is ignored
    """
    stem = base.removesuffix(".json")
    single_path = dir_a / f"{stem}.json"

    try:
        single_data = _load_single(single_path)
        parts_data = _load_parts(stem, dir_b)
    except ValueError as e:
        return False, f"Invalid JSON structure: {e}"
    except json.JSONDecodeError as e:
        return False, f"JSON parse error: {e}"
    except OSError as e:
        return False, f"File read error: {e}"

    if single_data is None and parts_data is None:
        return False, f"No data found: single={single_path} parts={stem}_part*.json in {dir_b}"
    if single_data is None:
        return False, f"Single file missing: {single_path}"
    if parts_data is None:
        return False, f"Part files missing: {dir_b / (stem + '_part*.json')}"

    original_n_single = len(single_data)
    original_n_parts = len(parts_data)

    single_data, removed_single = _dedupe_exact(single_data, "single")
    parts_data, removed_parts = _dedupe_exact(parts_data, "parts")

    n_single = len(single_data)
    n_parts = len(parts_data)

    if n_single != n_parts:
        return (
            False,
            "Length mismatch after dropping exact duplicates: "
            f"single={n_single}, parts={n_parts} "
            f"(original single={original_n_single}, parts={original_n_parts})"
        )

    single_counts = _build_signature_counts(single_data)
    parts_counts = _build_signature_counts(parts_data)

    single_sig_to_item = _build_signature_to_item(single_data)
    parts_sig_to_item = _build_signature_to_item(parts_data)

    single_sigs = set(single_counts.keys())
    parts_sigs = set(parts_counts.keys())

    if single_sigs != parts_sigs:
        only_single = list(single_sigs - parts_sigs)
        only_parts = list(parts_sigs - single_sigs)

        if only_single:
            sig = only_single[0]
            _print_first_diff(single_sig_to_item[sig], None, "present only in single after exact dedupe")
        elif only_parts:
            sig = only_parts[0]
            _print_first_diff(None, parts_sig_to_item[sig], "present only in parts after exact dedupe")

        return (
            False,
            f"Record mismatch after dropping exact duplicates: "
            f"{len(only_single)} unique records only in single, "
            f"{len(only_parts)} unique records only in parts"
        )

    # Same unique signatures; compare counts just in case
    # (after exact dedupe they should all be 1, but this keeps the logic explicit)
    for sig in tqdm(sorted(single_sigs), desc="Comparing records", unit="record"):
        s_count = single_counts[sig]
        p_count = parts_counts[sig]

        if s_count != p_count:
            _print_first_diff(
                single_sig_to_item.get(sig),
                parts_sig_to_item.get(sig),
                f"different multiplicity after exact dedupe (single={s_count}, parts={p_count})",
            )
            return False, f"Count mismatch for a record after dedupe: single={s_count}, parts={p_count}"

    return (
        True,
        "OK: records match after dropping exact duplicates "
        f"(single removed={removed_single}, parts removed={removed_parts}, final={n_single})"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="Compare valuations single vs parts")
    ap.add_argument("--season", default="2024-2025", help="Season (e.g. 2024-2025)")
    ap.add_argument("--dir-a", type=Path, default=None, help="Dir with single .json file")
    ap.add_argument("--dir-b", type=Path, default=None, help="Dir with _part*.json files")
    args = ap.parse_args()

    base = f"valuations_all_{args.season}"
    dir_a = (args.dir_a or DATA_DIR).resolve()
    dir_b = (args.dir_b or DATA_DIR).resolve()

    if dir_a == dir_b:
        single_path = dir_a / f"{base}.json"
        parts = list(dir_a.glob(f"{base}_part*.json"))

        if single_path.exists() and parts:
            ok, msg = compare(base, dir_a, dir_b)
        elif single_path.exists():
            try:
                single_data = _load_single(single_path)
                ok, msg = True, f"Only single file exists: {len(single_data or [])} records (no parts to compare)"
            except Exception as e:
                ok, msg = False, f"Could not read single file: {e}"
        elif parts:
            try:
                parts_data = _load_parts(base, dir_a)
                ok, msg = True, f"Only parts exist: {len(parts_data or [])} records (no single to compare)"
            except Exception as e:
                ok, msg = False, f"Could not read part files: {e}"
        else:
            ok, msg = False, f"No data found for {base} in {dir_a}"
    else:
        ok, msg = compare(base, dir_a, dir_b)

    print(msg)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()