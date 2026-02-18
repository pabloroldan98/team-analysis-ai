"""
Transfer window simulator.

Simulates a club's transfer window by:
1. Selling random players from the squad
2. Using ML model to predict future values
3. Finding optimal signings using knapsack optimization

Usage:
    from simulator.transfer_simulator import TransferSimulator
    
    sim = TransferSimulator(
        club_name="Real Madrid",
        season="2023-2024",
        transfer_budget=100,  # millions
        salary_budget=15,     # millions (annual)
    )
    result = sim.run()
"""
from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tqdm import tqdm

from player import Player
from transfer import Transfer
from valuation import Valuation
from simulator.knapsack_solver import best_full_teams
from scraping.utils.helpers import list_json_bases, load_json
from ml.feature_engineering import TOP_LEAGUE_IDS, load_team_league_mapping

# Paths
ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data" / "json"
MODELS_DIR = ROOT_DIR / "ml" / "models"

# Teams that are NOT valid destinations when selling (they are not real clubs)
INVALID_DESTINATION_TEAM_IDS = {"515", "2113", "123"}  # Without Club, Career break, Retired
INVALID_DESTINATION_TEAM_NAMES = {"without club", "career break", "retired"}

# Teams whose players should NOT be available for signing
INVALID_ORIGIN_TEAM_IDS = {"123"}    # Retired
INVALID_ORIGIN_TEAM_NAMES = {"retired"}

# Athletic Bilbao family – the club can only BUY players who have played
# for any of these clubs at some point in their career.
ATHLETIC_FAMILY_IDS = {
    "621",     # Athletic Bilbao
    "6688",    # Bilbao Athletic
    "45511",   # Athletic Bilbao UEFA U19
    "28860",   # Athletic Bilbao U19
    "107198",  # Athletic Bilbao U18
    "14733",   # Athletic Bilbao Youth
    "6665",    # CD Basconia
}
ATHLETIC_FAMILY_NAMES = {
    "athletic bilbao",
    "bilbao athletic",
    "athletic bilbao uefa u19",
    "athletic bilbao u19",
    "athletic bilbao u18",
    "athletic bilbao youth",
    "cd basconia",
}
ATHLETIC_BILBAO_ID = "621"

# Minimum market value (euros) for players outside top leagues when filtering
MIN_FILTER_MARKET_VALUE = 10_000_000


@dataclass
class SoldPlayer:
    """A player that was sold with destination info."""
    player: Player
    destination_team: Optional[str]  # None if no team could afford them
    
    @property
    def was_sold(self) -> bool:
        return self.destination_team is not None


@dataclass
class TransferResult:
    """Result of a transfer simulation."""
    
    club_name: str
    season: str
    
    # Budget
    initial_budget: int  # millions
    sales_revenue: int   # millions
    total_budget: int    # millions
    
    # Players sold (with destination)
    players_sold: List[SoldPlayer] = field(default_factory=list)
    formation_needed: List[int] = field(default_factory=list)  # [GK, DEF, MID, ATT] needed
    
    # Recommended signings
    recommended_signings: List[Player] = field(default_factory=list)
    recommended_formation: List[int] = field(default_factory=list)
    total_signing_cost: int = 0  # millions
    total_predicted_value: float = 0.0  # millions
    
    # Current squad (for context in LLM summary)
    current_squad: List[Player] = field(default_factory=list)
    
    # LLM summary (optional)
    llm_summary: Optional[str] = None
    
    def __str__(self) -> str:
        sold_count = sum(1 for sp in self.players_sold if sp.was_sold)
        unsold_count = len(self.players_sold) - sold_count
        
        lines = [
            f"\n{'='*60}",
            f"Transfer Simulation: {self.club_name} ({self.season})",
            f"{'='*60}",
            f"\nBudget:",
            f"  Initial:      €{self.initial_budget}M",
            f"  Sales:       +€{self.sales_revenue}M",
            f"  Total:        €{self.total_budget}M",
            f"\nPlayers Sold ({sold_count} sold, {unsold_count} no buyer found):",
        ]
        
        for sp in self.players_sold:
            p = sp.player
            mv = (p.market_value or 0) / 1e6
            if sp.was_sold:
                lines.append(f"  - {p.name} ({p.position}): €{mv:.1f}M -> {sp.destination_team}")
            else:
                lines.append(f"  - {p.name} ({p.position}): €{mv:.1f}M -> NO BUYER FOUND")
        
        # Format formation as "GK: X, DEF: Y, MID: Z, ATT: W"
        formation_str = f"GK: {self.formation_needed[0]}, DEF: {self.formation_needed[1]}, MID: {self.formation_needed[2]}, ATT: {self.formation_needed[3]}"
        lines.append(f"\nRecommended Signings ({formation_str}):")
        
        for p in self.recommended_signings:
            mv = (p.market_value or 0) / 1e6
            pv = (p.predicted_value or 0) / 1e6
            lines.append(f"  - {p.name} ({p.position}, from {p.team}): €{mv:.1f}M -> €{pv:.1f}M predicted")
        
        # Calculate totals from actual player values
        actual_total_cost = sum((p.market_value or 0) for p in self.recommended_signings) / 1e6
        actual_total_predicted = sum((p.predicted_value or 0) for p in self.recommended_signings) / 1e6
        remaining_budget = self.total_budget - actual_total_cost
        
        # Expected Net Financial Benefit = predicted value - cost
        expected_net_benefit = actual_total_predicted - actual_total_cost
        
        lines.append(f"\nBudget available: €{self.total_budget}M")
        lines.append(f"Total cost: €{actual_total_cost:.1f}M")
        lines.append(f"Remaining budget: €{remaining_budget:.1f}M")
        lines.append(f"Total predicted value (1 year): €{actual_total_predicted:.1f}M")
        lines.append(f"Expected Net Financial Benefit (1 year): €{expected_net_benefit:+.1f}M")
        
        # Include LLM summary if available
        if self.llm_summary:
            lines.append(f"\n{'='*60}")
            lines.append("AI ANALYSIS:")
            lines.append(f"{'='*60}")
            lines.append(self.llm_summary)
        
        lines.append(f"{'='*60}")
        
        return "\n".join(lines)
    
    def generate_llm_summary(
        self,
        provider: Optional[str] = None,
        api_key: Optional[str] = None,
        language: Optional[str] = None,
    ) -> str:
        """
        Generate an LLM summary for this result.
        
        Args:
            provider: LLM provider ("openai", "anthropic", "gemini")
            api_key: Optional API key override
            language: Response language ("es", "en", etc.)
        
        Returns:
            Generated summary text (also stored in self.llm_summary)
        """
        from simulator.llm_summarizer import generate_summary_from_result
        
        self.llm_summary = generate_summary_from_result(
            result=self,
            provider=provider,
            api_key=api_key,
            language=language,
        )
        return self.llm_summary


class TransferSimulator:
    """
    Simulates a club's transfer window.
    """
    
    # Position mapping
    POSITION_GROUPS = {
        "GK": "GK",
        "DEF": "DEF",
        "MID": "MID",
        "ATT": "ATT",
    }
    
    def __init__(
        self,
        club_name: str,
        season: str,
        transfer_budget: int,  # millions
        salary_budget: int,    # millions (annual)
    ):
        """
        Initialize transfer simulator.
        
        Args:
            club_name: Name of the club (e.g., "Real Madrid")
            season: Season string (e.g., "2023-2024")
            transfer_budget: Transfer budget in millions
            salary_budget: Annual salary budget in millions
        """
        self.club_name = club_name
        self.season = season
        self.transfer_budget = transfer_budget
        self.salary_budget = salary_budget
        
        # Budget = min(transfer, salary * 10)
        self.budget = min(transfer_budget, salary_budget * 10)
        
        # Data containers
        self.club_players: List[Player] = []
        self.all_players: List[Player] = []
        self.team_market_values: Dict[str, float] = {}  # team_name -> total market value
        self.predictor = None
    
    def preload_data(
        self,
        verbose: bool = False,
        progress_callback: Optional[object] = None,
    ) -> List[Player]:
        """Load data, identify squad and calculate team values (steps 1-3).

        Call this before ``run()`` when you need to show the squad to the user
        (e.g. for manual sell selection).  The results are cached on the
        instance so that ``run(preloaded=True)`` can skip these steps.

        Returns:
            The club's player list.
        """
        def _progress(pct: float, key: str) -> None:
            if progress_callback is not None:
                progress_callback(pct, key)

        _progress(0.05, "step_loading")
        all_players = self._load_active_players(verbose=verbose)
        self.all_players = all_players

        _progress(0.20, "step_team")
        club_players = self._get_club_players(all_players)
        if not club_players:
            raise ValueError(f"No players found for club: {self.club_name}")
        self.club_players = club_players

        _progress(0.35, "step_team_values")
        self.team_market_values = self._calculate_team_market_values(all_players)

        self._athletic_eligible_ids: Optional[set] = None
        self._is_athletic = self._is_athletic_club()
        athletic_in_market = any(
            name.lower() in ATHLETIC_FAMILY_NAMES
            for name in self.team_market_values
        )
        if self._is_athletic or athletic_in_market:
            self._athletic_eligible_ids = self._load_athletic_eligible_ids(verbose=verbose)

        self._preloaded = True
        _progress(0.40, "step_team_values")
        return club_players

    def _load_active_players(self, verbose: bool = False) -> List[Player]:
        """
        Load active players at season start using the data_loader pipeline.

        Delegates to ``get_active_players_at_season_start`` which:
          1. Loads ALL players (all seasons)
          2. Assigns teams from transfers (last transfer <= 01/07)
          3. Filters out Retired / Without Club / Career break
          4. Updates market_value & age from valuations
        """
        from simulator.data_loader import get_active_players_at_season_start
        return get_active_players_at_season_start(self.season, verbose=verbose)
    
    def _load_predictor(self):
        """Load the ML model for this season.

        When season is ``"today"`` the most recent model file is used.
        """
        from ml.value_predictor import ValuePredictor

        if self.season.lower() == "today":
            # Pick the latest model by season name (alphabetical = chronological)
            candidates = sorted(MODELS_DIR.glob("value_model_*.joblib"))
            if not candidates:
                raise FileNotFoundError(
                    "No trained models found in ml/models/.\n"
                    "Run: python -m ml.train_pipeline --season <season>"
                )
            model_path = candidates[-1]
        else:
            model_path = MODELS_DIR / f"value_model_{self.season}.joblib"

        if not model_path.exists():
            raise FileNotFoundError(
                f"Model not found: {model_path}\n"
                f"Run: python -m ml.train_pipeline --season {self.season}"
            )
        
        self.predictor = ValuePredictor(model_path=model_path)
    
    def _predict_values(
        self,
        players: List[Player],
        verbose: bool = False,
        _cache: Optional[dict] = None,
    ) -> List[Player]:
        """
        Add predicted_value to each player using the ML model.

        When _cache is provided (internal use), reuses pre-loaded valuations,
        team_league_mapping, transfer_map, by_player, team_total_values to avoid
        rebuilding when predicting for multiple player sets (e.g. sell-by-decline).
        """
        from ml.feature_engineering import (
            build_prediction_context,
            build_prediction_dataset,
            load_team_league_mapping,
        )

        if not self.predictor:
            self._load_predictor()

        # Build features for prediction
        if self.season.lower() == "today":
            cutoff_date = datetime.now()
        else:
            start_year = int(self.season.split("-")[0])
            cutoff_date = datetime(start_year, 7, 1)

        # Use cached context if provided (avoids duplicate load when called twice, e.g. sell-by-decline)
        if _cache is not None and _cache.get("cutoff_date") == cutoff_date:
            all_valuations = _cache["all_valuations"]
            team_league_mapping = _cache["team_league_mapping"]
            transfer_map = _cache["transfer_map"]
            by_player = _cache["by_player"]
            team_total_values = _cache["team_total_values"]
            use_cache = True
        else:
            all_valuations = self._load_all_valuations(verbose=verbose)
            team_league_mapping = load_team_league_mapping(verbose=verbose)
            if verbose:
                print("  Building prediction dataset...", flush=True)
            transfer_map, by_player, team_total_values = build_prediction_context(
                all_valuations, cutoff_date, verbose=verbose
            )
            if _cache is not None:
                _cache["cutoff_date"] = cutoff_date
                _cache["all_valuations"] = all_valuations
                _cache["team_league_mapping"] = team_league_mapping
                _cache["transfer_map"] = transfer_map
                _cache["by_player"] = by_player
                _cache["team_total_values"] = team_total_values
            use_cache = False

        # Create player dict for feature extraction
        player_dict = {p.player_id: p for p in players}

        # Build prediction dataset (reuses transfer_map, by_player, team_total_values)
        features = build_prediction_dataset(
            all_valuations,
            cutoff_date,
            players=player_dict,
            team_league_mapping=team_league_mapping,
            transfer_map=transfer_map,
            by_player=by_player,
            team_total_values=team_total_values,
            verbose=verbose and not use_cache,
        )
        
        # Get predictions (single batch call, no tqdm needed)
        if features:
            predictions = self.predictor.predict_batch(features)
            
            # Map predictions back to players with progress bar
            pred_map = {f.player_id: pred for f, pred in zip(features, predictions)}
            
            iterator = tqdm(players, desc="    Assigning predictions", disable=not verbose)
            for player in iterator:
                if player.player_id in pred_map:
                    player.predicted_value = pred_map[player.player_id]
                else:
                    # Fallback: use market_value as prediction
                    player.predicted_value = player.market_value
        
        return players
    
    def _load_all_valuations(self, verbose: bool = False) -> List[Valuation]:
        """Load all valuations for feature extraction. Supports multi-part files."""
        all_valuations = []
        bases = list(list_json_bases("valuations_all_*.json"))
        base_iter = tqdm(bases, desc="Loading valuations", disable=not verbose)
        for base in base_iter:
            if verbose:
                base_iter.set_postfix_str(base)
            data = load_json(base)
            if isinstance(data, list):
                for item in tqdm(data, desc=f"  {base}", disable=not verbose, leave=False):
                    if isinstance(item, dict):
                        all_valuations.append(Valuation.from_dict(item))
        return all_valuations
    
    def _get_club_players(self, all_players: List[Player]) -> List[Player]:
        """Filter players belonging to the specified club.

        Uses exact name match first (case-insensitive).  Falls back to
        substring match only when no exact results are found — this avoids
        confusing e.g. "Real Madrid Castilla" players with "Real Madrid".
        """
        club_lower = self.club_name.lower()
        exact = [p for p in all_players if p.team and p.team.lower() == club_lower]
        if exact:
            return exact
        # Fallback: substring match (useful for CLI partial names)
        return [p for p in all_players if p.team and club_lower in p.team.lower()]
    
    def _calculate_team_market_values(self, all_players: List[Player]) -> Dict[str, float]:
        """Calculate total market value for each team."""
        team_values: Dict[str, float] = {}
        
        for player in all_players:
            if player.team:
                team_name = player.team
                team_values[team_name] = team_values.get(team_name, 0) + (player.market_value or 0)
        
        return team_values
    
    @staticmethod
    def _is_invalid_destination(team_name: str) -> bool:
        """Return True if the team should never be a sell destination."""
        return team_name.lower() in INVALID_DESTINATION_TEAM_NAMES

    def _find_destination_team(
        self,
        player: Player,
        excluded_teams: List[str],
        athletic_eligible_ids: Optional[set] = None,
    ) -> Optional[str]:
        """
        Find a random team that can afford the player.
        
        A team can afford a player if: team_market_value >= player_market_value * 10
        The signing makes more sense if: player_market_value * 200 >= team_market_value (to avoid Barcelona buying really cheap players for example)
        
        Teams like "Without Club", "Career break" and "Retired" are never
        valid destinations.
        
        Athletic Bilbao (and its sub-clubs) can only be a destination if the
        player has played for an Athletic family club at some point — mirroring
        their real-world buying policy.
        
        Args:
            player: The player being sold
            excluded_teams: Teams to exclude (e.g., current club)
            athletic_eligible_ids: Set of player IDs with Athletic family
                history.  When provided, Athletic teams are excluded as
                destinations for players NOT in this set.
        
        Returns:
            Team name or None if no team can afford the player
        """
        if player.market_value is None:
            return None
        
        min_team_value = min(player.market_value * 10, 1_000_000_000)
        max_team_value = max(player.market_value * 200, 200_000_000)
        excluded_lower = {t.lower() for t in excluded_teams if t}

        player_is_athletic_eligible = (
            athletic_eligible_ids is not None
            and player.player_id in athletic_eligible_ids
        )

        def _valid_destination(team_name: str) -> bool:
            if team_name.lower() in excluded_lower:
                return False
            if self._is_invalid_destination(team_name):
                return False
            # Athletic family clubs only accept players with Athletic history
            if (team_name.lower() in ATHLETIC_FAMILY_NAMES
                    and not player_is_athletic_eligible):
                return False
            return True

        eligible_teams = [
            team_name
            for team_name, team_value in self.team_market_values.items()
            if (min_team_value <= team_value <= max_team_value
                and _valid_destination(team_name))
        ]
        
        if eligible_teams:
            return random.choice(eligible_teams)
        else:
            # Fallback: if no team in range, pick from top 5 or bottom 5 by value
            sorted_teams = sorted(self.team_market_values.items(), key=lambda kv: kv[1])
            if not sorted_teams:
                return None
            if player.market_value * 10 > sorted_teams[-1][1]:
                # Player is too expensive for any team -> pick from top 5
                fallback = [
                    name for name, _ in sorted_teams[-5:]
                    if _valid_destination(name)
                ]
            else:
                # Player is too cheap for the range -> pick from bottom 5
                fallback = [
                    name for name, _ in sorted_teams[:5]
                    if _valid_destination(name)
                ]
            return random.choice(fallback) if fallback else None
    
    def _sell_random_players(
        self,
        club_players: List[Player],
        min_sales: int = 5,
        max_sales: int = 10,
        max_per_position: int = 3,
        athletic_eligible_ids: Optional[set] = None,
    ) -> Tuple[List[SoldPlayer], List[int]]:
        """
        Randomly sell players from the club.
        
        Players are only sold if a destination team can afford them
        (team_market_value >= player_market_value * 10).
        
        Returns:
            (sold_players, formation_needed) where formation_needed is [GK, DEF, MID, ATT]
        """
        available = []
        for p in club_players:
            pos = p.position
            # if pos in ["GK", "DEF", "MID", "ATT"] and not p.on_loan and p.position == "ATT":
            if pos in ["GK", "DEF", "MID", "ATT"] and not p.on_loan:
                available.append(p)
        
        # Decide how many to try to sell (1-10)
        num_to_sell = random.randint(min_sales, max_sales)
        # num_to_sell = len(club_players)
        # max_per_position = len(club_players)
        
        # Track sales per position (only count actually sold)
        sales_per_position = {"GK": 0, "DEF": 0, "MID": 0, "ATT": 0}
        sold_players: List[SoldPlayer] = []
        
        random.shuffle(available)
        
        attempts = 0
        for player in available:
            if attempts >= num_to_sell:
                break
            
            # Check max per position constraint
            if sales_per_position[player.position] < max_per_position:
                attempts += 1
                
                # Try to find a destination team
                destination = self._find_destination_team(
                    player,
                    excluded_teams=[self.club_name],
                    athletic_eligible_ids=athletic_eligible_ids,
                )
                
                sold_players.append(SoldPlayer(player=player, destination_team=destination))
                
                # Only count towards position if actually sold
                if destination is not None:
                    sales_per_position[player.position] += 1
        
        # Formation needed: [GK, DEF, MID, ATT] (only positions that were actually sold)
        formation_needed = [
            sales_per_position["GK"],
            sales_per_position["DEF"],
            sales_per_position["MID"],
            sales_per_position["ATT"],
        ]
        
        return sold_players, formation_needed

    def _sell_selected_players(
        self,
        club_players: List[Player],
        player_ids_to_sell: List[str],
        athletic_eligible_ids: Optional[set] = None,
    ) -> Tuple[List[SoldPlayer], List[int]]:
        """Sell specific players chosen by the user.

        Same destination-finding logic as ``_sell_random_players`` but only
        the players whose ``player_id`` is in *player_ids_to_sell* are put
        up for sale.

        Returns:
            (sold_players, formation_needed) where formation_needed is [GK, DEF, MID, ATT]
        """
        ids_to_sell = set(player_ids_to_sell)
        sales_per_position = {"GK": 0, "DEF": 0, "MID": 0, "ATT": 0}
        sold_players: List[SoldPlayer] = []

        for player in club_players:
            if player.player_id not in ids_to_sell:
                continue
            if player.position not in sales_per_position:
                continue
            destination = self._find_destination_team(
                player,
                excluded_teams=[self.club_name],
                athletic_eligible_ids=athletic_eligible_ids,
            )
            sold_players.append(SoldPlayer(player=player, destination_team=destination))
            if destination is not None:
                sales_per_position[player.position] += 1

        formation_needed = [
            sales_per_position["GK"],
            sales_per_position["DEF"],
            sales_per_position["MID"],
            sales_per_position["ATT"],
        ]
        return sold_players, formation_needed

    def _sell_players_by_value_decline(
        self,
        club_players: List[Player],
        athletic_eligible_ids: Optional[set] = None,
    ) -> Tuple[List[SoldPlayer], List[int]]:
        """
        Sell all players whose predicted_value < market_value (expected to decline).

        Uses _find_destination_team for each candidate (same logic as _sell_random_players).
        Requires club_players to have predicted_value set (call _predict_values first).

        Returns:
            (sold_players, formation_needed) where formation_needed is [GK, DEF, MID, ATT]
        """
        available = []
        for p in club_players:
            if p.position not in ["GK", "DEF", "MID", "ATT"] or p.on_loan:
                continue
            mv = p.market_value or 0
            pv = p.predicted_value
            if pv is not None and mv > 0 and pv < mv:
                available.append(p)
        # Sort by (market_value - predicted_value) desc: sell biggest expected declines first
        available.sort(key=lambda p: (p.market_value or 0) - (p.predicted_value or 0), reverse=True)

        sales_per_position = {"GK": 0, "DEF": 0, "MID": 0, "ATT": 0}
        sold_players: List[SoldPlayer] = []

        for player in available:
            destination = self._find_destination_team(
                player,
                excluded_teams=[self.club_name],
                athletic_eligible_ids=athletic_eligible_ids,
            )
            sold_players.append(SoldPlayer(player=player, destination_team=destination))
            if destination is not None:
                sales_per_position[player.position] += 1

        formation_needed = [
            sales_per_position["GK"],
            sales_per_position["DEF"],
            sales_per_position["MID"],
            sales_per_position["ATT"],
        ]
        return sold_players, formation_needed

    def _load_all_transfers(self, verbose: bool = False) -> List[Transfer]:
        """Load all transfers from every ``transfers_all_*.json`` file. Supports multi-part files."""
        all_transfers: List[Transfer] = []
        bases = list_json_bases("transfers_all_*.json")
        base_iter = tqdm(bases, desc="Loading transfers", disable=not verbose)

        for base in base_iter:
            if verbose:
                base_iter.set_postfix_str(base)
            data = load_json(base)
            if isinstance(data, list):
                for item in tqdm(data, desc=f"  {base}", disable=not verbose, leave=False):
                    if isinstance(item, dict):
                        all_transfers.append(Transfer.from_dict(item))
        return all_transfers

    def _load_athletic_eligible_ids(self, verbose: bool = False) -> set:
        """
        Stream transfer files and return player IDs that have played for Athletic Bilbao
        or any of its sub-clubs. Avoids loading all Transfer objects into memory.
        """
        eligible: set = set()
        bases = list_json_bases("transfers_all_*.json")
        base_iter = tqdm(bases, desc="Loading Athletic eligibility", disable=not verbose)

        for base in base_iter:
            if verbose:
                base_iter.set_postfix_str(base)
            data = load_json(base)
            if not isinstance(data, list):
                continue
            for item in tqdm(data, desc=f"  {base}", disable=not verbose, leave=False):
                if not isinstance(item, dict):
                    continue
                from_id = str(item.get("from_club_id", "") or "")
                from_name = (item.get("from_club_name") or item.get("from_club", "") or "").lower()
                to_id = str(item.get("to_club_id", "") or "")
                to_name = (item.get("to_club_name") or item.get("to_club", "") or "").lower()
                from_match = from_id in ATHLETIC_FAMILY_IDS or from_name in ATHLETIC_FAMILY_NAMES
                to_match = to_id in ATHLETIC_FAMILY_IDS or to_name in ATHLETIC_FAMILY_NAMES
                if from_match or to_match:
                    pid = item.get("player_id", "")
                    if pid:
                        eligible.add(str(pid))
        return eligible

    def _is_athletic_club(self) -> bool:
        """Return True if the current club is Athletic Bilbao or a related club."""
        club_lower = self.club_name.lower()
        return club_lower in ATHLETIC_FAMILY_NAMES

    def _get_athletic_eligible_ids(
        self, all_transfers: List[Transfer], verbose: bool = False
    ) -> set:
        """
        Return player IDs that have played for Athletic Bilbao or any of its
        sub-clubs at any point in their career.

        A player is eligible if they appear in ANY transfer where either the
        ``from_club`` or ``to_club`` is an Athletic family club (checked by
        team_id **or** team_name).

        Prefer ``_load_athletic_eligible_ids()`` when you don't have transfers
        loaded yet – it streams files and avoids loading all Transfer objects.
        """
        eligible: set = set()
        transfer_iter = tqdm(all_transfers, desc="Athletic eligibility", disable=not verbose)
        for t in transfer_iter:
            from_match = (
                t.from_club_id in ATHLETIC_FAMILY_IDS
                or t.from_club_name.lower() in ATHLETIC_FAMILY_NAMES
            )
            to_match = (
                t.to_club_id in ATHLETIC_FAMILY_IDS
                or t.to_club_name.lower() in ATHLETIC_FAMILY_NAMES
            )
            if from_match or to_match:
                eligible.add(t.player_id)
        return eligible

    @staticmethod
    def _is_invalid_origin(team_name: str) -> bool:
        """Return True if players from this team should not be available for signing."""
        return team_name.lower() in INVALID_ORIGIN_TEAM_NAMES

    def _get_available_players(
        self,
        all_players: List[Player],
        club_players: List[Player],
        is_athletic: bool = False,
        athletic_eligible_ids: Optional[set] = None,
    ) -> List[Player]:
        """
        Get players available for signing (not in club).

        Excludes players from invalid origin teams (e.g. "Retired").
        If *is_athletic* is True (the buying club is Athletic Bilbao),
        only players present in *athletic_eligible_ids* are eligible.
        """
        club_ids = {p.player_id for p in club_players}
        available = [
            p for p in all_players
            if p.player_id not in club_ids
            and not self._is_invalid_origin(p.team or "")
        ]

        # Athletic Bilbao can only buy players with Athletic history
        if is_athletic and athletic_eligible_ids is not None:
            available = [p for p in available if p.player_id in athletic_eligible_ids]

        return available

    def _filter_players_by_value_and_league(
        self,
        players: List[Player],
        club_players: List[Player],
        team_league_mapping: Dict[str, Dict[str, Dict[str, str]]],
    ) -> List[Player]:
        f"""
        Filter out players with market value < €{MIN_FILTER_MARKET_VALUE/1_000_000:.1f}M unless they play in:
        - A top 5 league (GB1, IT1, L1, FR1, ES1), or
        - The same league as the club we're simulating for.
        """
        if not club_players:
            return players

        club_team_id = (club_players[0].team_id or "").strip()
        club_league_id = ""
        if club_team_id and self.season:
            club_league_id = (
                team_league_mapping.get(club_team_id, {}).get(self.season, {}).get("league_id", "") or ""
            )

        result = []
        for p in players:
            mv = p.market_value or 0
            if mv >= MIN_FILTER_MARKET_VALUE:
                result.append(p)
                continue
            # Below MIN_FILTER_MARKET_VALUE: keep only if in top 5 league or club's league
            player_league_id = ""
            if (p.team_id or "").strip():
                player_league_id = (
                    team_league_mapping.get(p.team_id, {}).get(self.season, {}).get("league_id", "") or ""
                )
            if player_league_id in TOP_LEAGUE_IDS:
                result.append(p)
            elif club_league_id and player_league_id == club_league_id:
                result.append(p)
        return result

    def run(
        self,
        min_sales: int = 5,
        max_sales: int = 10,
        max_per_position: int = 3,
        verbose: bool = True,
        generate_summary: bool = True,
        filter_players: bool = True,
        sell_by_value_decline: bool = False,
        llm_provider: Optional[str] = None,
        llm_api_key: Optional[str] = None,
        progress_callback: Optional[object] = None,
        unlimited_budget: bool = False,
        players_to_sell: Optional[List[str]] = None,
        buy_counts: Optional[Dict[str, int]] = None,
    ) -> TransferResult:
        f"""
        Run the transfer simulation.

        Args:
            min_sales: Minimum players to sell (random mode only)
            max_sales: Maximum players to sell (random mode only)
            max_per_position: Max players to sell per position (random mode only)
            verbose: Print progress to stdout
            generate_summary: If True, attempt to generate LLM summary
            filter_players: If True, exclude players <€{MIN_FILTER_MARKET_VALUE/1_000_000:.1f}M value unless in top 5
                leagues or the club's league (default: True)
            sell_by_value_decline: If True, sell players with predicted_value < market_value
                instead of random selection (default: False)
            llm_provider: LLM provider ("openai", "anthropic", "gemini")
            llm_api_key: Optional API key override
            progress_callback: Optional ``callable(pct: float, step_key: str)``
                invoked at each major step.  *step_key* matches the i18n keys
                used by the Streamlit UI (e.g. ``"step_loading"``).
            unlimited_budget: If True, ignore budget constraints in the
                knapsack optimiser.
            players_to_sell: Optional list of player IDs to sell manually.
                When provided, ``sell_by_value_decline`` and random selling
                are skipped.
            buy_counts: Optional per-position count of players to buy.
                E.g. ``{{"GK": 0, "DEF": 2, "MID": 1, "ATT": 1}}``.
                Overrides the formation derived from sales.

        Returns:
            TransferResult with simulation details
        """

        def _progress(pct: float, key: str) -> None:
            if progress_callback is not None:
                progress_callback(pct, key)

        preloaded = getattr(self, "_preloaded", False)

        if preloaded:
            all_players = self.all_players
            club_players = self.club_players
            athletic_eligible_ids = getattr(self, "_athletic_eligible_ids", None)
            is_athletic = getattr(self, "_is_athletic", False)
            if verbose:
                print(f"Using preloaded data: {len(all_players)} players, "
                      f"{len(club_players)} in squad")
            _progress(0.40, "step_team_values")
        else:
            # ── Step 1/8: Load data ──────────────────────────────────────
            _progress(0.05, "step_loading")
            if verbose:
                print(f"Loading data for {self.season}...")

            all_players = self._load_active_players(verbose=verbose)
            self.all_players = all_players

            if verbose:
                print(f"  Loaded {len(all_players)} active players")

            # ── Step 2/8: Identify club squad ────────────────────────────
            _progress(0.20, "step_team")
            club_players = self._get_club_players(all_players)

            if not club_players:
                raise ValueError(f"No players found for club: {self.club_name}")

            if verbose:
                print(f"  {self.club_name} has {len(club_players)} players")

            # ── Step 3/8: Calculate team market values ───────────────────
            _progress(0.35, "step_team_values")
            self.team_market_values = self._calculate_team_market_values(all_players)

            if verbose:
                print(f"  Calculated market values for {len(self.team_market_values)} teams")

            athletic_eligible_ids: Optional[set] = None
            is_athletic = self._is_athletic_club()
            athletic_in_market = any(
                name.lower() in ATHLETIC_FAMILY_NAMES
                for name in self.team_market_values
            )
            if is_athletic or athletic_in_market:
                if verbose and is_athletic:
                    print("  Athletic Bilbao detected – loading transfer history for eligibility filter...")
                elif verbose:
                    print("  Athletic family club(s) in market – loading transfer history for sell filter...")
                athletic_eligible_ids = self._load_athletic_eligible_ids(verbose=verbose)
                if verbose:
                    print(f"  {len(athletic_eligible_ids)} players with Athletic family history found")

        # ── Step 4/8: Sell players ───────────────────────────────────────
        _progress(0.50, "step_selling")
        pred_cache: Optional[dict] = None
        if players_to_sell is not None:
            sold_players, formation_needed = self._sell_selected_players(
                club_players,
                players_to_sell,
                athletic_eligible_ids=athletic_eligible_ids,
            )
        elif sell_by_value_decline:
            if verbose:
                print("  Predicting values for squad (sell-by-decline mode)...")
            pred_cache = {}
            club_players = self._predict_values(club_players, verbose=verbose, _cache=pred_cache)
            sold_players, formation_needed = self._sell_players_by_value_decline(
                club_players,
                athletic_eligible_ids=athletic_eligible_ids,
            )
        else:
            sold_players, formation_needed = self._sell_random_players(
                club_players,
                min_sales=min_sales,
                max_sales=max_sales,
                max_per_position=max_per_position,
                athletic_eligible_ids=athletic_eligible_ids,
            )

        actually_sold = [sp for sp in sold_players if sp.was_sold]
        sales_revenue = sum((sp.player.market_value or 0) for sp in actually_sold) / 1_000_000
        total_budget = self.budget + int(sales_revenue)

        if verbose:
            print(f"  Attempted to sell {len(sold_players)} players:")
            print(f"    - {len(actually_sold)} sold for €{sales_revenue:.1f}M")
            print(f"    - {len(sold_players) - len(actually_sold)} no buyer found")
            print(f"  Total budget: €{total_budget}M")
            print(f"  Formation needed: {formation_needed}")

        # ── Step 5/8: Predict future values ──────────────────────────────
        _progress(0.65, "step_predicting")
        if verbose:
            print(f"  Predicting future values...")

        sold_player_ids = {sp.player.player_id for sp in sold_players}
        available_players = self._get_available_players(
            all_players, club_players,
            is_athletic=is_athletic,
            athletic_eligible_ids=athletic_eligible_ids,
        )
        available_players = [p for p in available_players if p.player_id not in sold_player_ids]

        # Filter out players <1M unless in top 5 leagues or club's league
        if filter_players:
            if verbose:
                print("  Filtering players by value and league...")
            team_league_mapping = (
                pred_cache["team_league_mapping"]
                if (pred_cache and "team_league_mapping" in pred_cache)
                else load_team_league_mapping(verbose=verbose)
            )
            before = len(available_players)
            available_players = self._filter_players_by_value_and_league(
                available_players, club_players, team_league_mapping
            )
            if verbose:
                print(f"  Filtered {before} -> {len(available_players)} players (excluded <€{MIN_FILTER_MARKET_VALUE/1_000_000:.1f}M outside top leagues)")

        if verbose:
            print(f"  {len(available_players)} players available for signing")

        available_players = self._predict_values(
            available_players, verbose=verbose, _cache=pred_cache if sell_by_value_decline else None
        )

        # ── Step 6/8: Knapsack optimisation ──────────────────────────────
        _progress(0.80, "step_knapsack")
        if verbose:
            print(f"  Finding optimal signings...")

        if buy_counts:
            custom_formation = [[
                buy_counts.get("GK", 0),
                buy_counts.get("DEF", 0),
                buy_counts.get("MID", 0),
                buy_counts.get("ATT", 0),
            ]]
        else:
            gk_needed, def_needed, mid_needed, att_needed = formation_needed
            custom_formation = [[gk_needed, def_needed, mid_needed, att_needed]]

        results = best_full_teams(
            available_players,
            formations=custom_formation,
            budget=total_budget * 1_000_000,
            use_predicted_value=True,
            verbose=1 if verbose else 0,
            unlimited_budget=unlimited_budget,
        )

        recommended_signings = []
        recommended_formation = []
        total_signing_cost = 0
        total_predicted_value = 0.0

        if results:
            recommended_formation, score, recommended_signings = results[0]
            total_signing_cost = sum((p.market_value or 0) for p in recommended_signings) / 1_000_000
            total_predicted_value = score

        result = TransferResult(
            club_name=self.club_name,
            season=self.season,
            initial_budget=self.budget,
            sales_revenue=int(sales_revenue),
            total_budget=total_budget,
            players_sold=sold_players,
            formation_needed=formation_needed,
            recommended_signings=recommended_signings,
            recommended_formation=recommended_formation,
            total_signing_cost=int(total_signing_cost),
            total_predicted_value=total_predicted_value,
            current_squad=club_players,
        )

        # ── Step 7/8: LLM summary (optional) ────────────────────────────
        if generate_summary:
            _progress(0.90, "step_summary")
            if verbose:
                print(f"  Generating AI summary...")
            result.generate_llm_summary(
                provider=llm_provider,
                api_key=llm_api_key,
            )

        _progress(1.0, "step_done")
        return result


def main():
    """CLI entry point for testing."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Transfer window simulator")
    parser.add_argument("--club", type=str, required=True, help="Club name")
    parser.add_argument("--season", type=str, default="2023-2024", help="Season")
    parser.add_argument("--transfer-budget", type=int, default=100, help="Transfer budget (millions)")
    parser.add_argument("--salary-budget", type=int, default=15, help="Salary budget (millions/year)")
    parser.add_argument("--no-summary", action="store_true", help="Skip LLM summary generation")
    parser.add_argument("--filter-players", action="store_true", default=True,
                        help=f"Exclude players <€{MIN_FILTER_MARKET_VALUE/1_000_000:.1f}M unless in top 5 leagues or club's league (default: True)")
    parser.add_argument("--no-filter-players", dest="filter_players", action="store_false",
                        help="Disable value/league filter")
    parser.add_argument("--sell-by-value-decline", action="store_true",
                        help="Sell players with predicted value < market value (instead of random)")
    parser.add_argument("--verbose", action="store_true", default=True, help="Print progress (default: True)")
    parser.add_argument("--no-verbose", dest="verbose", action="store_false", help="Quiet mode")
    parser.add_argument("--llm-provider", type=str, default=None, 
                        help="LLM provider (openai, anthropic, gemini)")
    parser.add_argument("--llm-api-key", type=str, default=None,
                        help="LLM API key (or use env vars)")
    
    args = parser.parse_args()
    
    sim = TransferSimulator(
        club_name=args.club,
        season=args.season,
        transfer_budget=args.transfer_budget,
        salary_budget=args.salary_budget,
    )
    
    result = sim.run(
        generate_summary=not args.no_summary,
        filter_players=args.filter_players,
        sell_by_value_decline=args.sell_by_value_decline,
        verbose=args.verbose,
        llm_provider=args.llm_provider,
        llm_api_key=args.llm_api_key,
    )
    print(result)


if __name__ == "__main__":
    main()
