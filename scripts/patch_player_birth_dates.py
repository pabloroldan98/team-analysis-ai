"""
Patch invalid ``birth_date`` values in player data.

Scans every ``players_all_*.json`` file and every
``season_data_*.json`` cache file, finds players whose ``birth_date``
is not a canonical date (``DD/MM/YYYY`` or ``YYYY-MM-DD``), queries the
Transfermarkt tmapi endpoint

    https://tmapi-alpha.transfermarkt.technology/player/<player_id>

for each of them and overwrites the stored ``birth_date`` with
``data.lifeDates.dateOfBirth`` normalised to ``DD/MM/YYYY``. Entries
where the API confirms the date of birth is unknown are set to
``"Unknown"``; otherwise the original (unparseable) value is left
untouched so the next scrape pass can try again.

After patching birth dates the script recomputes ``age`` for every
player in every file using that file's season cutoff (``01/07`` of the
starting year, or ``datetime.now()`` for ``season_data_today.json``).

Usage::

    python scripts/patch_player_birth_dates.py
    python scripts/patch_player_birth_dates.py --dry-run
    python scripts/patch_player_birth_dates.py --no-api   # only recompute ages
    python scripts/patch_player_birth_dates.py --limit 50 # patch first N bad ids
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import requests
from tqdm import tqdm

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scraping.utils.helpers import (
    DATA_DIR,
    list_json_bases,
    load_json,
    save_json_with_parts,
)

# ── Configuration ───────────────────────────────────────────────────────
TM_API_URL = "https://tmapi-alpha.transfermarkt.technology"
MAX_RETRIES = 5
RETRY_PAUSE = 10        # seconds between retries
REQUEST_DELAY = 0.3     # polite delay between API requests

UNKNOWN = "Unknown"
CACHE_DIR = DATA_DIR / "cache"
TODAY_STEM = "season_data_today"

_VALID_FORMATS = ("%d/%m/%Y", "%Y-%m-%d")


# ── Helpers ─────────────────────────────────────────────────────────────

def _is_canonical_birth_date(value: Any) -> bool:
    """True if the value is already a real parseable date (any canonical form)."""
    if value is None or not isinstance(value, str):
        return False
    s = value.strip()
    if not s:
        return False
    for fmt in _VALID_FORMATS:
        try:
            datetime.strptime(s, fmt)
            return True
        except ValueError:
            continue
    return False


def _needs_patch(value: Any) -> bool:
    """A value needs patching when it's neither canonical nor the explicit
    ``Unknown`` marker (``Unknown`` means already confirmed via API)."""
    if value == UNKNOWN:
        return False
    return not _is_canonical_birth_date(value)


def _compute_age(birth_date: Any, cutoff: datetime) -> Optional[int]:
    if not _is_canonical_birth_date(birth_date):
        return None
    for fmt in _VALID_FORMATS:
        try:
            bd = datetime.strptime(birth_date, fmt)
        except ValueError:
            continue
        age = cutoff.year - bd.year
        if (cutoff.month, cutoff.day) < (bd.month, bd.day):
            age -= 1
        return max(0, age)
    return None


def _season_cutoff_from_stem(stem: str) -> Optional[datetime]:
    """Extract a season cutoff from stems like ``players_all_2024-2025``
    or ``season_data_2024-2025`` or ``season_data_today``."""
    if stem.endswith("_today") or stem == TODAY_STEM:
        return datetime.now()
    m = re.search(r"(\d{4})-\d{4}", stem)
    if m:
        return datetime(int(m.group(1)), 7, 1)
    return None


# ── API ─────────────────────────────────────────────────────────────────

def _api_get_player(player_id: str) -> Optional[dict]:
    """GET ``/player/<id>`` with retries. Returns parsed JSON or None."""
    url = f"{TM_API_URL}/player/{player_id}"
    last_code: Optional[int] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            time.sleep(REQUEST_DELAY)
            resp = requests.get(url, timeout=60)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code in (429, 500, 502, 503, 504):
                last_code = resp.status_code
                tqdm.write(
                    f"    [{player_id}] attempt {attempt}/{MAX_RETRIES}: "
                    f"HTTP {resp.status_code}"
                )
            else:
                tqdm.write(f"    [{player_id}] HTTP {resp.status_code} – giving up")
                return None
        except Exception as exc:
            last_code = last_code or 429
            tqdm.write(f"    [{player_id}] attempt {attempt}/{MAX_RETRIES}: {exc!r}")
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_PAUSE)
    return None


def _extract_birth_date(api_payload: dict) -> Optional[str]:
    """Pull ``data.lifeDates.dateOfBirth`` (YYYY-MM-DD) and convert to DD/MM/YYYY.

    Returns ``UNKNOWN`` when the API explicitly states the date is unknown,
    an empty string when the API response is missing / malformed, or the
    canonical date string otherwise."""
    if not isinstance(api_payload, dict):
        return ""
    if api_payload.get("success") is False:
        return ""

    data = api_payload.get("data")
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return ""

    life = data.get("lifeDates") or {}
    if life.get("isDateOfBirthUnknown"):
        return UNKNOWN
    raw = life.get("dateOfBirth")
    if not raw:
        return UNKNOWN
    try:
        return datetime.strptime(str(raw), "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return ""


# ── Players-all files ───────────────────────────────────────────────────

PlayersFileRecord = Tuple[str, List[dict]]  # (base_name, records)


def _load_players_all_files() -> List[PlayersFileRecord]:
    out: List[PlayersFileRecord] = []
    bases = list_json_bases("players_all_*.json")
    for base in tqdm(bases, desc="Loading players_all files", unit="file"):
        raw = load_json(base)
        if raw is None:
            continue
        records = raw["items"] if isinstance(raw, dict) and "items" in raw else raw
        if not isinstance(records, list):
            continue
        out.append((base, records))
    return out


# ── Cache files (season_data_*.json) ────────────────────────────────────

CacheFileRecord = Tuple[Path, dict]  # (file_path, full_payload_dict)


def _load_cache_files() -> List[CacheFileRecord]:
    if not CACHE_DIR.exists():
        return []
    out: List[CacheFileRecord] = []
    paths = sorted(CACHE_DIR.glob("season_data_*.json"))
    for path in tqdm(paths, desc="Loading cache files", unit="file"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as exc:
            tqdm.write(f"  SKIP {path.name}: {exc}")
            continue
        if isinstance(data, dict) and isinstance(data.get("players"), list):
            out.append((path, data))
    return out


def _save_cache_file(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    tmp.replace(path)


# ── Bad-id detection ────────────────────────────────────────────────────

def _collect_bad_ids(
    players_files: List[PlayersFileRecord],
    cache_files: List[CacheFileRecord],
) -> Set[str]:
    """Return every player_id whose birth_date is not canonical and not
    the explicit ``Unknown`` marker, seen anywhere in the data."""
    bad: Set[str] = set()

    for _base, records in players_files:
        for rec in records:
            pid = rec.get("player_id")
            if pid and _needs_patch(rec.get("birth_date")):
                bad.add(str(pid))

    for _path, payload in cache_files:
        for rec in payload.get("players", []):
            if not isinstance(rec, dict):
                continue
            pid = rec.get("player_id")
            if pid and _needs_patch(rec.get("birth_date")):
                bad.add(str(pid))

    return bad


# ── Apply patches ───────────────────────────────────────────────────────

def _apply_birth_dates(
    players_files: List[PlayersFileRecord],
    cache_files: List[CacheFileRecord],
    patches: Dict[str, str],
) -> Tuple[Set[str], Set[str]]:
    """Overwrite birth_date for every record whose player_id is in
    ``patches`` and whose current value still needs a patch. Returns the
    set of modified players_all bases and the set of modified cache
    paths (stringified)."""
    modified_bases: Set[str] = set()
    modified_caches: Set[str] = set()

    for base, records in players_files:
        changed = False
        for rec in records:
            pid = str(rec.get("player_id") or "")
            new_bd = patches.get(pid)
            if not new_bd:
                continue
            cur = rec.get("birth_date")
            # Overwrite whenever the new value is different AND the current
            # one is not already canonical with the same day/month/year.
            # We only ever "upgrade" values flagged by _needs_patch; keep
            # existing good values untouched.
            if _needs_patch(cur) or (cur == UNKNOWN and new_bd != UNKNOWN):
                if cur != new_bd:
                    rec["birth_date"] = new_bd
                    changed = True
        if changed:
            modified_bases.add(base)

    for path, payload in cache_files:
        changed = False
        for rec in payload.get("players", []):
            if not isinstance(rec, dict):
                continue
            pid = str(rec.get("player_id") or "")
            new_bd = patches.get(pid)
            if not new_bd:
                continue
            cur = rec.get("birth_date")
            if _needs_patch(cur) or (cur == UNKNOWN and new_bd != UNKNOWN):
                if cur != new_bd:
                    rec["birth_date"] = new_bd
                    changed = True
        if changed:
            modified_caches.add(str(path))

    return modified_bases, modified_caches


def _recompute_all_ages(
    players_files: List[PlayersFileRecord],
    cache_files: List[CacheFileRecord],
) -> Tuple[Set[str], Set[str]]:
    """Recompute ``age`` in every record using each file's season cutoff."""
    modified_bases: Set[str] = set()
    modified_caches: Set[str] = set()

    for base, records in tqdm(players_files, desc="Recomputing ages (players_all)", unit="file"):
        cutoff = _season_cutoff_from_stem(base)
        if cutoff is None:
            continue
        changed = False
        for rec in records:
            new_age = _compute_age(rec.get("birth_date"), cutoff)
            if new_age is None:
                # Don't wipe age — may have come from another source. Only
                # overwrite when birth_date is parseable.
                continue
            if rec.get("age") != new_age:
                rec["age"] = new_age
                changed = True
        if changed:
            modified_bases.add(base)

    for path, payload in tqdm(cache_files, desc="Recomputing ages (cache)", unit="file"):
        stem = path.stem  # e.g. "season_data_2024-2025" or "season_data_today"
        cutoff = _season_cutoff_from_stem(stem)
        if cutoff is None:
            continue
        changed = False
        for rec in payload.get("players", []):
            if not isinstance(rec, dict):
                continue
            new_age = _compute_age(rec.get("birth_date"), cutoff)
            if new_age is None:
                continue
            if rec.get("age") != new_age:
                rec["age"] = new_age
                changed = True
        if changed:
            modified_caches.add(str(path))

    return modified_bases, modified_caches


# ── Writing ─────────────────────────────────────────────────────────────

def _write_players_files(
    players_files: List[PlayersFileRecord],
    bases_to_write: Set[str],
) -> None:
    if not bases_to_write:
        return
    for base, records in tqdm(players_files, desc="Writing players_all files", unit="file"):
        if base in bases_to_write:
            save_json_with_parts(records, base)


def _write_cache_files(
    cache_files: List[CacheFileRecord],
    paths_to_write: Set[str],
) -> None:
    if not paths_to_write:
        return
    for path, payload in tqdm(cache_files, desc="Writing cache files", unit="file"):
        if str(path) in paths_to_write:
            _save_cache_file(path, payload)


# ── Main ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Patch invalid player birth_date values via the TM API.",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Detect and query, but don't write any file.")
    parser.add_argument("--no-api", action="store_true",
                        help="Skip API calls. Only recompute ages.")
    parser.add_argument("--limit", type=int, default=0,
                        help="If > 0, only patch the first N bad ids (debug).")
    args = parser.parse_args()

    if not DATA_DIR.exists():
        print(f"ERROR: {DATA_DIR} not found.")
        return

    # ── 1. Load ──────────────────────────────────────────────────────
    players_files = _load_players_all_files()
    cache_files = _load_cache_files()
    print(
        f"Loaded {len(players_files)} players_all file(s) and "
        f"{len(cache_files)} cache file(s)."
    )
    if not players_files and not cache_files:
        print("Nothing to patch.")
        return

    # ── 2. Detect bad ids ────────────────────────────────────────────
    bad_ids = _collect_bad_ids(players_files, cache_files)
    print(f"  {len(bad_ids)} players with non-canonical birth_date.")

    # ── 3. Fetch from API ────────────────────────────────────────────
    patches: Dict[str, str] = {}
    if bad_ids and not args.no_api:
        ids = sorted(bad_ids)
        if args.limit and args.limit > 0:
            ids = ids[: args.limit]
            print(f"  --limit {args.limit} → fetching {len(ids)} ids only.")

        stats = {"ok": 0, "unknown": 0, "missing": 0, "failed": 0}
        for pid in tqdm(ids, desc="Fetching from API", unit="player"):
            payload = _api_get_player(pid)
            if payload is None:
                stats["failed"] += 1
                continue
            bd = _extract_birth_date(payload)
            if bd == UNKNOWN:
                patches[pid] = UNKNOWN
                stats["unknown"] += 1
            elif bd:
                patches[pid] = bd
                stats["ok"] += 1
            else:
                stats["missing"] += 1
        print(
            f"\nAPI results → ok: {stats['ok']}, unknown: {stats['unknown']}, "
            f"missing: {stats['missing']}, failed: {stats['failed']}"
        )

    # ── 4. Apply birth_date patches ──────────────────────────────────
    modified_bases: Set[str] = set()
    modified_caches: Set[str] = set()
    if patches:
        mb, mc = _apply_birth_dates(players_files, cache_files, patches)
        modified_bases |= mb
        modified_caches |= mc
        print(f"  Birth dates updated in {len(mb)} players_all file(s) "
              f"and {len(mc)} cache file(s).")

    # ── 5. Recompute ages everywhere ─────────────────────────────────
    mb, mc = _recompute_all_ages(players_files, cache_files)
    modified_bases |= mb
    modified_caches |= mc
    print(
        f"  Ages refreshed in {len(mb)} players_all file(s) "
        f"and {len(mc)} cache file(s)."
    )

    # ── 6. Write ─────────────────────────────────────────────────────
    if args.dry_run:
        print(
            f"\n[DRY RUN] Would write {len(modified_bases)} players_all file(s) "
            f"and {len(modified_caches)} cache file(s)."
        )
        return

    _write_players_files(players_files, modified_bases)
    _write_cache_files(cache_files, modified_caches)
    print("\nDone.")


if __name__ == "__main__":
    main()
