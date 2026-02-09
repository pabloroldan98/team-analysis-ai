"""Load teams and players from JSON data."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scraping.utils.helpers import read_dict_from_json, DATA_DIR
from player import Player
from valuation import Valuation


def get_available_seasons() -> List[str]:
    """Get list of available seasons from data files."""
    seasons = set()
    if not DATA_DIR.exists():
        return []
    for f in DATA_DIR.glob("players_all_*.json"):
        if "_OLD" not in f.name:
            # Extract season from filename: players_all_2020-2021.json -> 2020-2021
            stem = f.stem
            if stem.startswith("players_all_"):
                season = stem.replace("players_all_", "")
                seasons.add(season)
    return sorted(seasons, reverse=True)


def load_teams(season: str, league: str = "all") -> List[dict]:
    """Load teams for a given season and league."""
    file_name = f"teams_{league}_{season}"
    data = read_dict_from_json(file_name)
    if data is None:
        return []
    return data if isinstance(data, list) else []


def load_players(season: str, league: str = "all") -> List[Player]:
    """Load players for a given season and league as Player objects."""
    file_name = f"players_{league}_{season}"
    data = read_dict_from_json(file_name)
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
    data = read_dict_from_json(file_name)
    if data is None:
        return []
    raw = data if isinstance(data, list) else []
    return [Valuation.from_dict(v) for v in raw if isinstance(v, dict)]


def _parse_valuation_date(date_str: str) -> Optional[datetime]:
    """Parse valuation date string (DD/MM/YYYY) to datetime."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%d/%m/%Y")
    except ValueError:
        return None


def _get_season_start_date(season: str) -> datetime:
    """
    Get the season start date (01/07 of the starting year).
    
    Args:
        season: Season string like "2023-2024"
    
    Returns:
        datetime for 01/07 of the starting year
    """
    start_year = int(season.split("-")[0])
    return datetime(start_year, 7, 1)


def get_valuation_at_season_start(
    valuations: List[Valuation],
    season: str,
) -> Dict[str, Valuation]:
    """
    Get the most recent valuation for each player BEFORE season start date.
    
    Args:
        valuations: List of all valuations
        season: Season string like "2023-2024"
    
    Returns:
        Dict mapping player_id to their valuation at season start
    """
    cutoff_date = _get_season_start_date(season)
    
    # Group valuations by player_id and find the most recent before cutoff
    player_valuations: Dict[str, Valuation] = {}
    player_dates: Dict[str, datetime] = {}
    
    for v in valuations:
        val_date = _parse_valuation_date(v.valuation_date)
        if val_date is None or val_date >= cutoff_date:
            continue
        
        pid = v.player_id
        current_best_date = player_dates.get(pid)
        
        if current_best_date is None or val_date > current_best_date:
            player_valuations[pid] = v
            player_dates[pid] = val_date
    
    return player_valuations


def get_active_players_at_season_start(
    season: str,
    league: str = "all",
) -> List[Player]:
    """
    Get list of active players with their data at season start (01/07).
    
    This function:
    1. Loads all players and valuations for the season
    2. For each player, finds their most recent valuation BEFORE 01/07/(start year)
    3. Excludes players who were "Retired" at that point
    4. Updates player data (market_value, team, team_id, age) from the valuation
    
    Args:
        season: Season string like "2023-2024"
        league: League code (default "all")
    
    Returns:
        List of Player objects with updated data from valuations (INNER JOIN)
    """
    players = load_players(season, league)
    valuations = load_valuations(season, league)
    
    if not players or not valuations:
        return players  # Return original if no valuations
    
    # Get valuation at season start for each player
    val_at_start = get_valuation_at_season_start(valuations, season)
    
    # INNER JOIN: only keep players that have a valuation at season start
    active_players = []
    
    for p in players:
        valuation = val_at_start.get(p.player_id)
        if valuation is None:
            continue  # No valuation found, skip (INNER JOIN behavior)
        
        # Exclude retired players
        club_name = valuation.club_name_at_valuation or ""
        if club_name.lower() == "retired":
            continue
        
        # Update player with valuation data
        p.market_value = valuation.valuation_amount
        p.team = club_name
        p.team_id = valuation.club_id_at_valuation
        if valuation.age_at_valuation is not None:
            p.age = valuation.age_at_valuation
        
        active_players.append(p)
    
    return active_players


def get_active_team_players_at_season_start(
    season: str,
    team_name_or_id: str,
    league: str = "all",
) -> List[Player]:
    """
    Get active players for a specific team at season start.
    
    Uses get_active_players_at_season_start and filters by team.
    Note: The team is determined by club_id_at_valuation from the valuation data.
    
    Args:
        season: Season string like "2023-2024"
        team_name_or_id: Team name (partial match) or team_id
        league: League code (default "all")
    
    Returns:
        List of active Player objects for the team
    """
    all_active = get_active_players_at_season_start(season, league)
    if not all_active:
        return []
    
    # Find team_id from teams data
    teams = load_teams(season, league)
    team_id = None
    team_name_lower = str(team_name_or_id).lower()
    
    for t in teams:
        tid = t.get("team_id", "")
        tname = (t.get("name") or "").lower()
        if str(tid) == str(team_name_or_id) or team_name_lower in tname:
            team_id = str(tid)
            break
    
    if not team_id:
        # Try matching by team name directly from player's team
        return [p for p in all_active if team_name_lower in (p.team or "").lower()]
    
    return [p for p in all_active if str(p.team_id) == team_id]


def enrich_players_with_predictions(
    players: List[Player],
    valuations: List[Valuation],
    season: str,
    model_path: Optional[Path] = None,
) -> List[Player]:
    """
    Enrich players with ML-predicted future values.
    
    Args:
        players: List of Player objects to enrich
        valuations: Historical valuations for feature extraction
        season: Season string (e.g., "2023-2024")
        model_path: Optional path to trained model. If None, tries to find latest.
    
    Returns:
        Same players with predicted_value set (if model available)
    """
    try:
        from ml.value_predictor import ValuePredictor, predict_player_values
    except ImportError:
        # ML module not available or dependencies missing
        return players
    
    # Find model
    if model_path is None:
        model_path = ValuePredictor.get_latest_model()
    
    if model_path is None or not model_path.exists():
        return players  # No model available
    
    # Load model
    try:
        predictor = ValuePredictor(model_path)
    except Exception:
        return players
    
    # Get cutoff date
    cutoff_date = _get_season_start_date(season)
    
    # Predict values
    predictions = predict_player_values(
        valuations,
        cutoff_date,
        predictor,
        players={p.player_id: p for p in players},
    )
    
    # Enrich players
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
    
    Combines get_active_players_at_season_start with ML predictions.
    
    Args:
        season: Season string (e.g., "2023-2024")
        league: League code (default "all")
        model_path: Optional path to trained model
    
    Returns:
        List of Player objects with market_value and predicted_value set
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
