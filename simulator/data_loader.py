"""
Load teams and players from JSON data.

Player team assignment is determined by transfers (not valuations).
The pipeline is:

1. Load ALL players from every ``players_all_*.json`` file.
2. Load ALL transfers from every ``transfers_all_*.json`` file.
   For each player find the last transfer whose date <= 01/07/{start_year}.
   Use that transfer to set the player's current team (``to_club``).
   Also track whether the player is on loan.
3. Filter out players whose team is "Retired", "Without Club", etc.
4. Load ALL valuations from every ``valuations_all_*.json`` file.
   For each player find the last valuation whose date <= 01/07/{start_year}.
   Update ``market_value`` and ``age``.
"""
from __future__ import annotations

import functools
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from tqdm import tqdm

from scraping.utils.helpers import list_json_bases, load_json, parse_date, DATA_DIR
from entities.player import Player
from entities.transfer import Transfer
from entities.valuation import Valuation

# Precomputed season cache (see scripts/precompute_active_players_cache.py)
CACHE_DIR = DATA_DIR / "cache"
CACHE_PREFIX = "season_data"

# Maximum JSON size per cache part (90 MB keeps headroom under GitHub's 100 MB).
# Caches > 100 MB fail to push, so we shard automatically into ``*_partN.json``.
_MAX_CACHE_PART_BYTES = 90 * 1024 * 1024


class _NumpyEncoder(json.JSONEncoder):
    """JSON encoder that accepts numpy scalars/arrays (match legacy cache writer)."""

    def default(self, obj):  # type: ignore[override]
        try:
            import numpy as _np
        except ImportError:
            return super().default(obj)
        if isinstance(obj, _np.integer):
            return int(obj)
        if isinstance(obj, _np.floating):
            return float(obj)
        if isinstance(obj, _np.ndarray):
            return obj.tolist()
        return super().default(obj)


# ---------------------------------------------------------------------------
# Cache path helpers (single file OR ``*_partN.json`` parts)
# ---------------------------------------------------------------------------

def _cache_base_path(season: str) -> Path:
    """Return the base (non-partitioned) cache path for a season."""
    stem = (
        f"{CACHE_PREFIX}_today"
        if season.lower() == "today"
        else f"{CACHE_PREFIX}_{season}"
    )
    return CACHE_DIR / f"{stem}.json"


def _cache_part_paths(base_path: Path) -> List[Path]:
    """Return sorted list of existing cache files for ``base_path``.

    Prefers ``<stem>_part1.json``, ``<stem>_part2.json``, … when present;
    falls back to the single ``<stem>.json`` file if no parts exist.
    Returns an empty list when neither exists.
    """
    stem = base_path.stem  # e.g. "season_data_2024-2025"
    parts = sorted(base_path.parent.glob(f"{stem}_part*.json"))
    if parts:
        return parts
    if base_path.exists():
        return [base_path]
    return []


def list_cached_seasons(include_today: bool = False) -> List[str]:
    """Return unique season strings that have a cache on disk.

    Collapses parts (``season_data_2024-2025_part3.json``) down to their
    base season and de-duplicates. Skips ``today`` unless *include_today*
    is ``True``. Result is sorted in reverse chronological order.
    """
    if not CACHE_DIR.exists():
        return []
    seen: set = set()
    for p in CACHE_DIR.glob(f"{CACHE_PREFIX}_*.json"):
        stem = p.stem  # season_data_XXXX-XXXX[_partN]
        # Strip trailing "_partN" if present
        part_idx = stem.rfind("_part")
        if part_idx != -1 and stem[part_idx + 5 :].isdigit():
            stem = stem[:part_idx]
        season = stem[len(CACHE_PREFIX) + 1 :]  # drop "season_data_"
        if not season:
            continue
        if season == "today" and not include_today:
            continue
        seen.add(season)
    return sorted(seen, reverse=True)


# ---------------------------------------------------------------------------
# Cache save / load (multi-part aware)
# ---------------------------------------------------------------------------

def _clean_existing_cache_files(base_path: Path) -> None:
    """Remove the legacy single-file AND any existing ``_partN`` siblings."""
    if base_path.exists():
        base_path.unlink()
    for old in base_path.parent.glob(f"{base_path.stem}_part*.json"):
        old.unlink()


def _split_horizon_predictions(
    horizon_preds: Optional[dict],
    pids_in_chunk: set,
) -> dict:
    """Return a copy of ``horizon_preds`` restricted to ``pids_in_chunk``."""
    if not isinstance(horizon_preds, dict):
        return {}
    out: dict = {}
    for hz_key, hz_val in horizon_preds.items():
        if not isinstance(hz_val, dict):
            continue
        pv = hz_val.get("predicted_values") or {}
        fp = hz_val.get("fair_prices") or {}
        out[hz_key] = {
            "predicted_values": {pid: v for pid, v in pv.items() if pid in pids_in_chunk},
            "fair_prices": {pid: v for pid, v in fp.items() if pid in pids_in_chunk},
        }
    return out


def save_season_cache_payload(payload: dict, season: str) -> Path:
    """
    Persist a precomputed-season cache payload as one file when it fits
    under ``_MAX_CACHE_PART_BYTES`` or as ``*_partN.json`` parts otherwise.

    Mirrors the single/multi-part convention used for training datasets
    (``ml/feature_engineering.save_training_dataset``).

    The split is performed **per player**: each part receives a contiguous
    chunk of ``payload["players"]`` plus the matching slice of
    ``payload["horizon_predictions"][*]["predicted_values" / "fair_prices"]``.
    Small aggregate data (``team_market_values``, ``athletic_eligible_ids``)
    is written in part 1 only; the loader merges them back.

    Returns the path to the single file or to part 1 when split.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    base_path = _cache_base_path(season)

    full_blob = json.dumps(payload, ensure_ascii=False, cls=_NumpyEncoder).encode("utf-8")

    if len(full_blob) <= _MAX_CACHE_PART_BYTES:
        _clean_existing_cache_files(base_path)
        with open(base_path, "wb") as f:
            f.write(full_blob)
        return base_path

    _clean_existing_cache_files(base_path)

    players: List[dict] = payload.get("players") or []
    horizon_preds = payload.get("horizon_predictions")

    # Conservative estimate of parts needed (ceil)
    num_parts = max(2, -(-len(full_blob) // _MAX_CACHE_PART_BYTES))
    chunk_size = -(-len(players) // num_parts) if players else 0

    part_paths: List[Path] = []
    for i in range(num_parts):
        chunk = players[i * chunk_size : (i + 1) * chunk_size] if chunk_size else []
        if not chunk and i > 0:
            break

        pids_in_chunk = {
            str(p.get("player_id"))
            for p in chunk
            if isinstance(p, dict) and p.get("player_id") is not None
        }

        part_payload: dict = {
            "season": payload.get("season"),
            "computed_date": payload.get("computed_date"),
            "player_count": payload.get("player_count"),
            "team_count": payload.get("team_count"),
            "athletic_eligible_count": payload.get("athletic_eligible_count"),
            "part": i + 1,
            "total_parts": num_parts,
            "players": chunk,
            "horizon_predictions": _split_horizon_predictions(horizon_preds, pids_in_chunk),
        }
        # Small shared data lives in part 1 only (deduplicated on load).
        if i == 0:
            if "team_market_values" in payload:
                part_payload["team_market_values"] = payload["team_market_values"]
            if "athletic_eligible_ids" in payload:
                part_payload["athletic_eligible_ids"] = payload["athletic_eligible_ids"]

        part_path = base_path.parent / f"{base_path.stem}_part{i + 1}.json"
        with open(part_path, "w", encoding="utf-8") as f:
            json.dump(part_payload, f, ensure_ascii=False, cls=_NumpyEncoder)
        part_paths.append(part_path)

    return part_paths[0] if part_paths else base_path


def _load_raw_season_cache(season: str) -> Optional[dict]:
    """
    Load the raw (unparsed) cache payload for a season, transparently
    merging ``_partN.json`` files when present.

    Returns ``None`` when no file exists or the payload is malformed.
    Matches the legacy single-file structure so callers don't need to
    know whether it was stored sharded.
    """
    base_path = _cache_base_path(season)
    paths = _cache_part_paths(base_path)
    if not paths:
        return None

    # Legacy single file
    if len(paths) == 1 and paths[0] == base_path:
        try:
            with open(paths[0], encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    merged: Optional[dict] = None
    for pp in paths:
        try:
            with open(pp, encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
        if merged is None:
            merged = {
                k: v
                for k, v in data.items()
                if k not in ("part", "total_parts", "players", "horizon_predictions")
            }
            merged["players"] = []
            merged["horizon_predictions"] = {}

        players_chunk = data.get("players") or []
        if isinstance(players_chunk, list):
            merged["players"].extend(players_chunk)

        hp = data.get("horizon_predictions") or {}
        if isinstance(hp, dict):
            for hz_key, hz_val in hp.items():
                if not isinstance(hz_val, dict):
                    continue
                bucket = merged["horizon_predictions"].setdefault(
                    hz_key, {"predicted_values": {}, "fair_prices": {}}
                )
                bucket["predicted_values"].update(hz_val.get("predicted_values") or {})
                bucket["fair_prices"].update(hz_val.get("fair_prices") or {})

        # Small data lives in part 1; copy the first occurrence we see.
        for k in ("team_market_values", "athletic_eligible_ids"):
            if k in data and k not in merged:
                merged[k] = data[k]

    return merged


@functools.lru_cache(maxsize=20000)
def _parse_date_cached(date_str: str) -> Optional[datetime]:
    """Cached parse_date for repeated date strings (e.g. in transfers/valuations)."""
    return parse_date(date_str)


# Team IDs that represent "out-of-football" destinations
EXCLUDED_TEAM_IDS = {
    "123",   # Retired
    # "515",   # Without Club
    # "2113",  # Career break
}

EXCLUDED_TEAM_NAMES = {
    "retired",
    # "without club",
    # "career break",
}


TODAY_SEASON = "today"


def _get_season_start_date(season: str) -> datetime:
    """Return 01/07 of the starting year of a season like '2023-2024'.

    If *season* is ``"today"``, returns ``datetime.now()`` (the squad
    snapshot is taken as-of right now).
    """
    if season.lower() == TODAY_SEASON:
        return datetime.now()
    start_year = int(season.split("-")[0])
    return datetime(start_year, 7, 1)


# ── Bulk loaders (all files) ────────────────────────────────────────────

def _load_all_players(verbose: bool = False) -> Dict[str, Player]:
    """
    Load ALL ``players_all_*.json`` files.
    Supports single and multi-part files (when >90MB).

    Returns a dict keyed by ``player_id``.  When a player appears in
    multiple season files we keep the entry from the latest file (by
    filename sort).
    """
    players: Dict[str, Player] = {}
    bases = list_json_bases("players_all_*.json")
    base_iter = tqdm(bases, desc="Loading players", disable=not verbose)

    for base in base_iter:
        if verbose:
            base_iter.set_postfix_str(base)
        data = load_json(base)
        if not isinstance(data, list):
            continue
        for item in tqdm(data, desc=f"  {base}", disable=not verbose, leave=False):
            if not isinstance(item, dict):
                continue
            p = Player.from_dict(item)
            players[p.player_id] = p  # later file overwrites earlier

    return players


def _load_all_transfers() -> List[Transfer]:
    """Load ALL ``transfers_all_*.json`` files into a flat list. Supports multi-part files."""
    transfers: List[Transfer] = []

    for base in list_json_bases("transfers_all_*.json"):
        data = load_json(base)
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            transfers.append(Transfer.from_dict(item))

    return transfers


def _load_all_valuations() -> List[Valuation]:
    """Load ALL ``valuations_all_*.json`` files into a flat list. Supports multi-part files."""
    valuations: List[Valuation] = []

    for base in list_json_bases("valuations_all_*.json"):
        data = load_json(base)
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            valuations.append(Valuation.from_dict(item))

    return valuations


def _load_transfer_map_at_cutoff(season: str, verbose: bool = False) -> Dict[str, Transfer]:
    """
    Build transfer_map (player_id -> last Transfer before cutoff) by iterating
    files once. Avoids loading millions of Transfer objects into memory.
    """
    cutoff = _get_season_start_date(season)
    best: Dict[str, Tuple[datetime, Transfer]] = {}
    bases = list_json_bases("transfers_all_*.json")
    base_iter = tqdm(bases, desc="Loading transfers", disable=not verbose)

    for base in base_iter:
        if verbose:
            base_iter.set_postfix_str(base)
        data = load_json(base)
        if not isinstance(data, list):
            continue
        for item in tqdm(data, desc=f"  {base}", disable=not verbose, leave=False):
            if not isinstance(item, dict):
                continue
            date_str = item.get("transfer_date") or ""
            td = _parse_date_cached(date_str)
            if td is None or td > cutoff:
                continue

            pid = item.get("player_id", "")
            if not pid:
                continue
            pid = str(pid)

            prev = best.get(pid)
            if prev is None or td > prev[0]:
                best[pid] = (td, Transfer.from_dict(item))

    return {pid: tr for pid, (_, tr) in best.items()}


def _load_valuation_map_at_cutoff(season: str, verbose: bool = False) -> Dict[str, float]:
    """
    Build player_id -> market_value map by iterating valuation files once.
    Only stores the amount (float); avoids full Valuation objects.
    """
    cutoff = _get_season_start_date(season)
    best: Dict[str, Tuple[datetime, float]] = {}
    bases = list_json_bases("valuations_all_*.json")
    base_iter = tqdm(bases, desc="Loading valuations", disable=not verbose)

    for base in base_iter:
        if verbose:
            base_iter.set_postfix_str(base)
        data = load_json(base)
        if not isinstance(data, list):
            continue
        for item in tqdm(data, desc=f"  {base}", disable=not verbose, leave=False):
            if not isinstance(item, dict):
                continue
            date_str = item.get("valuation_date") or ""
            vd = _parse_date_cached(date_str)
            if vd is None or vd > cutoff:
                continue

            pid = item.get("player_id", "")
            if not pid:
                continue
            pid = str(pid)

            amount = item.get("valuation_amount")
            if amount is None:
                continue
            try:
                amount = float(amount)
            except (TypeError, ValueError):
                continue

            prev = best.get(pid)
            if prev is None or vd > prev[0]:
                best[pid] = (vd, amount)

    return {pid: amt for pid, (_, amt) in best.items()}


# ── Season-level queries ─────────────────────────────────────────────────

def get_transfer_at_season_start(
    transfers: List[Transfer],
    season: str,
) -> Dict[str, Transfer]:
    """
    For each player return the most recent transfer whose date
    is **<= 01/07/{start_year}** (only 1 transfer per player).

    Args:
        transfers: Flat list of ALL transfers.
        season: e.g. "2023-2024"

    Returns:
        Dict ``player_id -> Transfer``
    """
    cutoff = _get_season_start_date(season)

    best: Dict[str, Tuple[datetime, Transfer]] = {}

    for t in transfers:
        td = parse_date(t.transfer_date)
        if td is None or td > cutoff:
            continue

        prev = best.get(t.player_id)
        if prev is None or td > prev[0]:
            best[t.player_id] = (td, t)

    return {pid: tr for pid, (_, tr) in best.items()}


def get_valuation_at_season_start(
    valuations: List[Valuation],
    season: str,
) -> Dict[str, Valuation]:
    """
    For each player return the most recent valuation whose date
    is **<= 01/07/{start_year}** (only 1 valuation per player).
    """
    cutoff = _get_season_start_date(season)

    best: Dict[str, Tuple[datetime, Valuation]] = {}

    for v in valuations:
        vd = parse_date(v.valuation_date)
        if vd is None or vd > cutoff:
            continue

        prev = best.get(v.player_id)
        if prev is None or vd > prev[0]:
            best[v.player_id] = (vd, v)

    return {pid: val for pid, (_, val) in best.items()}


# ── Main entry points ───────────────────────────────────────────────────

def get_active_players_at_season_start(
    season: str,
    league: str = "all",
    verbose: bool = False,
) -> List[Player]:
    """
    Build the definitive list of active players at season start (01/07).

    Pipeline:
      1. Load ALL players  →  dict[player_id, Player]
      2. Load ALL transfers →  inner join: only players with a transfer
         record are kept.  Updates ``team``, ``team_id``, ``on_loan``,
         ``loaning_team``.
      3. Filter out Retired / Without Club / Career break
      4. Compute ``age`` from ``birth_date`` + season cutoff date
      5. Load ALL valuations → for each player, last valuation <= cutoff
         → update ``market_value`` (0 if no valuation found)

    Args:
        season: e.g. "2023-2024"
        league: unused for now (kept for API compat)
        verbose: if True, show tqdm progress bars during loading

    Returns:
        List of Player objects ready for simulation
    """
    # 1. All players
    players = _load_all_players(verbose=verbose)

    # 2. Transfers → team assignment (streaming: no full list in memory)
    transfer_map = _load_transfer_map_at_cutoff(season, verbose=verbose)

    # Inner join: only keep players that appear in the transfer map
    matched: Dict[str, Player] = {}
    transfer_iter = tqdm(transfer_map.items(), desc="Assigning teams", disable=not verbose)
    for pid, t in transfer_iter:
        if pid not in players:
            continue  # player not in any players file, skip

        p = players[pid]
        p.team = t.to_club_name
        p.team_id = t.to_club_id

        # Loan tracking: if the last transfer is a loan, the player is
        # on loan at to_club, and the owning club is from_club.
        # if t.is_loan and t.price_str in ("loan transfer", "Loan fee"):
        if t.is_loan and t.transfer_type == "loan_out":
            p.on_loan = True
            p.loaning_team = t.from_club_name
            p.loaning_team_id = t.from_club_id
        else:
            p.on_loan = False
            p.loaning_team = ""
            p.loaning_team_id = ""

        matched[pid] = p

    # 3. Filter out excluded teams and players without a team
    active: Dict[str, Player] = {}
    matched_iter = tqdm(matched.items(), desc="Filtering active", disable=not verbose)
    for pid, p in matched_iter:
        # Players with no team at all are excluded
        if not p.team:
            continue

        team_name_lower = p.team.lower()
        team_id = str(p.team_id or "")

        if team_id in EXCLUDED_TEAM_IDS:
            continue
        if team_name_lower in EXCLUDED_TEAM_NAMES:
            continue

        active[pid] = p

    # 4. Compute age from birth_date + cutoff_date
    cutoff = _get_season_start_date(season)
    age_iter = tqdm(active.values(), desc="Computing ages", disable=not verbose)
    for p in age_iter:
        if p.birth_date and p.birth_date != "Unknown":
            bd = None
            for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
                try:
                    bd = datetime.strptime(p.birth_date, fmt)
                    break
                except (ValueError, TypeError):
                    continue
            if bd:
                age = cutoff.year - bd.year
                if (cutoff.month, cutoff.day) < (bd.month, bd.day):
                    age -= 1
                p.age = age

    # 5. Valuations → market_value update (streaming: no full list in memory)
    valuation_map = _load_valuation_map_at_cutoff(season, verbose=verbose)

    value_iter = tqdm(active.items(), desc="Updating market values", disable=not verbose)
    for pid, p in value_iter:
        p.market_value = valuation_map.get(pid, 0)

    return list(active.values())


def get_active_team_players_at_season_start(
    season: str,
    team_name_or_id: str,
    league: str = "all",
) -> List[Player]:
    """
    Get active players for a specific team at season start.

    Args:
        season: e.g. "2023-2024"
        team_name_or_id: Team name (partial match) or team_id
        league: unused (kept for API compat)

    Returns:
        List of Player objects for the team
    """
    all_active = get_active_players_at_season_start(season, league)
    if not all_active:
        return []

    team_lower = str(team_name_or_id).lower()

    # Try exact team_id match first
    by_id = [p for p in all_active if str(p.team_id) == str(team_name_or_id)]
    if by_id:
        return by_id

    # Fallback: partial name match
    return [p for p in all_active if team_lower in (p.team or "").lower()]


# ── Legacy / helper functions ────────────────────────────────────────────

def get_available_seasons() -> List[str]:
    """Get list of available seasons from data files. Supports multi-part files."""
    seasons = []
    for base in list_json_bases("players_all_*.json"):
        if base.startswith("players_all_"):
            season = base.replace("players_all_", "")
            if season and season not in seasons:
                seasons.append(season)
    return sorted(seasons, reverse=True)


def load_teams(season: str, league: str = "all") -> List[dict]:
    """Load teams for a given season and league."""
    file_name = f"teams_{league}_{season}"
    data = load_json(file_name)
    if data is None:
        return []
    return data if isinstance(data, list) else []


def load_players(season: str, league: str = "all") -> List[Player]:
    """Load players for a given season and league (raw, no enrichment)."""
    file_name = f"players_{league}_{season}"
    data = load_json(file_name)
    if data is None:
        return []
    raw = data if isinstance(data, list) else []
    return [Player.from_dict(p) for p in raw if isinstance(p, dict)]


def get_team_players(season: str, team_name_or_id: str, league: str = "all") -> List[Player]:
    """Get players belonging to a specific team for a season."""
    teams = load_teams(season, league)
    players = load_players(season, league)
    if not teams or not players:
        return []
    team_id = None
    team_name_lower = str(team_name_or_id).lower()
    for t in teams:
        tid = t.get("team_id", "")
        tname = (t.get("name") or "").lower()
        if str(tid) == str(team_name_or_id) or team_name_lower in tname:
            team_id = str(tid)
            break
    if not team_id:
        return []
    return [p for p in players if str(p.team_id) == team_id]


def get_available_clubs(season: str, league: str = "all") -> List[str]:
    """Get list of club names available for a season."""
    teams = load_teams(season, league)
    return [t.get("name", "") for t in teams if t.get("name")]


def load_valuations(season: str, league: str = "all") -> List[Valuation]:
    """Load valuations for a given season and league as Valuation objects."""
    file_name = f"valuations_{league}_{season}"
    data = load_json(file_name)
    if data is None:
        return []
    raw = data if isinstance(data, list) else []
    return [Valuation.from_dict(v) for v in raw if isinstance(v, dict)]


def _enrich_fair_prices(
    players: List[Player],
    valuations: List[Valuation],
    season: str,
) -> None:
    """Set fair_price via linear extrapolation from the last 2 valuations <= cutoff.

    Groups valuations by player, then delegates to
    ``feature_engineering.compute_fair_prices``.
    """
    from collections import defaultdict
    from ml.feature_engineering import compute_fair_prices

    cutoff = _get_season_start_date(season)

    by_player: Dict[str, List[Valuation]] = defaultdict(list)
    for v in valuations:
        by_player[v.player_id].append(v)

    fp_map = compute_fair_prices(by_player, cutoff)
    for p in players:
        fp = fp_map.get(p.player_id)
        if fp is not None:
            p.fair_price = fp


def enrich_players_with_predictions(
    players: List[Player],
    valuations: List[Valuation],
    season: str,
    model_path: Optional[Path] = None,
) -> List[Player]:
    """
    Enrich players with ML-predicted future values.

    Tries segmented models first (better accuracy at extreme values),
    then falls back to the global model.
    """
    try:
        from ml.value_predictor import (
            ValuePredictor, SegmentedValuePredictor, predict_player_values,
        )
    except ImportError:
        return players

    predictor = None
    # Try segmented models: exact season first, then fall back
    seg_seasons = [season]
    if season.lower() != "today":
        start_yr = int(season.split("-")[0])
        seg_seasons += [f"{start_yr - i}-{start_yr - i + 1}" for i in range(1, 6)]
    for seg_s in seg_seasons:
        try:
            seg = SegmentedValuePredictor(seg_s)
            if seg.is_trained:
                predictor = seg
                break
        except Exception:
            continue

    if predictor is None:
        if model_path is None:
            model_path = ValuePredictor.find_model_with_fallback(season) if season.lower() != "today" else ValuePredictor.get_latest_model()
        if model_path is None or not model_path.exists():
            return players
        try:
            predictor = ValuePredictor(model_path)
        except Exception:
            return players

    # fair_price uses START of season cutoff (01/07/YYYY)
    _enrich_fair_prices(players, valuations, season)

    # predicted_value uses END of season cutoff (01/07/(YYYY+1))
    if season.lower() == "today":
        pred_cutoff = datetime.now()
    else:
        start_year = int(season.split("-")[0])
        pred_cutoff = datetime(start_year + 1, 7, 1)

    predictions = predict_player_values(
        valuations,
        pred_cutoff,
        predictor,
        players={p.player_id: p for p in players},
    )

    for p in players:
        pred_value = predictions.get(p.player_id)
        if pred_value is not None:
            p.predicted_value = pred_value

    return players


def load_season_cache(season: str, max_age_days: int = 1) -> Optional[dict]:
    """
    Load the precomputed season cache.

    Works transparently for both legacy single-file caches
    (``season_data_{season}.json``) and multi-part shards
    (``season_data_{season}_part1.json``, …). For ``"today"`` the cache is
    only considered fresh if ``computed_date`` is within *max_age_days* of
    the current date.

    Returns a dict with keys:
        players          : List[Player]
        team_market_values : Dict[str, float]
        athletic_eligible_ids : Set[str]
    or None when no cache exists / is stale / fails.
    """
    raw = _load_raw_season_cache(season)
    if raw is None:
        return None

    # Freshness check for "today"
    if season.lower() == "today":
        computed = raw.get("computed_date")
        if computed:
            try:
                computed_dt = datetime.strptime(computed, "%Y-%m-%d")
                delta = (datetime.now() - computed_dt).days
                if delta > max_age_days:
                    return None
            except ValueError:
                return None

    players_raw = raw.get("players", [])
    if not isinstance(players_raw, list):
        return None

    players = [Player.from_dict(p) for p in players_raw if isinstance(p, dict)]

    # Recalculate ages from birth_date to fix stale/incorrect values in cache
    cutoff = _get_season_start_date(season)
    for p in players:
        if p.birth_date and p.birth_date != "Unknown":
            bd = None
            for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
                try:
                    bd = datetime.strptime(p.birth_date, fmt)
                    break
                except (ValueError, TypeError):
                    continue
            if bd:
                age = cutoff.year - bd.year
                if (cutoff.month, cutoff.day) < (bd.month, bd.day):
                    age -= 1
                p.age = age

    team_market_values = raw.get("team_market_values", {})
    athletic_ids = set(raw.get("athletic_eligible_ids", []))

    result = {
        "players": players,
        "team_market_values": team_market_values,
        "athletic_eligible_ids": athletic_ids,
    }
    horizon_preds = raw.get("horizon_predictions")
    if horizon_preds and isinstance(horizon_preds, dict):
        result["horizon_predictions"] = horizon_preds
    return result


def get_active_players_with_predictions(
    season: str,
    league: str = "all",
    model_path: Optional[Path] = None,
    use_cache: bool = True,
) -> List[Player]:
    """
    Get active players at season start with ML-predicted values.

    If use_cache is True and a precomputed season cache exists, loads
    players (with predictions already set) from cache.
    Otherwise computes on the fly.
    """
    if use_cache:
        cached = load_season_cache(season)
        if cached is not None:
            return cached["players"]

    players = get_active_players_at_season_start(season, league)
    if not players:
        return []

    valuations = load_valuations(season, league)

    return enrich_players_with_predictions(
        players,
        valuations,
        season,
        model_path,
    )
