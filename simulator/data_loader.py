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
from player import Player
from transfer import Transfer
from valuation import Valuation


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
        if p.birth_date:
            try:
                bd = datetime.strptime(p.birth_date, "%Y-%m-%d")
            except (ValueError, TypeError):
                bd = None
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


def enrich_players_with_predictions(
    players: List[Player],
    valuations: List[Valuation],
    season: str,
    model_path: Optional[Path] = None,
) -> List[Player]:
    """
    Enrich players with ML-predicted future values.
    """
    try:
        from ml.value_predictor import ValuePredictor, predict_player_values
    except ImportError:
        return players

    if model_path is None:
        model_path = ValuePredictor.get_latest_model()

    if model_path is None or not model_path.exists():
        return players

    try:
        predictor = ValuePredictor(model_path)
    except Exception:
        return players

    cutoff_date = _get_season_start_date(season)

    predictions = predict_player_values(
        valuations,
        cutoff_date,
        predictor,
        players={p.player_id: p for p in players},
    )

    for p in players:
        pred_value = predictions.get(p.player_id)
        if pred_value is not None:
            p.predicted_value = pred_value

    return players


def get_active_players_with_predictions(
    season: str,
    league: str = "all",
    model_path: Optional[Path] = None,
) -> List[Player]:
    """
    Get active players at season start with ML-predicted values.
    """
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
