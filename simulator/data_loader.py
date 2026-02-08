"""Load teams and players from JSON data."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scraping.utils.helpers import read_dict_from_json, DATA_DIR
from player import Player


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
