"""Buy/sell logic for transfer simulation."""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional

from player import Player

from simulator.data_loader import (
    get_active_players_at_season_start,
    get_active_team_players_at_season_start,
)
from simulator.knapsack_solver import (
    best_full_teams,
    FORMATIONS,
)


@dataclass
class SimulationResult:
    """Result of a transfer simulation run."""
    club_name: str
    season: str
    initial_squad: List[Player]
    final_squad: List[Player]
    players_sold: List[Player]
    players_bought: List[Player]
    best_eleven: List[Player]
    formation: List[int]
    initial_valuation: float
    final_valuation: float
    transfer_budget_used: float
    net_benefit: float
    ai_summary: str = ""


def _compute_valuation(players: List[Player]) -> float:
    """Sum market value of all players."""
    return sum(p.market_value or 0 for p in players)


def _sell_phase(
    squad: List[Player],
    min_sells: int = 5,
    max_sells: int = 10,
    max_per_position: int = 3,
) -> tuple[List[Player], List[Player], float]:
    """Select players to sell. Returns (remaining_squad, sold_players, sale_proceeds)."""
    if not squad:
        return [], [], 0.0

    by_position: dict[str, List[Player]] = {}
    for p in squad:
        pos = p.position or "N/A"
        by_position.setdefault(pos, []).append(p)

    sold = []
    sold_count_by_pos: dict[str, int] = {}
    n_to_sell = random.randint(min_sells, min(max_sells, len(squad)))
    candidates = squad.copy()
    random.shuffle(candidates)

    for p in candidates:
        if len(sold) >= n_to_sell:
            break
        pos = p.position or "N/A"
        count = sold_count_by_pos.get(pos, 0)
        if count >= max_per_position:
            continue
        sold.append(p)
        sold_count_by_pos[pos] = count + 1

    remaining = [p for p in squad if p not in sold]
    proceeds = sum(p.market_value or 0 for p in sold)
    return remaining, sold, proceeds


def _build_purchase_pool(
    remaining_squad: List[Player],
    league_players: List[Player],
    team_id: str,
) -> List[Player]:
    """Build pool: remaining squad (price=0) + other teams' players (price=market_value)."""
    our_ids = {p.player_id for p in remaining_squad}
    pool = []
    for p in remaining_squad:
        p._knapsack_price = 0
        pool.append(p)
    for p in league_players:
        if p.player_id in our_ids:
            continue
        if str(p.team_id) != str(team_id):
            pool.append(p)
    return pool


def run_simulation(
    club_name: str,
    season: str,
    transfer_budget: float,
    salary_budget: float,
    initial_squad: Optional[List[Player]] = None,
    league_players: Optional[List[Player]] = None,
) -> Optional[SimulationResult]:
    """
    Run transfer simulation: sell phase then buy phase using knapsack.
    
    Args:
        club_name: Club name
        season: Season string (e.g. "2020-2021")
        transfer_budget: Transfer budget in euros
        salary_budget: Salary budget in euros
        initial_squad: Optional pre-loaded squad. If None, loaded from data.
        league_players: Optional pre-loaded league players. If None, loaded from data.
    
    Returns:
        SimulationResult or None if data insufficient.
    """
    if initial_squad is None or league_players is None:
        # Use active players at season start (01/07) with updated market values
        squad = get_active_team_players_at_season_start(season, club_name)
        all_players = get_active_players_at_season_start(season, "all")
        if not squad:
            return None
        if not all_players:
            all_players = squad
    else:
        squad = list(initial_squad)
        all_players = list(league_players) if league_players else squad

    initial_valuation = _compute_valuation(squad)
    budget_euros = min(
        transfer_budget * 1_000_000,
        salary_budget * 1_000_000 * 10,
    )
    budget_euros = max(0, budget_euros)

    remaining, sold, sale_proceeds = _sell_phase(squad)
    budget_euros += sale_proceeds

    team_id = str(remaining[0].team_id) if remaining else ""
    if not team_id and squad:
        team_id = str(squad[0].team_id)

    pool = _build_purchase_pool(remaining, all_players, team_id)

    results = best_full_teams(pool, formations=FORMATIONS, budget=int(budget_euros))
    bought = []
    if not results:
        final_squad = remaining
        best_eleven = remaining[:11] if len(remaining) >= 11 else remaining
        formation = [4, 4, 2]
    else:
        formation, _, best_eleven = results[0]
        remaining_ids = {p.player_id for p in remaining}
        bought = [p for p in best_eleven if p.player_id not in remaining_ids]
        final_squad = remaining + bought

    players_bought = [
        p for p in best_eleven
        if p not in remaining and p.player_id not in {x.player_id for x in remaining}
    ]
    transfer_budget_used = sum(p.market_value or 0 for p in players_bought)
    final_valuation = _compute_valuation(final_squad)
    net_benefit = final_valuation - initial_valuation - transfer_budget_used + sale_proceeds

    return SimulationResult(
        club_name=club_name,
        season=season,
        initial_squad=squad,
        final_squad=final_squad,
        players_sold=sold,
        players_bought=players_bought,
        best_eleven=best_eleven,
        formation=formation,
        initial_valuation=initial_valuation,
        final_valuation=final_valuation,
        transfer_budget_used=transfer_budget_used,
        net_benefit=net_benefit,
    )
