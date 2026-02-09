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
from valuation import Valuation
from simulator.knapsack_solver import best_full_teams

# Paths
ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data" / "json"
MODELS_DIR = ROOT_DIR / "ml" / "models"


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
        
        lines.append(f"\nFormation needed: {self.formation_needed}")
        lines.append(f"  (GK: {self.formation_needed[0]}, DEF: {self.formation_needed[1]}, "
                    f"MID: {self.formation_needed[2]}, ATT: {self.formation_needed[3]})")
        
        lines.append(f"\nRecommended Signings ({len(self.recommended_signings)}):")
        lines.append(f"  Formation: {self.recommended_formation}")
        
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
        lines.append(f"{'='*60}")
        
        return "\n".join(lines)


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
    
    def _load_players_for_season(self) -> Dict[str, Player]:
        """Load players from players_all_{season}.json."""
        filepath = DATA_DIR / f"players_all_{self.season}.json"
        
        if not filepath.exists():
            raise FileNotFoundError(f"Players file not found: {filepath}")
        
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        players = {}
        for item in data:
            p = Player.from_dict(item)
            players[p.player_id] = p
        
        return players
    
    def _load_valuations_for_season(self) -> Dict[str, Valuation]:
        """
        Load valuations for the season's cutoff date (01/07/start_year).
        Returns the most recent valuation for each player before cutoff.
        """
        start_year = int(self.season.split("-")[0])
        cutoff_date = datetime(start_year, 7, 1)
        
        # Load all valuations
        filepath = DATA_DIR / f"valuations_all_{self.season}.json"
        if not filepath.exists():
            return {}
        
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Find most recent valuation per player before cutoff
        latest_valuations: Dict[str, Tuple[datetime, Valuation]] = {}
        
        for item in data:
            v = Valuation.from_dict(item)
            
            # Parse date
            try:
                val_date = datetime.strptime(v.valuation_date, "%d/%m/%Y")
            except ValueError:
                try:
                    val_date = datetime.strptime(v.valuation_date, "%Y-%m-%d")
                except ValueError:
                    continue
            
            # Only valuations before or at cutoff
            if val_date <= cutoff_date:
                if v.player_id not in latest_valuations or val_date > latest_valuations[v.player_id][0]:
                    latest_valuations[v.player_id] = (val_date, v)
        
        return {pid: v for pid, (_, v) in latest_valuations.items()}
    
    def _update_players_with_valuations(
        self,
        players: Dict[str, Player],
        valuations: Dict[str, Valuation],
    ) -> List[Player]:
        """
        Update player data with valuation data (inner join).
        Only keeps players that have valuations.
        """
        result = []
        
        for player_id, valuation in valuations.items():
            if player_id in players:
                player = players[player_id]
                # Update with valuation data
                player.market_value = valuation.valuation_amount
                player.team = valuation.club_name_at_valuation or player.team
                player.team_id = valuation.club_id_at_valuation or player.team_id
                if valuation.age_at_valuation:
                    player.age = valuation.age_at_valuation
                result.append(player)
        
        return result
    
    def _load_predictor(self):
        """Load the ML model for this season."""
        from ml.value_predictor import ValuePredictor
        
        model_path = MODELS_DIR / f"value_model_{self.season}.joblib"
        
        if not model_path.exists():
            raise FileNotFoundError(
                f"Model not found: {model_path}\n"
                f"Run: python -m ml.train_pipeline --season {self.season}"
            )
        
        self.predictor = ValuePredictor(model_path=model_path)
    
    def _predict_values(self, players: List[Player], verbose: bool = True) -> List[Player]:
        """Add predicted_value to each player using the ML model."""
        from ml.feature_engineering import build_prediction_dataset, load_team_league_mapping
        
        if not self.predictor:
            self._load_predictor()
        
        # Build features for prediction
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
    
    def _find_destination_team(
        self,
        player: Player,
        excluded_teams: List[str],
    ) -> Optional[str]:
        """
        Find a random team that can afford the player.
        
        A team can afford a player if: team_market_value >= player_market_value * 10
        The signing makes more sense if: player_market_value * 200 >= team_market_value (to avoid Barcelona buying really cheap players for example)
        
        Args:
            player: The player being sold
            excluded_teams: Teams to exclude (e.g., current club)
        
        Returns:
            Team name or None if no team can afford the player
        """
        if not player.market_value:
            return None
        
        min_team_value = player.market_value * 10
        max_team_value = max(player.market_value * 200, 200_000_000)
        excluded_lower = {t.lower() for t in excluded_teams if t}
        
        eligible_teams = [
            team_name
            for team_name, team_value in self.team_market_values.items()
            if min_team_value <= team_value <= max_team_value and team_name.lower() not in excluded_lower
        ]
        
        if eligible_teams:
            return random.choice(eligible_teams)
        
        return None
    
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
        
        # Create pool of sellable players
        available = []
        for pos, players in by_position.items():
            available.extend([(p, pos) for p in players])
        
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
    
    def _get_available_players(
        self,
        all_players: List[Player],
        club_players: List[Player],
    ) -> List[Player]:
        """Get players available for signing (not in club)."""
        club_ids = {p.player_id for p in club_players}
        return [p for p in all_players if p.player_id not in club_ids]
    
    def run(
        self,
        min_sales: int = 5,
        max_sales: int = 10,
        max_per_position: int = 3,
        verbose: bool = True,
    ) -> TransferResult:
        """
        Run the transfer simulation.
        
        Args:
            min_sales: Minimum players to sell
            max_sales: Maximum players to sell
            max_per_position: Max players to sell per position
            verbose: Print progress
        
        Returns:
            TransferResult with simulation details
        """
        if verbose:
            print(f"Loading data for {self.season}...")
        
        # Load and merge player data with valuations
        players_dict = self._load_players_for_season()
        valuations = self._load_valuations_for_season()
        all_players = self._update_players_with_valuations(players_dict, valuations)
        
        if verbose:
            print(f"  Loaded {len(all_players)} players with valuations")
        
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
        
        # Get available players (not in club, and not the ones we're trying to sell)
        sold_player_ids = {sp.player.player_id for sp in sold_players}
        available_players = self._get_available_players(all_players, club_players)
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
        
        return TransferResult(
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
        )


def main():
    """CLI entry point for testing."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Transfer window simulator")
    parser.add_argument("--club", type=str, required=True, help="Club name")
    parser.add_argument("--season", type=str, default="2023-2024", help="Season")
    parser.add_argument("--transfer-budget", type=int, default=100, help="Transfer budget (millions)")
    parser.add_argument("--salary-budget", type=int, default=15, help="Salary budget (millions/year)")
    
    args = parser.parse_args()
    
    sim = TransferSimulator(
        club_name=args.club,
        season=args.season,
        transfer_budget=args.transfer_budget,
        salary_budget=args.salary_budget,
    )
    
    result = sim.run()
    print(result)


if __name__ == "__main__":
    main()
