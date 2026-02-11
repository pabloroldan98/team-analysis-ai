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
    
    def _load_active_players(self) -> List[Player]:
        """
        Load active players at season start using the data_loader pipeline.

        Delegates to ``get_active_players_at_season_start`` which:
          1. Loads ALL players (all seasons)
          2. Assigns teams from transfers (last transfer <= 01/07)
          3. Filters out Retired / Without Club / Career break
          4. Updates market_value & age from valuations
        """
        from simulator.data_loader import get_active_players_at_season_start
        return get_active_players_at_season_start(self.season)
    
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
    
    def _predict_values(self, players: List[Player], verbose: bool = False) -> List[Player]:
        """Add predicted_value to each player using the ML model."""
        from ml.feature_engineering import build_prediction_dataset, load_team_league_mapping
        
        if not self.predictor:
            self._load_predictor()
        
        # Build features for prediction
        if self.season.lower() == "today":
            cutoff_date = datetime.now()
        else:
            start_year = int(self.season.split("-")[0])
            cutoff_date = datetime(start_year, 7, 1)
        
        # Load valuations for feature extraction
        if verbose:
            print("    Loading valuations...")
        all_valuations = self._load_all_valuations()
        team_league_mapping = load_team_league_mapping()
        
        # Create player dict for feature extraction
        player_dict = {p.player_id: p for p in players}
        
        # Build prediction dataset
        if verbose:
            print("    Building features...")
        features = build_prediction_dataset(
            all_valuations,
            cutoff_date,
            players=player_dict,
            team_league_mapping=team_league_mapping,
        )
        
        # Get predictions
        if features:
            if verbose:
                print(f"    Predicting values for {len(features)} players...")
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
    
    def _load_all_valuations(self) -> List[Valuation]:
        """Load all valuations for feature extraction."""
        all_valuations = []
        
        for filepath in DATA_DIR.glob("valuations_all_*.json"):
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                all_valuations.append(Valuation.from_dict(item))
        
        return all_valuations
    
    def _get_club_players(self, all_players: List[Player]) -> List[Player]:
        """Filter players belonging to the specified club."""
        club_lower = self.club_name.lower()
        return [
            p for p in all_players
            if p.team and club_lower in p.team.lower()
        ]
    
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
    ) -> Optional[str]:
        """
        Find a random team that can afford the player.
        
        A team can afford a player if: team_market_value >= player_market_value * 10
        The signing makes more sense if: player_market_value * 200 >= team_market_value (to avoid Barcelona buying really cheap players for example)
        
        Teams like "Without Club", "Career break" and "Retired" are never
        valid destinations.
        
        Args:
            player: The player being sold
            excluded_teams: Teams to exclude (e.g., current club)
        
        Returns:
            Team name or None if no team can afford the player
        """
        if not player.market_value:
            return None
        
        min_team_value = min(player.market_value * 10, 1_000_000_000)
        max_team_value = max(player.market_value * 200, 200_000_000)
        excluded_lower = {t.lower() for t in excluded_teams if t}
        
        eligible_teams = [
            team_name
            for team_name, team_value in self.team_market_values.items()
            if (min_team_value <= team_value <= max_team_value
                and team_name.lower() not in excluded_lower
                and not self._is_invalid_destination(team_name))
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
                    if name.lower() not in excluded_lower
                    and not self._is_invalid_destination(name)
                ]
            else:
                # Player is too cheap for the range -> pick from bottom 5
                fallback = [
                    name for name, _ in sorted_teams[:5]
                    if name.lower() not in excluded_lower
                    and not self._is_invalid_destination(name)
                ]
            return random.choice(fallback) if fallback else None
    
    def _sell_random_players(
        self,
        club_players: List[Player],
        min_sales: int = 5,
        max_sales: int = 10,
        max_per_position: int = 3,
    ) -> Tuple[List[SoldPlayer], List[int]]:
        """
        Randomly sell players from the club.
        
        Players are only sold if a destination team can afford them
        (team_market_value >= player_market_value * 10).
        
        Returns:
            (sold_players, formation_needed) where formation_needed is [GK, DEF, MID, ATT]
        """
        # Group players by position
        by_position: Dict[str, List[Player]] = {
            "GK": [], "DEF": [], "MID": [], "ATT": []
        }
        
        for p in club_players:
            pos = p.position
            if pos in by_position:
                by_position[pos].append(p)
        
        # Decide how many to try to sell (1-10)
        num_to_sell = random.randint(min_sales, max_sales)
        
        # Track sales per position (only count actually sold)
        sales_per_position = {"GK": 0, "DEF": 0, "MID": 0, "ATT": 0}
        sold_players: List[SoldPlayer] = []
        
        # Create pool of sellable players (on-loan players cannot be sold)
        available = []
        for pos, players in by_position.items():
            available.extend([(p, pos) for p in players if not p.on_loan])
        
        random.shuffle(available)
        
        attempts = 0
        for player, pos in available:
            if attempts >= num_to_sell:
                break
            
            # Check max per position constraint
            if sales_per_position[pos] < max_per_position:
                attempts += 1
                
                # Try to find a destination team
                destination = self._find_destination_team(
                    player,
                    excluded_teams=[self.club_name],
                )
                
                sold_players.append(SoldPlayer(player=player, destination_team=destination))
                
                # Only count towards position if actually sold
                if destination is not None:
                    sales_per_position[pos] += 1
        
        # Formation needed: [GK, DEF, MID, ATT] (only positions that were actually sold)
        formation_needed = [
            sales_per_position["GK"],
            sales_per_position["DEF"],
            sales_per_position["MID"],
            sales_per_position["ATT"],
        ]
        
        return sold_players, formation_needed
    
    def _load_all_transfers(self) -> List[Transfer]:
        """Load all transfers from every ``transfers_all_*.json`` file."""
        all_transfers: List[Transfer] = []
        for filepath in DATA_DIR.glob("transfers_all_*.json"):
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                all_transfers.append(Transfer.from_dict(item))
        return all_transfers

    def _is_athletic_club(self) -> bool:
        """Return True if the current club is Athletic Bilbao or a related club."""
        club_lower = self.club_name.lower()
        return club_lower in ATHLETIC_FAMILY_NAMES

    def _get_athletic_eligible_ids(self, all_transfers: List[Transfer]) -> set:
        """
        Return player IDs that have played for Athletic Bilbao or any of its
        sub-clubs at any point in their career.

        A player is eligible if they appear in ANY transfer where either the
        ``from_club`` or ``to_club`` is an Athletic family club (checked by
        team_id **or** team_name).
        """
        eligible: set = set()
        for t in all_transfers:
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
        athletic_eligible_ids: Optional[set] = None,
    ) -> List[Player]:
        """
        Get players available for signing (not in club).

        Excludes players from invalid origin teams (e.g. "Retired").
        If ``athletic_eligible_ids`` is provided (when the buying club is
        Athletic Bilbao), only players in that set are eligible.
        """
        club_ids = {p.player_id for p in club_players}
        available = [
            p for p in all_players
            if p.player_id not in club_ids
            and not self._is_invalid_origin(p.team or "")
        ]

        # Athletic Bilbao can only buy players with Athletic history
        if athletic_eligible_ids is not None:
            available = [p for p in available if p.player_id in athletic_eligible_ids]

        return available
    
    def run(
        self,
        min_sales: int = 5,
        max_sales: int = 10,
        max_per_position: int = 3,
        verbose: bool = True,
        generate_summary: bool = True,
        llm_provider: Optional[str] = None,
        llm_api_key: Optional[str] = None,
    ) -> TransferResult:
        """
        Run the transfer simulation.
        
        Args:
            min_sales: Minimum players to sell
            max_sales: Maximum players to sell
            max_per_position: Max players to sell per position
            verbose: Print progress
            generate_summary: If True, attempt to generate LLM summary (skipped if no API key)
            llm_provider: LLM provider ("openai", "anthropic", "gemini")
            llm_api_key: Optional API key override
        
        Returns:
            TransferResult with simulation details
        """
        if verbose:
            print(f"Loading data for {self.season}...")
        
        # Load active players (transfer-based team assignment + valuation update)
        all_players = self._load_active_players()
        self.all_players = all_players
        
        if verbose:
            print(f"  Loaded {len(all_players)} active players")
        
        # Get club's players
        club_players = self._get_club_players(all_players)
        
        if not club_players:
            raise ValueError(f"No players found for club: {self.club_name}")
        
        if verbose:
            print(f"  {self.club_name} has {len(club_players)} players")
        
        # Calculate team market values for finding destination teams
        self.team_market_values = self._calculate_team_market_values(all_players)
        
        if verbose:
            print(f"  Calculated market values for {len(self.team_market_values)} teams")
        
        # Sell random players
        sold_players, formation_needed = self._sell_random_players(
            club_players,
            min_sales=min_sales,
            max_sales=max_sales,
            max_per_position=max_per_position,
        )
        
        # Only count revenue from players that were actually sold
        actually_sold = [sp for sp in sold_players if sp.was_sold]
        sales_revenue = sum((sp.player.market_value or 0) for sp in actually_sold) / 1_000_000
        total_budget = self.budget + int(sales_revenue)
        
        if verbose:
            print(f"  Attempted to sell {len(sold_players)} players:")
            print(f"    - {len(actually_sold)} sold for €{sales_revenue:.1f}M")
            print(f"    - {len(sold_players) - len(actually_sold)} no buyer found")
            print(f"  Total budget: €{total_budget}M")
            print(f"  Formation needed: {formation_needed}")
        
        # Athletic Bilbao special case: can only buy players with Athletic
        # family history.  Pre-compute the eligible set if needed.
        athletic_eligible_ids: Optional[set] = None
        if self._is_athletic_club():
            if verbose:
                print("  Athletic Bilbao detected – loading transfer history to filter eligible signings...")
            all_transfers = self._load_all_transfers()
            athletic_eligible_ids = self._get_athletic_eligible_ids(all_transfers)
            if verbose:
                print(f"  {len(athletic_eligible_ids)} players with Athletic family history found")

        # Get available players (not in club, and not the ones we're trying to sell)
        sold_player_ids = {sp.player.player_id for sp in sold_players}
        available_players = self._get_available_players(
            all_players, club_players,
            athletic_eligible_ids=athletic_eligible_ids,
        )
        # Also exclude sold players (they shouldn't be bought back)
        available_players = [p for p in available_players if p.player_id not in sold_player_ids]
        
        if verbose:
            print(f"  {len(available_players)} players available for signing")
        
        # Predict values for available players
        if verbose:
            print(f"  Predicting future values...")
        
        # available_players = self._predict_values(available_players, verbose=verbose)
        available_players = self._predict_values(available_players)
        
        # Find best signings using knapsack
        if verbose:
            print(f"  Finding optimal signings...")
        
        # Convert formation_needed [GK, DEF, MID, ATT] to formations for knapsack
        # The knapsack expects [DEF, MID, ATT] (GK is always 1)
        gk_needed = formation_needed[0]
        def_needed = formation_needed[1]
        mid_needed = formation_needed[2]
        att_needed = formation_needed[3]
        
        # Create custom formation based on needs
        custom_formation = [[def_needed, mid_needed, att_needed]]
        
        # If we need GK, we need to handle it separately or include in formation
        # For simplicity, if GK needed, add to the formation search
        if gk_needed > 0:
            custom_formation = [[gk_needed, def_needed, mid_needed, att_needed]]
        
        # Run knapsack optimization
        results = best_full_teams(
            available_players,
            formations=custom_formation,
            budget=total_budget * 1_000_000,  # Convert to euros
            use_predicted_value=True,
            verbose=1 if verbose else 0,
        )
        
        # Get best result
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
        
        # Generate LLM summary if requested
        if generate_summary:
            if verbose:
                print(f"  Generating AI summary...")
            result.generate_llm_summary(
                provider=llm_provider,
                api_key=llm_api_key,
            )
        
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
        llm_provider=args.llm_provider,
        llm_api_key=args.llm_api_key,
    )
    print(result)


if __name__ == "__main__":
    main()
