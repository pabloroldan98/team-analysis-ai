"""
Feature engineering for player value prediction.

Extracts features from valuation history for XGBoost model.

Current club is determined from transfer data (not valuations).
Age is computed from birth_date + cutoff_date.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field

import numpy as np

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from valuation import Valuation
from player import Player
from transfer import Transfer
from scraping.utils.helpers import DATA_DIR

# Top 5 leagues (league_id values)
TOP_LEAGUE_IDS: Set[str] = {"GB1", "IT1", "L1", "FR1", "ES1"}

# Top nationalities for binning (rest will be "Other")
# These are the most common nationalities in top European leagues
TOP_NATIONALITIES: List[str] = [
    "France", "Spain", "Germany", "England", "Brazil", "Italy", "Argentina",
    "Portugal", "Netherlands", "Belgium", "Croatia", "Serbia", "Poland",
    "Denmark", "Switzerland", "Austria", "Senegal", "Morocco", "Nigeria",
    "Colombia", "Japan", "United States", "Cameroon", "Ivory Coast", "Ghana",
    "Uruguay", "Scotland", "Wales", "Turkey", "Norway", "Sweden",
]

# Top clubs for binning (rest will be "Other")
# These are the most valuable/prominent clubs
TOP_CLUBS: List[str] = [
    "Real Madrid", "FC Barcelona", "Manchester City", "Manchester United",
    "Liverpool FC", "Chelsea FC", "Arsenal FC", "Tottenham Hotspur",
    "Paris Saint-Germain", "Bayern Munich", "Borussia Dortmund", "RB Leipzig",
    "Juventus FC", "Inter Milan", "AC Milan", "SSC Napoli", "AS Roma",
    "Atletico Madrid", "Sevilla FC", "Real Sociedad",
    "Newcastle United", "Aston Villa", "West Ham United", "Brighton & Hove Albion",
    "Bayer 04 Leverkusen",
]


@dataclass
class PlayerFeatures:
    """Features extracted for a single player at a point in time."""
    player_id: str
    player_name: str
    
    # Current state
    current_value: float
    age: int
    position: str  # GK, DEF, MID, ATT
    player_nationality: str  # Player's nationality
    player_nationality_bin: str  # Binned nationality (top nationalities or "Other")
    is_in_top_league: bool  # Is player in one of top 5 leagues
    is_in_home_league: bool  # Is player playing in their home country
    current_club: str  # Club name at valuation time
    current_club_bin: str  # Binned club (top 25 clubs or "Other")
    valuation_date: datetime  # Date of valuation (important for market inflation)
    
    # Historical value features
    max_value: float
    min_value: float
    avg_value: float
    value_6m_ago: Optional[float]
    value_1y_ago: Optional[float]
    value_2y_ago: Optional[float]
    value_3y_ago: Optional[float]
    value_4y_ago: Optional[float]
    value_5y_ago: Optional[float]
    
    # Trend features (% change)
    trend_6m: float
    trend_1y: float
    trend_2y: float
    trend_4y: float
    trend_5y: float
    
    # Time features
    months_since_peak: int
    num_valuations: int
    months_of_history: int
    
    # Training metadata
    cutoff_season: str = ""  # Season of the cutoff (e.g., "2022-2023") for filtering
    
    # Target (only for training)
    target_value: Optional[float] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for DataFrame."""
        return {
            "player_id": self.player_id,
            "player_name": self.player_name,
            "current_value": self.current_value,
            "age": self.age,
            "position": self.position,
            "player_nationality": self.player_nationality,
            "player_nationality_bin": self.player_nationality_bin,
            "is_in_top_league": self.is_in_top_league,
            "is_in_home_league": self.is_in_home_league,
            "current_club": self.current_club,
            "current_club_bin": self.current_club_bin,
            "valuation_date": self.valuation_date.strftime("%Y-%m-%d") if self.valuation_date else None,
            "valuation_year": self.valuation_date.year + self.valuation_date.month / 12.0 if self.valuation_date else None,
            "max_value": self.max_value,
            "min_value": self.min_value,
            "avg_value": self.avg_value,
            "value_6m_ago": self.value_6m_ago,
            "value_1y_ago": self.value_1y_ago,
            "value_2y_ago": self.value_2y_ago,
            "value_3y_ago": self.value_3y_ago,
            "value_4y_ago": self.value_4y_ago,
            "value_5y_ago": self.value_5y_ago,
            "trend_6m": self.trend_6m,
            "trend_1y": self.trend_1y,
            "trend_2y": self.trend_2y,
            "trend_4y": self.trend_4y,
            "trend_5y": self.trend_5y,
            "months_since_peak": self.months_since_peak,
            "num_valuations": self.num_valuations,
            "months_of_history": self.months_of_history,
            "cutoff_season": self.cutoff_season,
            "target_value": self.target_value,
        }
    
    def to_feature_dict(self) -> Dict[str, any]:
        """
        Convert to feature dict for XGBoost with enable_categorical.
        
        Categorical features are kept as strings (XGBoost handles them natively).
        """
        # Valuation date as decimal year (e.g., 2023.5 for July 2023)
        valuation_year = self.valuation_date.year + self.valuation_date.month / 12.0 if self.valuation_date else 2020.0
        
        return {
            "current_value_M": self.current_value / 1_000_000,
            "age": float(self.age),
            "position": self.position,  # Categorical
            "player_nationality_bin": self.player_nationality_bin,  # Categorical
            "current_club_bin": self.current_club_bin,  # Categorical
            "is_in_top_league": 1.0 if self.is_in_top_league else 0.0,
            "is_in_home_league": 1.0 if self.is_in_home_league else 0.0,
            "valuation_year": valuation_year,
            "max_value_M": self.max_value / 1_000_000,
            "min_value_M": self.min_value / 1_000_000,
            "avg_value_M": self.avg_value / 1_000_000,
            "value_6m_ago_M": (self.value_6m_ago or 0) / 1_000_000,
            "value_1y_ago_M": (self.value_1y_ago or 0) / 1_000_000,
            "value_2y_ago_M": (self.value_2y_ago or 0) / 1_000_000,
            "value_3y_ago_M": (self.value_3y_ago or 0) / 1_000_000,
            "value_4y_ago_M": (self.value_4y_ago or 0) / 1_000_000,
            "value_5y_ago_M": (self.value_5y_ago or 0) / 1_000_000,
            "trend_6m": self.trend_6m,
            "trend_1y": self.trend_1y,
            "trend_2y": self.trend_2y,
            "trend_4y": self.trend_4y,
            "trend_5y": self.trend_5y,
            "months_since_peak": float(self.months_since_peak),
            "num_valuations": float(self.num_valuations),
            "months_of_history": float(self.months_of_history),
        }


def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse date string DD/MM/YYYY or YYYY-MM-DD to datetime."""
    if not date_str:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def _compute_age(birth_date_str: str, reference_date: datetime) -> Optional[int]:
    """Compute age in years from a DD/MM/YYYY birth date string."""
    bd = _parse_date(birth_date_str)
    if bd is None:
        return None
    age = reference_date.year - bd.year
    if (reference_date.month, reference_date.day) < (bd.month, bd.day):
        age -= 1
    return max(age, 0)


def _get_value_at_date(
    valuations: List[Tuple[datetime, float]],
    target_date: datetime,
    tolerance_days: int = 90,
) -> Optional[float]:
    """
    Get valuation closest to target_date within tolerance.
    """
    if not valuations:
        return None
    
    best_val = None
    best_diff = timedelta(days=tolerance_days + 1)
    
    for val_date, val_amount in valuations:
        diff = abs(val_date - target_date)
        if diff < best_diff:
            best_diff = diff
            best_val = val_amount
    
    if best_diff <= timedelta(days=tolerance_days):
        return best_val
    return None


def _compute_trend(current: float, past: Optional[float]) -> float:
    """Compute percentage change from past to current."""
    if past is None or past <= 0:
        return 0.0
    return (current - past) / past


def _is_home_league(nationality: str, country: str) -> bool:
    """Check if player nationality matches the country of their league."""
    if not nationality or not country:
        return False
    # Direct case-insensitive match (nationality is already country name like "Italy")
    return nationality.lower() == country.lower()


def _bin_nationality(nationality: str) -> str:
    """Bin nationality to top categories or 'Other'."""
    if not nationality:
        return "Other"
    if nationality in TOP_NATIONALITIES:
        return nationality
    return "Other"


def _bin_club(club: str) -> str:
    """Bin club to top categories or 'Other'."""
    if not club:
        return "Other"
    if club in TOP_CLUBS:
        return club
    return "Other"


def _load_all_transfers() -> List[Transfer]:
    """Load ALL ``transfers_all_*.json`` files into a flat list."""
    transfers: List[Transfer] = []
    for filepath in sorted(DATA_DIR.glob("transfers_all_*.json")):
        if "_OLD" in filepath.name:
            continue
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            if isinstance(item, dict):
                transfers.append(Transfer.from_dict(item))
    return transfers


def _get_transfer_map_at_cutoff(
    all_transfers: List[Transfer],
    cutoff_date: datetime,
) -> Dict[str, Transfer]:
    """
    For each player return their most recent transfer with date <= cutoff.

    Returns:
        Dict ``player_id -> Transfer``
    """
    best: Dict[str, Tuple[datetime, Transfer]] = {}
    for t in all_transfers:
        td = _parse_date(t.transfer_date)
        if td is None or td > cutoff_date:
            continue
        prev = best.get(t.player_id)
        if prev is None or td > prev[0]:
            best[t.player_id] = (td, t)
    return {pid: tr for pid, (_, tr) in best.items()}


def _normalize_position(pos: str) -> str:
    """Normalize position to GK/DEF/MID/ATT."""
    if not pos:
        return "MID"
    pos = pos.strip().upper()
    if pos in ["GK", "DEF", "MID", "ATT"]:
        return pos
    pos_lower = pos.lower()
    if "keeper" in pos_lower or "portero" in pos_lower:
        return "GK"
    if "defend" in pos_lower or "back" in pos_lower or "defens" in pos_lower:
        return "DEF"
    if "midfield" in pos_lower or "medio" in pos_lower:
        return "MID"
    if "forward" in pos_lower or "attack" in pos_lower or "striker" in pos_lower or "wing" in pos_lower:
        return "ATT"
    return "MID"


def load_team_league_mapping() -> Dict[str, Dict[str, Dict[str, str]]]:
    """
    Load mapping of (team_id, season) -> {league_id, country} for ALL seasons.
    
    Loads from all teams_all_{season}.json files.
    
    Returns:
        Dict mapping team_id -> season -> {"league_id": str, "country": str}
        This allows looking up a team's league_id for a specific season
        (e.g., Valladolid might be in ES1 one year and ES2 the next)
    """
    # team_id -> season -> {league_id, country}
    team_mapping: Dict[str, Dict[str, Dict[str, str]]] = {}
    
    # Load from all teams_all_*.json files
    teams_files = sorted(DATA_DIR.glob("teams_all_*.json"))
    
    for teams_file in teams_files:
        # Extract season from filename: teams_all_2023-2024.json -> 2023-2024
        season = teams_file.stem.replace("teams_all_", "")
        
        try:
            with open(teams_file, "r", encoding="utf-8") as f:
                teams = json.load(f)
            
            if isinstance(teams, list):
                for team in teams:
                    team_id = str(team.get("team_id", ""))
                    league_id = team.get("league_id", "")
                    country = team.get("country", "")
                    if team_id:
                        if team_id not in team_mapping:
                            team_mapping[team_id] = {}
                        team_mapping[team_id][season] = {
                            "league_id": league_id,
                            "country": country,
                        }
        except Exception:
            pass
    
    return team_mapping


def get_team_info_for_date(
    team_id: str,
    valuation_date: datetime,
    team_mapping: Dict[str, Dict[str, Dict[str, str]]],
    ignore_date: bool = False,
) -> Dict[str, str]:
    """
    Get team's league_id and country for a specific valuation date.
    
    Determines the season based on the date (season starts July 1st).
    
    Args:
        team_id: Team ID
        valuation_date: Date of the valuation
        team_mapping: Full team mapping from load_team_league_mapping()
    
    Returns:
        {"league_id": str, "country": str} or empty dict if not found
    """
    if not team_id or team_id not in team_mapping:
        return {}
    
    # Determine season from date (season starts July 1st)
    year = valuation_date.year
    month = valuation_date.month
    if month >= 7:
        season = f"{year}-{year + 1}"
    else:
        season = f"{year - 1}-{year}"
    
    team_seasons = team_mapping.get(team_id, {})
    
    # Try exact season match
    if season in team_seasons:
        return team_seasons[season]
    
    # Fallback: try adjacent seasons or any available
    if ignore_date:
        for s in sorted(team_seasons.keys(), reverse=True):
            return team_seasons[s]
    
    return {}


def extract_player_features(
    player_valuations: List[Valuation],
    cutoff_date: datetime,
    player_info: Optional[Player] = None,
    team_league_mapping: Optional[Dict[str, Dict[str, Dict[str, str]]]] = None,
    include_target: bool = False,
    cutoff_season: str = "",
    player_transfer: Optional[Transfer] = None,
) -> Optional[PlayerFeatures]:
    """
    Extract features for a player from their valuation history.
    
    Args:
        player_valuations: All valuations for this player
        cutoff_date: Date to use as "now" (e.g., 01/07/2023)
        player_info: Optional Player object for additional info
        team_league_mapping: Dict from load_team_league_mapping() 
            (team_id -> season -> {"league_id": str, "country": str})
        include_target: If True, also compute target (value 1 year later)
        cutoff_season: Season string (e.g., "2022-2023") for filtering during training
        player_transfer: Optional Transfer for current club determination.
            If provided, the player's club is taken from to_club (transfer-based).
            If None, falls back to the most recent valuation's club.
    
    Returns:
        PlayerFeatures or None if insufficient data
    """
    if not player_valuations:
        return None
    
    team_league_mapping = team_league_mapping or {}
    
    # Parse and filter valuations
    parsed: List[Tuple[datetime, float, Valuation]] = []
    future_vals: List[Tuple[datetime, float]] = []
    
    for v in player_valuations:
        val_date = _parse_date(v.valuation_date)
        if val_date is None or v.valuation_amount is None:
            continue
        
        if val_date < cutoff_date:
            parsed.append((val_date, v.valuation_amount, v))
        elif include_target:
            future_vals.append((val_date, v.valuation_amount))
    
    if not parsed:
        return None
    
    # Sort by date
    parsed.sort(key=lambda x: x[0])


    future_vals.sort(key=lambda x: x[0])
    
    # Get most recent valuation before cutoff
    last_date, current_value, last_val = parsed[-1]
    
    # Basic info
    player_id = last_val.player_id
    player_name = last_val.player_name

    # Age: compute from birth_date + cutoff, fallback to valuation age, then player age
    age = None
    if player_info and player_info.birth_date:
        age = _compute_age(player_info.birth_date, cutoff_date)
    if age is None:
        age = last_val.age_at_valuation or (player_info.age if player_info else None) or 25
    
    # Position
    if player_info and player_info.position:
        position = _normalize_position(player_info.position)
    else:
        position = "MID"
    
    # Player nationality and binned version
    player_nationality = player_info.nationality if player_info else ""
    player_nationality_bin = _bin_nationality(player_nationality)
    
    # Current club: prefer transfer data, fallback to valuation
    if player_transfer is not None:
        club_id = str(player_transfer.to_club_id or "")
        current_club = player_transfer.to_club_name or ""
    else:
        club_id = str(last_val.club_id_at_valuation or "")
        current_club = last_val.club_name_at_valuation or ""

    # Is in top league? Look up team_id in mapping for the specific season
    team_info = get_team_info_for_date(club_id, last_date, team_league_mapping)
    any_team_info = get_team_info_for_date(club_id, last_date, team_league_mapping, ignore_date=True)
    league_id = team_info.get("league_id", "")
    team_country = any_team_info.get("country", "")
    is_in_top_league = league_id in TOP_LEAGUE_IDS
    
    # Is in home league? Check if player nationality matches team's country
    is_in_home_league = _is_home_league(player_nationality, team_country)

    current_club_bin = _bin_club(current_club)
    valuation_date = last_date  # Date of the most recent valuation before cutoff
    
    # Historical stats
    values = [v[1] for v in parsed]
    max_value = max(values)
    min_value = min(values)
    avg_value = sum(values) / len(values)
    
    # Value at specific past dates
    val_list = [(d, v) for d, v, _ in parsed]
    
    value_6m_ago = _get_value_at_date(val_list, cutoff_date - timedelta(days=180), 60)
    value_1y_ago = _get_value_at_date(val_list, cutoff_date - timedelta(days=365), 90)
    value_2y_ago = _get_value_at_date(val_list, cutoff_date - timedelta(days=730), 90)
    value_3y_ago = _get_value_at_date(val_list, cutoff_date - timedelta(days=1095), 90)
    value_4y_ago = _get_value_at_date(val_list, cutoff_date - timedelta(days=1460), 90)
    value_5y_ago = _get_value_at_date(val_list, cutoff_date - timedelta(days=1825), 90)
    
    # Trends
    trend_6m = _compute_trend(current_value, value_6m_ago)
    trend_1y = _compute_trend(current_value, value_1y_ago)
    trend_2y = _compute_trend(current_value, value_2y_ago)
    trend_4y = _compute_trend(current_value, value_4y_ago)
    trend_5y = _compute_trend(current_value, value_5y_ago)
    
    # Time features
    peak_date = max(parsed, key=lambda x: x[1])[0]
    months_since_peak = int((cutoff_date - peak_date).days / 30)
    num_valuations = len(parsed)
    first_date = parsed[0][0]
    months_of_history = int((cutoff_date - first_date).days / 30)
    
    # Target value (1 year after cutoff, or latest if not available)
    target_value = None
    if include_target and future_vals:
        target_date = cutoff_date + timedelta(days=365)
        target_value = _get_value_at_date(future_vals, target_date, tolerance_days=120)
        # If no value at 1 year, use the latest available (for current season)
        if target_value is None and future_vals:
            target_value = future_vals[-1][1]  # Latest valuation
    
    return PlayerFeatures(
        player_id=player_id,
        player_name=player_name,
        current_value=current_value,
        age=age,
        position=position,
        player_nationality=player_nationality,
        player_nationality_bin=player_nationality_bin,
        is_in_top_league=is_in_top_league,
        is_in_home_league=is_in_home_league,
        current_club=current_club,
        current_club_bin=current_club_bin,
        valuation_date=valuation_date,
        max_value=max_value,
        min_value=min_value,
        avg_value=avg_value,
        value_6m_ago=value_6m_ago,
        value_1y_ago=value_1y_ago,
        value_2y_ago=value_2y_ago,
        value_3y_ago=value_3y_ago,
        value_4y_ago=value_4y_ago,
        value_5y_ago=value_5y_ago,
        trend_6m=trend_6m,
        trend_1y=trend_1y,
        trend_2y=trend_2y,
        trend_4y=trend_4y,
        trend_5y=trend_5y,
        months_since_peak=months_since_peak,
        num_valuations=num_valuations,
        months_of_history=months_of_history,
        cutoff_season=cutoff_season,
        target_value=target_value,
    )


def _get_season_for_cutoff(cutoff_date: datetime) -> str:
    """
    Get season string for a cutoff date.
    Cutoff 01/07/2023 belongs to season 2023-2024 (predicting end of that season).
    """
    year = cutoff_date.year
    return f"{year}-{year + 1}"


def _detect_cutoff_dates(
    all_valuations: List[Valuation],
    cutoff_months: int = 12,
) -> List[datetime]:
    """
    Detect all valid cutoff dates from valuations.
    
    Args:
        all_valuations: All valuations to analyze
        cutoff_months: Months between cutoffs (12 = annual, 6 = semi-annual, etc.)
    
    A cutoff is valid if:
    - There is data before it (for features)
    - There is data after it (for target, at least 1 year later)
    """
    # Find min and max dates in valuations
    min_date = None
    max_date = None
    
    for v in all_valuations:
        try:
            date_val = v.valuation_date
            if isinstance(date_val, str) and date_val:
                # Try DD/MM/YYYY format first (from JSON), then YYYY-MM-DD
                try:
                    dt = datetime.strptime(date_val, "%d/%m/%Y")
                except ValueError:
                    dt = datetime.strptime(date_val, "%Y-%m-%d")
            elif isinstance(date_val, datetime):
                dt = date_val
            else:
                continue
            
            if min_date is None or dt < min_date:
                min_date = dt
            if max_date is None or dt > max_date:
                max_date = dt
        except (ValueError, AttributeError):
            continue
    
    if min_date is None or max_date is None:
        print(f"  Warning: Could not determine date range from valuations")
        return []
    
    print(f"  Valuation date range: {min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')}")
    
    # Generate cutoffs based on frequency
    # Start from min_date + 1 year (need history), end at max_date - 1 year (need target)
    cutoffs = []
    
    # Start at first July 1st after min_date + 1 year
    start_year = min_date.year + 1
    first_cutoff = datetime(start_year, 7, 1)
    if first_cutoff <= min_date:
        first_cutoff = datetime(start_year + 1, 7, 1)
    
    # Generate cutoffs with specified frequency
    current = first_cutoff
    target_horizon = timedelta(days=365)  # We predict 1 year ahead
    
    while current + target_horizon < max_date:
        if current > min_date:
            cutoffs.append(current)
        
        # Move to next cutoff
        new_month = current.month + cutoff_months
        new_year = current.year + (new_month - 1) // 12
        new_month = ((new_month - 1) % 12) + 1
        current = datetime(new_year, new_month, 1)
    
    if cutoffs:
        print(f"  Generated {len(cutoffs)} cutoffs (every {cutoff_months} months): "
              f"{cutoffs[0].strftime('%Y-%m-%d')} to {cutoffs[-1].strftime('%Y-%m-%d')}")
    
    return sorted(cutoffs)


def build_training_dataset(
    all_valuations: List[Valuation],
    players: Optional[Dict[str, Player]] = None,
    team_league_mapping: Optional[Dict[str, Dict[str, Dict[str, str]]]] = None,
    min_valuations: int = 3,
    cutoff_dates: Optional[List[datetime]] = None,
    cutoff_months: int = 12,
    all_transfers: Optional[List[Transfer]] = None,
) -> List[PlayerFeatures]:
    """
    Build complete training dataset with multiple cutoff dates.
    
    Generates multiple rows per player (one per cutoff date where they have data),
    maximizing use of historical valuation data.
    
    Current club is determined from transfer data (last transfer <= cutoff).
    Age is computed from birth_date + cutoff_date.
    
    Args:
        all_valuations: All valuations (all leagues, all time)
        players: Optional dict of player_id -> Player for extra info
        team_league_mapping: Dict from load_team_league_mapping()
        min_valuations: Minimum valuations required per player per cutoff
        cutoff_dates: Optional list of cutoff dates. If None, auto-detects from data.
        cutoff_months: Months between cutoffs if auto-detecting (12=annual, 6=semi-annual)
        all_transfers: Optional list of ALL transfers. If None, loads from files.
    
    Returns:
        List of PlayerFeatures with target values and cutoff_season metadata
    """
    # Auto-detect cutoff dates if not provided
    if cutoff_dates is None:
        cutoff_dates = _detect_cutoff_dates(all_valuations, cutoff_months=cutoff_months)
    
    if not cutoff_dates:
        print("Warning: No valid cutoff dates found")
        return []
    
    print(f"Using {len(cutoff_dates)} cutoff dates: "
          f"{cutoff_dates[0].strftime('%Y-%m-%d')} to {cutoff_dates[-1].strftime('%Y-%m-%d')}")
    
    # Load transfers for club determination
    if all_transfers is None:
        print("Loading all transfers for club assignment...")
        all_transfers = _load_all_transfers()
        print(f"  Loaded {len(all_transfers)} transfers")
    
    # Group valuations by player
    by_player: Dict[str, List[Valuation]] = {}
    for v in all_valuations:
        by_player.setdefault(v.player_id, []).append(v)
    
    dataset = []
    total_players = len(by_player)
    
    # For each cutoff date, generate features for all eligible players
    for cutoff_idx, cutoff_date in enumerate(cutoff_dates):
        cutoff_season = _get_season_for_cutoff(cutoff_date)
        players_for_cutoff = 0
        
        # Build transfer map for this cutoff
        transfer_map = _get_transfer_map_at_cutoff(all_transfers, cutoff_date)
        
        for player_id, player_vals in by_player.items():
            if len(player_vals) < min_valuations:
                continue
            
            player_info = players.get(player_id) if players else None
            player_transfer = transfer_map.get(player_id)
            
            features = extract_player_features(
                player_vals,
                cutoff_date,
                player_info=player_info,
                team_league_mapping=team_league_mapping,
                include_target=True,
                cutoff_season=cutoff_season,
                player_transfer=player_transfer,
            )
            
            if features and features.target_value is not None:
                dataset.append(features)
                players_for_cutoff += 1
        
        print(f"  Cutoff {cutoff_date.strftime('%Y-%m-%d')} ({cutoff_season}): "
              f"{players_for_cutoff} players")
    
    print(f"Total training samples: {len(dataset)} "
          f"({len(cutoff_dates)} cutoffs x ~{len(dataset) // max(1, len(cutoff_dates))} players/cutoff)")
    
    return dataset


# ============================================================================
# Dataset Persistence (Save/Load)
# ============================================================================

DATASETS_DIR = Path(__file__).parent / "datasets"


def _get_dataset_path(cutoff_months: int = 12) -> Path:
    """Get path for the training dataset file."""
    return DATASETS_DIR / f"training_dataset_{cutoff_months}m.json"


def save_training_dataset(
    dataset: List[PlayerFeatures],
    cutoff_months: int = 12,
) -> Path:
    """
    Save training dataset to JSON file.
    
    Args:
        dataset: List of PlayerFeatures to save
        cutoff_months: Frequency used to generate dataset (for filename)
    
    Returns:
        Path to saved file
    """
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = _get_dataset_path(cutoff_months)
    
    # Convert to list of dicts
    data = [f.to_dict() for f in dataset]
    
    # Add metadata
    output = {
        "metadata": {
            "cutoff_months": cutoff_months,
            "num_samples": len(dataset),
            "created_at": datetime.now().isoformat(),
            "cutoff_seasons": sorted(set(f.cutoff_season for f in dataset)),
        },
        "samples": data,
    }
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)
    
    print(f"Saved training dataset to: {filepath}")
    print(f"  Samples: {len(dataset)}")
    print(f"  Cutoff frequency: {cutoff_months} months")
    print(f"  Seasons: {output['metadata']['cutoff_seasons']}")
    
    return filepath


def load_training_dataset(cutoff_months: int = 12) -> Optional[List[PlayerFeatures]]:
    """
    Load training dataset from JSON file.
    
    Args:
        cutoff_months: Frequency used to generate dataset (for filename)
    
    Returns:
        List of PlayerFeatures or None if file doesn't exist
    """
    filepath = _get_dataset_path(cutoff_months)
    
    if not filepath.exists():
        return None
    
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    metadata = data.get("metadata", {})
    samples = data.get("samples", [])
    
    print(f"Loading training dataset from: {filepath}")
    print(f"  Samples: {metadata.get('num_samples', len(samples))}")
    print(f"  Created: {metadata.get('created_at', 'unknown')}")
    print(f"  Seasons: {metadata.get('cutoff_seasons', [])}")
    
    # Convert dicts back to PlayerFeatures
    dataset = []
    for item in samples:
        # Parse valuation_date back to datetime
        val_date = item.get("valuation_date")
        if isinstance(val_date, str) and val_date:
            try:
                val_date = datetime.fromisoformat(val_date)
            except ValueError:
                val_date = datetime(2020, 1, 1)  # Fallback
        else:
            val_date = datetime(2020, 1, 1)
        
        features = PlayerFeatures(
            player_id=item.get("player_id", ""),
            player_name=item.get("player_name", ""),
            current_value=item.get("current_value", 0),
            age=item.get("age", 0),
            position=item.get("position", "MID"),
            player_nationality=item.get("player_nationality", ""),
            player_nationality_bin=item.get("player_nationality_bin", "Other"),
            is_in_top_league=item.get("is_in_top_league", False),
            is_in_home_league=item.get("is_in_home_league", False),
            current_club=item.get("current_club", ""),
            current_club_bin=item.get("current_club_bin", "Other"),
            valuation_date=val_date,
            max_value=item.get("max_value", 0),
            min_value=item.get("min_value", 0),
            avg_value=item.get("avg_value", 0),
            value_6m_ago=item.get("value_6m_ago"),
            value_1y_ago=item.get("value_1y_ago"),
            value_2y_ago=item.get("value_2y_ago"),
            value_3y_ago=item.get("value_3y_ago"),
            value_4y_ago=item.get("value_4y_ago"),
            value_5y_ago=item.get("value_5y_ago"),
            trend_6m=item.get("trend_6m", 0),
            trend_1y=item.get("trend_1y", 0),
            trend_2y=item.get("trend_2y", 0),
            trend_4y=item.get("trend_4y", 0),
            trend_5y=item.get("trend_5y", 0),
            months_since_peak=item.get("months_since_peak", 0),
            num_valuations=item.get("num_valuations", 0),
            months_of_history=item.get("months_of_history", 0),
            cutoff_season=item.get("cutoff_season", ""),
            target_value=item.get("target_value"),
        )
        dataset.append(features)
    
    return dataset


def filter_dataset_for_season(
    dataset: List[PlayerFeatures],
    target_season: str,
) -> List[PlayerFeatures]:
    """
    Filter dataset to include samples from seasons UP TO AND INCLUDING target season.
    
    For model 2023-2024, this includes cutoff 01/07/2023 (season 2023-2024),
    which predicts values for 01/07/2024.
    
    Args:
        dataset: Full training dataset
        target_season: Season to train for (e.g., "2023-2024")
    
    Returns:
        Filtered dataset with samples from target season and earlier
    """
    target_year = int(target_season.split("-")[0])
    
    filtered = [
        f for f in dataset
        if f.cutoff_season and int(f.cutoff_season.split("-")[0]) <= target_year
    ]
    
    return filtered


def get_samples_for_season(
    dataset: List[PlayerFeatures],
    season: str,
) -> List[PlayerFeatures]:
    """
    Get only samples from a specific season (for evaluation).
    
    Args:
        dataset: Full training dataset
        season: Season to filter (e.g., "2023-2024")
    
    Returns:
        Samples only from that season
    """
    return [f for f in dataset if f.cutoff_season == season]


def build_prediction_dataset(
    all_valuations: List[Valuation],
    cutoff_date: datetime,
    players: Optional[Dict[str, Player]] = None,
    team_league_mapping: Optional[Dict[str, Dict[str, Dict[str, str]]]] = None,
    min_valuations: int = 2,
    all_transfers: Optional[List[Transfer]] = None,
) -> List[PlayerFeatures]:
    """
    Build dataset for prediction (no target required).

    Current club is determined from transfer data (last transfer <= cutoff).
    Age is computed from birth_date + cutoff_date.
    """
    # Load transfers for club determination
    if all_transfers is None:
        all_transfers = _load_all_transfers()

    transfer_map = _get_transfer_map_at_cutoff(all_transfers, cutoff_date)

    by_player: Dict[str, List[Valuation]] = {}
    for v in all_valuations:
        by_player.setdefault(v.player_id, []).append(v)
    
    dataset = []
    for player_id, player_vals in by_player.items():
        if len(player_vals) < min_valuations:
            continue
        
        player_info = players.get(player_id) if players else None
        player_transfer = transfer_map.get(player_id)
        
        features = extract_player_features(
            player_vals,
            cutoff_date,
            player_info=player_info,
            team_league_mapping=team_league_mapping,
            include_target=False,
            player_transfer=player_transfer,
        )
        
        if features:
            dataset.append(features)
    
    return dataset
