"""
Feature engineering for player value prediction.

Extracts features from valuation history for XGBoost model.

Current club is determined from transfer data (not valuations).
Age is computed from birth_date + cutoff_date.
"""
from __future__ import annotations

import bisect
import functools
import json
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field

import numpy as np
from tqdm import tqdm

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from valuation import Valuation
from player import Player
from transfer import Transfer
from scraping.utils.helpers import DATA_DIR, list_json_bases, load_json, parse_date
from scraping.base_scraper import BaseScraper


@functools.lru_cache(maxsize=50000)
def _parse_date_cached(date_str: str):
    """Cached parse_date for repeated date strings in transfers/valuations."""
    return parse_date(date_str)

# Top 5 leagues (league_id values)
TOP_LEAGUE_IDS: Set[str] = {"GB1", "IT1", "L1", "FR1", "ES1"}

# Top nationalities for binning (rest will be "Other")
# These are the most common nationalities in top European leagues
TOP_NATIONALITIES: List[str] = [
    "France", "Spain", "Germany", "England", "Brazil", "Italy", "Argentina",
    "Portugal", "Netherlands", "Belgium", "Croatia", "Serbia", "Poland",
    "Denmark", "Switzerland", "Austria", "Senegal", "Morocco", "Nigeria",
    "Colombia", "Japan", "United States", "Cameroon", "Ivory Coast", "Ghana",
    "Uruguay", "Scotland", "Wales", "Turkey", "Norway", "Sweden", "Greece",
    "Romania", "Czech Republic", "Slovakia", "Hungary", "Slovenia", "Iran",
    "Bosnia and Herzegovina", "North Macedonia", "Albania", "Kosovo",
    "Egypt", "South Africa", "Qatar", "Saudi Arabia", "United Arab Emirates",
    "China", "Australia", "South Korea", "Ecuador", "Peru", "Paraguay",
    "Chile", "Mexico", "Canada", "Russia", "Ukraine",
]

# Top clubs for binning (rest will be "Other")
# These are the most valuable/prominent clubs
# league_id -> (league_key, tier_str) built from LEAGUE_INFO; unknown -> ("Other", "Other")
LEAGUE_ID_TO_KEY_AND_TIER: Dict[str, Tuple[str, str]] = {}
for _key, _info in BaseScraper.LEAGUE_INFO.items():
    _lid = _info.get("id", "")
    if _lid:
        _t = _info.get("tier", "Other")
        LEAGUE_ID_TO_KEY_AND_TIER[_lid] = (_key, str(_t) if isinstance(_t, int) else _t)

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
    age: float
    position: str  # GK, DEF, MID, ATT
    player_nationality: str  # Player's nationality
    player_nationality_bin: str  # Binned nationality (top nationalities or "Other")
    is_in_top_league: bool  # Is player in one of top 5 leagues
    is_in_home_league: bool  # Is player playing in their home country
    current_league: str  # League key from LEAGUE_INFO or "Other"
    league_tier: str  # Tier from LEAGUE_INFO (1, 2, 3, 4, youth, cup) or "Other"
    current_club: str  # Club name at valuation time
    current_club_value: float  # Sum of market values of all players in team at cutoff (€)
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
    
    # Percent features (current / past)
    pct_6m: float
    pct_1y: float
    pct_2y: float
    pct_4y: float
    pct_5y: float
    
    # Difference features (current - past)
    diff_6m: float
    diff_1y: float
    diff_2y: float
    diff_4y: float
    diff_5y: float
    
    # Time features
    months_since_peak: int
    num_valuations: int
    months_of_history: int
    
    # Percentile features (computed per cutoff, 0-100; np.nan when no data)
    current_value_percentile: float = 0.0
    value_6m_ago_percentile: float = 0.0
    value_1y_ago_percentile: float = 0.0
    value_2y_ago_percentile: float = 0.0
    value_3y_ago_percentile: float = 0.0
    value_4y_ago_percentile: float = 0.0
    value_5y_ago_percentile: float = 0.0
    # Derived: diff (current - past), trend ((current-past)/max(past,1)), pct (current/max(past,1))
    diff_percentile_6m: float = 0.0
    diff_percentile_1y: float = 0.0
    diff_percentile_2y: float = 0.0
    diff_percentile_3y: float = 0.0
    diff_percentile_4y: float = 0.0
    diff_percentile_5y: float = 0.0
    trend_percentile_6m: float = 0.0
    trend_percentile_1y: float = 0.0
    trend_percentile_2y: float = 0.0
    trend_percentile_3y: float = 0.0
    trend_percentile_4y: float = 0.0
    trend_percentile_5y: float = 0.0
    pct_percentile_6m: float = 0.0
    pct_percentile_1y: float = 0.0
    pct_percentile_2y: float = 0.0
    pct_percentile_3y: float = 0.0
    pct_percentile_4y: float = 0.0
    pct_percentile_5y: float = 0.0
    
    # Training metadata
    cutoff_season: str = ""  # Season of the cutoff (e.g., "2022-2023") for filtering
    
    # Target (only for training)
    target_value: Optional[float] = None
    
    @staticmethod
    def _safe_float(x: Optional[float]) -> float:
        """Return float for feature dict; np.nan for None (XGBoost handles missing)."""
        if x is None:
            return np.nan
        return float(x)

    @staticmethod
    def _json_float(x: float) -> Optional[float]:
        """Return None for nan (JSON-serializable); else the value."""
        if isinstance(x, float) and np.isnan(x):
            return None
        return x

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
            "current_league": self.current_league,
            "league_tier": self.league_tier,
            "current_club": self.current_club,
            "current_club_value": self.current_club_value,
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
            "pct_6m": self.pct_6m,
            "pct_1y": self.pct_1y,
            "pct_2y": self.pct_2y,
            "pct_4y": self.pct_4y,
            "pct_5y": self.pct_5y,
            "diff_6m": self.diff_6m,
            "diff_1y": self.diff_1y,
            "diff_2y": self.diff_2y,
            "diff_4y": self.diff_4y,
            "diff_5y": self.diff_5y,
            "months_since_peak": self.months_since_peak,
            "num_valuations": self.num_valuations,
            "months_of_history": self.months_of_history,
            "current_value_percentile": self.current_value_percentile,
            "value_6m_ago_percentile": self._json_float(self.value_6m_ago_percentile),
            "value_1y_ago_percentile": self._json_float(self.value_1y_ago_percentile),
            "value_2y_ago_percentile": self._json_float(self.value_2y_ago_percentile),
            "value_3y_ago_percentile": self._json_float(self.value_3y_ago_percentile),
            "value_4y_ago_percentile": self._json_float(self.value_4y_ago_percentile),
            "value_5y_ago_percentile": self._json_float(self.value_5y_ago_percentile),
            "diff_percentile_6m": self._json_float(self.diff_percentile_6m),
            "diff_percentile_1y": self._json_float(self.diff_percentile_1y),
            "diff_percentile_2y": self._json_float(self.diff_percentile_2y),
            "diff_percentile_3y": self._json_float(self.diff_percentile_3y),
            "diff_percentile_4y": self._json_float(self.diff_percentile_4y),
            "diff_percentile_5y": self._json_float(self.diff_percentile_5y),
            "trend_percentile_6m": self._json_float(self.trend_percentile_6m),
            "trend_percentile_1y": self._json_float(self.trend_percentile_1y),
            "trend_percentile_2y": self._json_float(self.trend_percentile_2y),
            "trend_percentile_3y": self._json_float(self.trend_percentile_3y),
            "trend_percentile_4y": self._json_float(self.trend_percentile_4y),
            "trend_percentile_5y": self._json_float(self.trend_percentile_5y),
            "pct_percentile_6m": self._json_float(self.pct_percentile_6m),
            "pct_percentile_1y": self._json_float(self.pct_percentile_1y),
            "pct_percentile_2y": self._json_float(self.pct_percentile_2y),
            "pct_percentile_3y": self._json_float(self.pct_percentile_3y),
            "pct_percentile_4y": self._json_float(self.pct_percentile_4y),
            "pct_percentile_5y": self._json_float(self.pct_percentile_5y),
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
            "current_league": self.current_league,  # Categorical (league key or "Other")
            "league_tier": self.league_tier,  # Categorical ("1", "2", "3", "4", "youth", "cup", "Other")
            "current_club_value_M": self.current_club_value / 1_000_000,
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
            "pct_6m": self.pct_6m,
            "pct_1y": self.pct_1y,
            "pct_2y": self.pct_2y,
            "pct_4y": self.pct_4y,
            "pct_5y": self.pct_5y,
            "diff_6m_M": self.diff_6m / 1_000_000,
            "diff_1y_M": self.diff_1y / 1_000_000,
            "diff_2y_M": self.diff_2y / 1_000_000,
            "diff_4y_M": self.diff_4y / 1_000_000,
            "diff_5y_M": self.diff_5y / 1_000_000,
            "months_since_peak": float(self.months_since_peak),
            "num_valuations": float(self.num_valuations),
            "months_of_history": float(self.months_of_history),
            "current_value_percentile": float(self.current_value_percentile),
            "value_6m_ago_percentile": self._safe_float(self.value_6m_ago_percentile),
            "value_1y_ago_percentile": self._safe_float(self.value_1y_ago_percentile),
            "value_2y_ago_percentile": self._safe_float(self.value_2y_ago_percentile),
            "value_3y_ago_percentile": self._safe_float(self.value_3y_ago_percentile),
            "value_4y_ago_percentile": self._safe_float(self.value_4y_ago_percentile),
            "value_5y_ago_percentile": self._safe_float(self.value_5y_ago_percentile),
            "diff_percentile_6m": self._safe_float(self.diff_percentile_6m),
            "diff_percentile_1y": self._safe_float(self.diff_percentile_1y),
            "diff_percentile_2y": self._safe_float(self.diff_percentile_2y),
            "diff_percentile_3y": self._safe_float(self.diff_percentile_3y),
            "diff_percentile_4y": self._safe_float(self.diff_percentile_4y),
            "diff_percentile_5y": self._safe_float(self.diff_percentile_5y),
            "trend_percentile_6m": self._safe_float(self.trend_percentile_6m),
            "trend_percentile_1y": self._safe_float(self.trend_percentile_1y),
            "trend_percentile_2y": self._safe_float(self.trend_percentile_2y),
            "trend_percentile_3y": self._safe_float(self.trend_percentile_3y),
            "trend_percentile_4y": self._safe_float(self.trend_percentile_4y),
            "trend_percentile_5y": self._safe_float(self.trend_percentile_5y),
            "pct_percentile_6m": self._safe_float(self.pct_percentile_6m),
            "pct_percentile_1y": self._safe_float(self.pct_percentile_1y),
            "pct_percentile_2y": self._safe_float(self.pct_percentile_2y),
            "pct_percentile_3y": self._safe_float(self.pct_percentile_3y),
            "pct_percentile_4y": self._safe_float(self.pct_percentile_4y),
            "pct_percentile_5y": self._safe_float(self.pct_percentile_5y),
        }


def _compute_age(birth_date_str: str, reference_date: datetime) -> Optional[float]:
    """Compute age as a float (e.g. 23.5) from a DD/MM/YYYY birth date string."""
    bd = parse_date(birth_date_str)
    if bd is None:
        return None
    delta = reference_date - bd
    age = delta.days / 365.25
    return max(age, 0.0)


def _get_value_at_date(
    valuations: List[Tuple[datetime, float]],
    target_date: datetime,
    tolerance_days: int = 90,
) -> Optional[float]:
    """
    Get valuation closest to target_date within tolerance.
    Uses binary search when list is sorted by date (O(log n) vs O(n)).
    """
    if not valuations:
        return None
    
    tolerance = timedelta(days=tolerance_days)
    # Binary search for closest date (list must be sorted by date)
    dates = [v[0] for v in valuations]
    idx = bisect.bisect_left(dates, target_date)
    candidates: List[Tuple[timedelta, float]] = []
    if idx < len(dates):
        candidates.append((abs(dates[idx] - target_date), valuations[idx][1]))
    if idx > 0:
        candidates.append((abs(dates[idx - 1] - target_date), valuations[idx - 1][1]))
    if not candidates:
        return None
    best_diff, best_val = min(candidates, key=lambda x: x[0])
    return best_val if best_diff <= tolerance else None


def _compute_trend(current: float, past: Optional[float]) -> float:
    """Compute percentage change from past to current.
    
    If past == 0, uses max(past, 1) to avoid division by zero.
    """
    if past is None:
        return 0.0
    denom = max(past, 1)
    return (current - past) / denom


def _compute_pct(current: float, past: Optional[float]) -> float:
    """Compute ratio current / past.
    
    If past == 0, uses max(past, 1) to avoid division by zero.
    """
    if past is None:
        return 0.0
    denom = max(past, 1)
    return current / denom


def _compute_diff(current: float, past: Optional[float]) -> float:
    """Compute difference current - past."""
    if past is None:
        return 0.0
    return current - past


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


# Horizons for percentile features (attribute suffix)
_PERCENTILE_HORIZONS = ["6m", "1y", "2y", "3y", "4y", "5y"]


def _load_float(x: Optional[float], default: float = 0.0) -> float:
    """Load float from JSON; None -> default (for backward compat with old datasets)."""
    if x is None:
        return default
    return float(x)


def _percentile_rank(values: List[float], x: float) -> float:
    """
    Compute percentile rank of x within values (0-100).
    Uses 'rank' method: (count of values <= x) / n * 100.
    (Kept for small inputs; use _percentile_ranks_vectorized for large batches.)
    """
    if not values:
        return 0.0
    n = len(values)
    count = sum(1 for v in values if v <= x)
    return 100.0 * count / n


def _percentile_ranks_vectorized(values: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """
    Compute percentile rank (0-100) for each value: (count of values <= x) / n * 100.
    O(n log n) via sort + searchsorted instead of O(n²) with naive per-element rank.

    Args:
        values: array of values (may contain NaN)
        mask: boolean mask, True = use this value in distribution and compute its percentile

    Returns:
        array same shape as values; percentile for masked positions, np.nan for others
    """
    valid = values[mask].astype(float)
    if len(valid) == 0:
        return np.full(len(values), np.nan, dtype=float)
    n = len(valid)
    valid_sorted = np.sort(valid)
    # For each valid value: count how many <= it, then pct = count/n*100
    counts = np.searchsorted(valid_sorted, valid, side="right")
    percentiles_valid = 100.0 * counts / n
    out = np.full(len(values), np.nan, dtype=float)
    out[mask] = percentiles_valid
    return out


def _compute_percentile_features(batch: List[PlayerFeatures], verbose: bool = False) -> None:
    """
    Compute all percentile features for a batch (mutates in place).
    Requires distribution per cutoff - call once per cutoff batch.
    Uses vectorized percentile computation for O(n log n) instead of O(n²).
    """
    if not batch:
        return
    n = len(batch)
    # Current value percentile (vectorized)
    current_values = np.array([f.current_value for f in batch], dtype=float)
    mask_curr = np.isfinite(current_values)
    pct_arr = _percentile_ranks_vectorized(current_values, mask_curr)
    for i, f in enumerate(batch):
        f.current_value_percentile = float(pct_arr[i]) if mask_curr[i] else np.nan

    # Historical value percentiles and derived (diff, trend, pct)
    horizons_iter = tqdm(_PERCENTILE_HORIZONS, desc="Computing percentile features", disable=not verbose)
    for h in horizons_iter:
        attr_val = f"value_{h}_ago"
        attr_pct = f"value_{h}_ago_percentile"
        attr_diff = f"diff_percentile_{h}"
        attr_trend = f"trend_percentile_{h}"
        attr_pct_pct = f"pct_percentile_{h}"
        raw = np.array([getattr(f, attr_val) if getattr(f, attr_val) is not None else np.nan for f in batch], dtype=float)
        mask_finite = np.isfinite(raw)
        pct_arr = _percentile_ranks_vectorized(raw, mask_finite)
        for i, f in enumerate(batch):
            pct = float(pct_arr[i]) if mask_finite[i] else np.nan
            setattr(f, attr_pct, pct)
            curr = f.current_value_percentile
            past = pct
            if not np.isnan(past):
                setattr(f, attr_diff, curr - past)
                denom = max(past, 1.0)
                setattr(f, attr_trend, (curr - past) / denom)
                setattr(f, attr_pct_pct, curr / denom)
            else:
                setattr(f, attr_diff, np.nan)
                setattr(f, attr_trend, np.nan)
                setattr(f, attr_pct_pct, np.nan)


def _get_league_and_tier(league_id: str) -> Tuple[str, str]:
    """Get league_key and tier from league_id. Returns ('Other', 'Other') if not in LEAGUE_INFO."""
    if not league_id:
        return "Other", "Other"
    info = LEAGUE_ID_TO_KEY_AND_TIER.get(league_id)
    if info is None:
        return "Other", "Other"
    return info


def _bin_club(club: str) -> str:
    """Bin club to top categories or 'Other'."""
    if not club:
        return "Other"
    if club in TOP_CLUBS:
        return club
    return "Other"


def _load_all_transfers(verbose: bool = False) -> List[Transfer]:
    """Load ALL ``transfers_all_*.json`` files into a flat list. Supports multi-part files."""
    transfers: List[Transfer] = []
    bases = list_json_bases("transfers_all_*.json")
    base_iter = tqdm(bases, desc="Loading transfers", disable=not verbose)

    for base in base_iter:
        if verbose:
            base_iter.set_postfix_str(base)
        data = load_json(base)
        if not isinstance(data, list):
            continue
        for item in tqdm(data, desc=f"  {base}", disable=not verbose, leave=False):
            if isinstance(item, dict):
                transfers.append(Transfer.from_dict(item))
    return transfers


def _process_transfer_file_for_cutoff(
    base: str, cutoff_date: datetime
) -> Dict[str, Tuple[datetime, Transfer]]:
    """
    Load one transfer file and return partial best map (player_id -> (date, Transfer)).
    Used for parallel loading.
    """
    partial: Dict[str, Tuple[datetime, Transfer]] = {}
    data = load_json(base)
    if not isinstance(data, list):
        return partial
    for item in data:
        if not isinstance(item, dict):
            continue
        date_str = item.get("transfer_date") or ""
        td = _parse_date_cached(date_str)
        if td is None or td > cutoff_date:
            continue
        pid = item.get("player_id", "")
        if not pid:
            continue
        pid = str(pid)
        prev = partial.get(pid)
        if prev is None or td > prev[0]:
            partial[pid] = (td, Transfer.from_dict(item))
    return partial


def _load_transfer_map_at_cutoff_date(
    cutoff_date: datetime, verbose: bool = False
) -> Dict[str, Transfer]:
    """
    Build transfer_map (player_id -> last Transfer before cutoff) by loading
    transfer files. Uses parallel I/O when multiple files, orjson for fast parsing.
    """
    bases = list_json_bases("transfers_all_*.json")
    if verbose:
        tqdm.write("  Loading transfer map (for club assignment)...")

    best: Dict[str, Tuple[datetime, Transfer]] = {}

    if len(bases) <= 1:
        for base in bases:
            partial = _process_transfer_file_for_cutoff(base, cutoff_date)
            for pid, (td, t) in partial.items():
                prev = best.get(pid)
                if prev is None or td > prev[0]:
                    best[pid] = (td, t)
    else:
        # Parallel load and process
        max_workers = min(len(bases), 4)
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_process_transfer_file_for_cutoff, base, cutoff_date): base for base in bases}
            done = tqdm(as_completed(futures), total=len(futures), desc="Loading transfer map", disable=not verbose)
            for future in done:
                if verbose:
                    base = futures[future]
                    done.set_postfix_str(base)
                partial = future.result()
                for pid, (td, t) in partial.items():
                    prev = best.get(pid)
                    if prev is None or td > prev[0]:
                        best[pid] = (td, t)

    return {pid: tr for pid, (_, tr) in best.items()}


def _get_team_total_values_at_cutoff(
    by_player: Dict[str, List[Valuation]],
    transfer_map: Dict[str, Transfer],
    cutoff_date: datetime,
    verbose: bool = False,
) -> Dict[str, float]:
    """
    Compute sum of market values per team at cutoff (single O(players) pass).
    Used for current_club_value feature.
    """
    team_totals: Dict[str, float] = {}
    items_iter = tqdm(by_player.items(), desc="Team total values", disable=not verbose)
    for player_id, vals in items_iter:
        t = transfer_map.get(player_id)
        if not t or not t.to_club_id:
            continue
        val_list = []
        for v in vals:
            d = _parse_date_cached(v.valuation_date or "")
            if d is not None and v.valuation_amount is not None:
                val_list.append((d, v.valuation_amount))
        if not val_list:
            continue
        val_list.sort(key=lambda x: x[0])
        v_at = _get_value_at_date(val_list, cutoff_date, tolerance_days=90)
        if v_at is not None and v_at > 0:
            tid = str(t.to_club_id)
            team_totals[tid] = team_totals.get(tid, 0.0) + v_at
    return team_totals


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
        td = parse_date(t.transfer_date)
        if td is None or td > cutoff_date:
            continue
        prev = best.get(t.player_id)
        if prev is None or td > prev[0]:
            best[t.player_id] = (td, t)
    return {pid: tr for pid, (_, tr) in best.items()}


def _get_transfer_maps_for_all_cutoffs(
    all_transfers: List[Transfer],
    cutoff_dates: List[datetime],
) -> Dict[datetime, Dict[str, Transfer]]:
    """
    Build transfer maps for all cutoffs in a single O(transfers) pass.
    Much faster than calling _get_transfer_map_at_cutoff per cutoff.
    """
    if not all_transfers or not cutoff_dates:
        return {c: {} for c in cutoff_dates}
    # Parse and sort transfers by date
    parsed: List[Tuple[datetime, Transfer]] = []
    for t in all_transfers:
        td = parse_date(t.transfer_date)
        if td is not None:
            parsed.append((td, t))
    parsed.sort(key=lambda x: x[0])
    sorted_cutoffs = sorted(cutoff_dates)
    # Single pass: process transfers in order, snapshot best per player at each cutoff
    result: Dict[datetime, Dict[str, Transfer]] = {}
    best: Dict[str, Tuple[datetime, Transfer]] = {}
    transfer_idx = 0
    for cutoff in sorted_cutoffs:
        while transfer_idx < len(parsed) and parsed[transfer_idx][0] <= cutoff:
            td, t = parsed[transfer_idx]
            pid = t.player_id
            prev = best.get(pid)
            if prev is None or td > prev[0]:
                best[pid] = (td, t)
            transfer_idx += 1
        result[cutoff] = {pid: tr for pid, (_, tr) in best.items()}
    return result


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


def load_team_league_mapping(verbose: bool = False) -> Dict[str, Dict[str, Dict[str, str]]]:
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

    # Load from all teams_all_*.json files (supports multi-part)
    bases = list(list_json_bases("teams_all_*.json"))
    iterator = tqdm(bases, desc="Loading team-league mapping", disable=not verbose)
    for base in iterator:
        season = base.replace("teams_all_", "")

        try:
            teams = load_json(base)
            if teams is None:
                continue

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
    team_total_values: Optional[Dict[str, float]] = None,
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
        team_total_values: Optional dict team_id -> sum of squad market values at cutoff.
            If provided, current_club_value is looked up. If None, current_club_value=0.
    
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
        val_date = parse_date(v.valuation_date)
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
        age = float(last_val.age_at_valuation or (player_info.age if player_info else None) or 25)
    
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

    # Current league and tier (from LEAGUE_INFO, or "Other" if unknown)
    current_league, league_tier = _get_league_and_tier(league_id)

    # Is in home league? Check if player nationality matches team's country
    is_in_home_league = _is_home_league(player_nationality, team_country)

    current_club_bin = _bin_club(current_club)
    team_total_values = team_total_values or {}
    current_club_value = team_total_values.get(club_id, 0.0) if club_id else 0.0
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
    
    # Percent (current / past)
    pct_6m = _compute_pct(current_value, value_6m_ago)
    pct_1y = _compute_pct(current_value, value_1y_ago)
    pct_2y = _compute_pct(current_value, value_2y_ago)
    pct_4y = _compute_pct(current_value, value_4y_ago)
    pct_5y = _compute_pct(current_value, value_5y_ago)
    
    # Difference (current - past)
    diff_6m = _compute_diff(current_value, value_6m_ago)
    diff_1y = _compute_diff(current_value, value_1y_ago)
    diff_2y = _compute_diff(current_value, value_2y_ago)
    diff_4y = _compute_diff(current_value, value_4y_ago)
    diff_5y = _compute_diff(current_value, value_5y_ago)
    
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
        current_league=current_league,
        league_tier=league_tier,
        current_club=current_club,
        current_club_value=current_club_value,
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
        pct_6m=pct_6m,
        pct_1y=pct_1y,
        pct_2y=pct_2y,
        pct_4y=pct_4y,
        pct_5y=pct_5y,
        diff_6m=diff_6m,
        diff_1y=diff_1y,
        diff_2y=diff_2y,
        diff_4y=diff_4y,
        diff_5y=diff_5y,
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


def _process_cutoff_batch(
    cutoff_date: datetime,
    by_player: Dict[str, List[Valuation]],
    transfer_map: Dict[str, Transfer],
    players: Optional[Dict[str, Player]],
    team_league_mapping: Optional[Dict[str, Dict[str, Dict[str, str]]]],
    min_valuations: int,
) -> Tuple[datetime, str, List[PlayerFeatures]]:
    """Process one cutoff: extract features for all players, compute percentiles."""
    cutoff_season = _get_season_for_cutoff(cutoff_date)
    team_total_values = _get_team_total_values_at_cutoff(by_player, transfer_map, cutoff_date)
    batch: List[PlayerFeatures] = []
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
            team_total_values=team_total_values,
        )
        if features and features.target_value is not None:
            batch.append(features)
    if batch:
        _compute_percentile_features(batch, verbose=False)
    return (cutoff_date, cutoff_season, batch)


def build_training_dataset(
    all_valuations: List[Valuation],
    players: Optional[Dict[str, Player]] = None,
    team_league_mapping: Optional[Dict[str, Dict[str, Dict[str, str]]]] = None,
    min_valuations: int = 3,
    cutoff_dates: Optional[List[datetime]] = None,
    cutoff_months: int = 12,
    all_transfers: Optional[List[Transfer]] = None,
    n_jobs: int = 1,
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
        n_jobs: Number of parallel workers for cutoff processing (default 1 = sequential)
    
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
    
    # Precompute transfer maps for all cutoffs in one pass (O(transfers) vs O(transfers × cutoffs))
    transfer_maps = _get_transfer_maps_for_all_cutoffs(all_transfers, cutoff_dates)
    
    # Process cutoffs (parallel if n_jobs > 1)
    cutoff_results: List[Tuple[datetime, str, List[PlayerFeatures]]] = []
    if n_jobs <= 1:
        for cutoff_date in cutoff_dates:
            transfer_map = transfer_maps[cutoff_date]
            res = _process_cutoff_batch(
                cutoff_date, by_player, transfer_map,
                players, team_league_mapping, min_valuations,
            )
            cutoff_results.append(res)
            print(f"  Cutoff {res[0].strftime('%Y-%m-%d')} ({res[1]}): {len(res[2])} players")
    else:
        with ThreadPoolExecutor(max_workers=n_jobs) as executor:
            futures = {
                executor.submit(
                    _process_cutoff_batch,
                    cutoff_date, by_player, transfer_maps[cutoff_date],
                    players, team_league_mapping, min_valuations,
                ): cutoff_date
                for cutoff_date in cutoff_dates
            }
            results_by_date: Dict[datetime, Tuple[datetime, str, List[PlayerFeatures]]] = {}
            for future in as_completed(futures):
                res = future.result()
                results_by_date[res[0]] = res
            for cutoff_date in cutoff_dates:
                cutoff_results.append(results_by_date[cutoff_date])
                r = results_by_date[cutoff_date]
                print(f"  Cutoff {r[0].strftime('%Y-%m-%d')} ({r[1]}): {len(r[2])} players")
    
    for _, _, batch in cutoff_results:
        dataset.extend(batch)
    
    print(f"Total training samples: {len(dataset)} "
          f"({len(cutoff_dates)} cutoffs x ~{len(dataset) // max(1, len(cutoff_dates))} players/cutoff)")
    
    return dataset


# ============================================================================
# Dataset Persistence (Save/Load)
# ============================================================================

DATASETS_DIR = Path(__file__).parent / "datasets"

# Maximum file size per part (90 MB leaves headroom under GitHub's 100 MB limit)
_MAX_PART_BYTES = 90 * 1024 * 1024


def _get_dataset_path(cutoff_months: int = 12) -> Path:
    """Get base path for the training dataset file."""
    return DATASETS_DIR / f"training_dataset_{cutoff_months}m.json"


def _get_part_paths(base_path: Path) -> List[Path]:
    """Return sorted list of existing part files for a dataset.
    
    Parts follow the pattern ``<base_stem>_part1.json``, ``<base_stem>_part2.json``, …
    Falls back to the single-file ``<base>.json`` if no parts exist.
    """
    stem = base_path.stem  # e.g. "training_dataset_12m"
    parts = sorted(base_path.parent.glob(f"{stem}_part*.json"))
    if parts:
        return parts
    # Legacy single file
    if base_path.exists():
        return [base_path]
    return []


def save_training_dataset(
    dataset: List[PlayerFeatures],
    cutoff_months: int = 12,
) -> Path:
    """
    Save training dataset to one or more JSON files.

    If the full dataset exceeds ``_MAX_PART_BYTES`` it is automatically
    split into ``*_part1.json``, ``*_part2.json``, … so that each file
    stays under 90 MB (safely below GitHub's 100 MB limit).

    Args:
        dataset: List of PlayerFeatures to save
        cutoff_months: Frequency used to generate dataset (for filename)

    Returns:
        Path to the base file (or first part)
    """
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    base_path = _get_dataset_path(cutoff_months)

    # Convert to list of dicts
    data = [f.to_dict() for f in dataset]

    metadata = {
        "cutoff_months": cutoff_months,
        "num_samples": len(dataset),
        "created_at": datetime.now().isoformat(),
        "cutoff_seasons": sorted(set(f.cutoff_season for f in dataset)),
    }

    # ── Try writing as a single file first ──────────────────────────────
    full_output = {"metadata": metadata, "samples": data}
    full_blob = json.dumps(full_output, indent=2, default=str).encode("utf-8")

    if len(full_blob) <= _MAX_PART_BYTES:
        # Clean up old part files if they exist
        for old_part in base_path.parent.glob(f"{base_path.stem}_part*.json"):
            old_part.unlink()
        with open(base_path, "wb") as f:
            f.write(full_blob)
        print(f"Saved training dataset to: {base_path}")
        print(f"  Samples: {len(dataset)}")
        print(f"  Size: {len(full_blob)/1e6:.1f} MB (single file)")
        return base_path

    # ── Split into parts ────────────────────────────────────────────────
    # Remove legacy single file
    if base_path.exists():
        base_path.unlink()
    # Remove old parts
    for old_part in base_path.parent.glob(f"{base_path.stem}_part*.json"):
        old_part.unlink()

    # Estimate how many parts we need (conservative)
    num_parts = max(2, -(-len(full_blob) // _MAX_PART_BYTES))  # ceil division
    chunk_size = -(-len(data) // num_parts)  # samples per part (ceil)

    part_paths: List[Path] = []
    for i in range(num_parts):
        chunk = data[i * chunk_size : (i + 1) * chunk_size]
        if not chunk:
            break
        part_meta = {**metadata, "part": i + 1, "total_parts": num_parts}
        part_output = {"metadata": part_meta, "samples": chunk}
        part_path = base_path.parent / f"{base_path.stem}_part{i + 1}.json"
        with open(part_path, "w", encoding="utf-8") as f:
            json.dump(part_output, f, indent=2, default=str)
        part_paths.append(part_path)

    print(f"Saved training dataset in {len(part_paths)} parts:")
    for pp in part_paths:
        sz = pp.stat().st_size / 1e6
        print(f"  {pp.name}  ({sz:.1f} MB)")
    print(f"  Total samples: {len(dataset)}")
    print(f"  Cutoff frequency: {cutoff_months} months")
    print(f"  Seasons: {metadata['cutoff_seasons']}")

    return part_paths[0]


def load_training_dataset(cutoff_months: int = 12) -> Optional[List[PlayerFeatures]]:
    """
    Load training dataset from JSON file(s).

    Supports both a single file and multi-part datasets
    (``*_part1.json``, ``*_part2.json``, …).

    Args:
        cutoff_months: Frequency used to generate dataset (for filename)

    Returns:
        List of PlayerFeatures or None if no files exist
    """
    base_path = _get_dataset_path(cutoff_months)
    part_paths = _get_part_paths(base_path)

    if not part_paths:
        return None

    all_samples: list = []
    metadata: dict = {}

    for pp in part_paths:
        with open(pp, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not metadata:
            metadata = data.get("metadata", {})
        all_samples.extend(data.get("samples", []))

    num_files = len(part_paths)
    label = f"{num_files} part(s)" if num_files > 1 else "single file"
    print(f"Loading training dataset ({label}):")
    for pp in part_paths:
        print(f"  {pp.name}")
    print(f"  Samples: {metadata.get('num_samples', len(all_samples))}")
    print(f"  Created: {metadata.get('created_at', 'unknown')}")
    print(f"  Seasons: {metadata.get('cutoff_seasons', [])}")

    # Convert dicts back to PlayerFeatures
    dataset = []
    for item in all_samples:
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
            current_league=item.get("current_league", "Other"),
            league_tier=item.get("league_tier", "Other"),
            current_club=item.get("current_club", ""),
            current_club_value=item.get("current_club_value", 0.0),
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
            pct_6m=item.get("pct_6m", 0),
            pct_1y=item.get("pct_1y", 0),
            pct_2y=item.get("pct_2y", 0),
            pct_4y=item.get("pct_4y", 0),
            pct_5y=item.get("pct_5y", 0),
            diff_6m=item.get("diff_6m", 0),
            diff_1y=item.get("diff_1y", 0),
            diff_2y=item.get("diff_2y", 0),
            diff_4y=item.get("diff_4y", 0),
            diff_5y=item.get("diff_5y", 0),
            months_since_peak=item.get("months_since_peak", 0),
            num_valuations=item.get("num_valuations", 0),
            months_of_history=item.get("months_of_history", 0),
            current_value_percentile=item.get("current_value_percentile", 0.0),
            value_6m_ago_percentile=_load_float(item.get("value_6m_ago_percentile"), 0.0),
            value_1y_ago_percentile=_load_float(item.get("value_1y_ago_percentile"), 0.0),
            value_2y_ago_percentile=_load_float(item.get("value_2y_ago_percentile"), 0.0),
            value_3y_ago_percentile=_load_float(item.get("value_3y_ago_percentile"), 0.0),
            value_4y_ago_percentile=_load_float(item.get("value_4y_ago_percentile"), 0.0),
            value_5y_ago_percentile=_load_float(item.get("value_5y_ago_percentile"), 0.0),
            diff_percentile_6m=_load_float(item.get("diff_percentile_6m"), 0.0),
            diff_percentile_1y=_load_float(item.get("diff_percentile_1y"), 0.0),
            diff_percentile_2y=_load_float(item.get("diff_percentile_2y"), 0.0),
            diff_percentile_3y=_load_float(item.get("diff_percentile_3y"), 0.0),
            diff_percentile_4y=_load_float(item.get("diff_percentile_4y"), 0.0),
            diff_percentile_5y=_load_float(item.get("diff_percentile_5y"), 0.0),
            trend_percentile_6m=_load_float(item.get("trend_percentile_6m"), 0.0),
            trend_percentile_1y=_load_float(item.get("trend_percentile_1y"), 0.0),
            trend_percentile_2y=_load_float(item.get("trend_percentile_2y"), 0.0),
            trend_percentile_3y=_load_float(item.get("trend_percentile_3y"), 0.0),
            trend_percentile_4y=_load_float(item.get("trend_percentile_4y"), 0.0),
            trend_percentile_5y=_load_float(item.get("trend_percentile_5y"), 0.0),
            pct_percentile_6m=_load_float(item.get("pct_percentile_6m"), 0.0),
            pct_percentile_1y=_load_float(item.get("pct_percentile_1y"), 0.0),
            pct_percentile_2y=_load_float(item.get("pct_percentile_2y"), 0.0),
            pct_percentile_3y=_load_float(item.get("pct_percentile_3y"), 0.0),
            pct_percentile_4y=_load_float(item.get("pct_percentile_4y"), 0.0),
            pct_percentile_5y=_load_float(item.get("pct_percentile_5y"), 0.0),
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


def build_prediction_context(
    all_valuations: List[Valuation],
    cutoff_date: datetime,
    all_transfers: Optional[List[Transfer]] = None,
    verbose: bool = False,
) -> Tuple[Dict[str, Transfer], Dict[str, List[Valuation]], Dict[str, float]]:
    """
    Build transfer_map, by_player, team_total_values for prediction.
    Reusable across multiple build_prediction_dataset calls (same cutoff).
    """
    if all_transfers is None:
        transfer_map = _load_transfer_map_at_cutoff_date(cutoff_date, verbose=verbose)
    else:
        transfer_map = _get_transfer_map_at_cutoff(all_transfers, cutoff_date)

    by_player: Dict[str, List[Valuation]] = defaultdict(list)
    val_iter = tqdm(all_valuations, desc="Grouping valuations by player", disable=not verbose)
    for v in val_iter:
        by_player[v.player_id].append(v)

    team_total_values = _get_team_total_values_at_cutoff(
        by_player, transfer_map, cutoff_date, verbose=verbose
    )
    return transfer_map, by_player, team_total_values


def build_prediction_dataset(
    all_valuations: List[Valuation],
    cutoff_date: datetime,
    players: Optional[Dict[str, Player]] = None,
    team_league_mapping: Optional[Dict[str, Dict[str, Dict[str, str]]]] = None,
    min_valuations: int = 2,
    all_transfers: Optional[List[Transfer]] = None,
    transfer_map: Optional[Dict[str, Transfer]] = None,
    by_player: Optional[Dict[str, List[Valuation]]] = None,
    team_total_values: Optional[Dict[str, float]] = None,
    verbose: bool = False,
) -> List[PlayerFeatures]:
    """
    Build dataset for prediction (no target required).

    Current club is determined from transfer data (last transfer <= cutoff).
    Age is computed from birth_date + cutoff_date.

    Optional transfer_map, by_player, team_total_values allow reusing precomputed
    context (avoids rebuilding when predicting for multiple player sets).
    """
    if transfer_map is None:
        if all_transfers is None:
            transfer_map = _load_transfer_map_at_cutoff_date(cutoff_date, verbose=verbose)
        else:
            transfer_map = _get_transfer_map_at_cutoff(all_transfers, cutoff_date)

    if by_player is None:
        by_player = defaultdict(list)
        val_iter = tqdm(all_valuations, desc="Grouping valuations by player", disable=not verbose)
        for v in val_iter:
            by_player[v.player_id].append(v)

    if team_total_values is None:
        team_total_values = _get_team_total_values_at_cutoff(
            by_player, transfer_map, cutoff_date, verbose=verbose
        )

    # When players dict is provided, only process those player_ids (reduces work when filtered)
    if players:
        items = [(pid, vals) for pid, vals in by_player.items() if pid in players]
    else:
        items = list(by_player.items())
    dataset: List[PlayerFeatures] = []
    iterator = tqdm(items, desc="Building prediction features", disable=not verbose)
    for player_id, player_vals in iterator:
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
            team_total_values=team_total_values,
        )
        
        if features:
            dataset.append(features)
    
    # Compute percentile features per cutoff
    if dataset:
        _compute_percentile_features(dataset, verbose=verbose)
    
    return dataset
