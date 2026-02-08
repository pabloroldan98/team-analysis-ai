"""
Best 11 calculation using knapsack-based formations.

Ported from knapsack-football-formations. Adapts Player objects for the
multiple-choice knapsack: price and value are derived from market_value.
"""
from __future__ import annotations

import copy
import itertools
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

try:
    import streamlit as st

    STREAMLIT_ACTIVE = st.runtime.exists()
except Exception:
    STREAMLIT_ACTIVE = False

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

from player import Player

# Scale factor: market_value in euros -> knapsack weight (millions)
# e.g. 50M€ player -> price=50, budget 200M -> budget_int=200
_PRICE_SCALE = 1_000_000

FORMATIONS = [
    [3, 4, 3],
    [3, 5, 2],
    [4, 3, 3],
    [4, 4, 2],
    [4, 5, 1],
    [5, 3, 2],
    [5, 4, 1],
]


@dataclass
class _KnapsackPlayer:
    """Wrapper for Player with knapsack-specific price and value."""

    player: Player
    position: str
    price: int
    value: float

    def __getattr__(self, name: str):
        """Delegate unknown attrs to the underlying Player."""
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        return getattr(self.player, name)


def _players_to_knapsack_format(players: List[Player]) -> List[_KnapsackPlayer]:
    """Convert Player list to knapsack format: price=market_value, value=market_value."""
    result = []
    for p in players:
        mv = p.market_value or 0.0
        price = max(1, int(round(mv / _PRICE_SCALE)))
        result.append(
            _KnapsackPlayer(
                player=p,
                position=p.position,
                price=price,
                value=float(mv),
            )
        )
    return result


def _knapsack_multichoice_onepick(
    weights: List[List[int]],
    values: List[List[float]],
    max_weight: int,
    verbose: bool = False,
    update_master: Optional[Callable[[int], None]] = None,
) -> Tuple[float, List[Tuple[int, int]]]:
    """
    Multiple-choice knapsack: pick exactly one from each group.
    Returns (best_score, path as list of (group_idx, item_idx)).
    """
    if not weights or not weights[0]:
        return 0.0, []

    last_array = [-1.0] * (max_weight + 1)
    last_path = [[] for _ in range(max_weight + 1)]
    for i in range(len(weights[0])):
        w = weights[0][i]
        if w <= max_weight and last_array[w] < values[0][i]:
            last_array[w] = values[0][i]
            last_path[w] = [(0, i)]

    total_ops = sum(len(weights[i]) for i in range(1, len(weights)))
    pbar = tqdm(total=total_ops, disable=not verbose, desc="Knapsack") if tqdm else None

    for i in range(1, len(weights)):
        current_array = [-1.0] * (max_weight + 1)
        current_path = [[] for _ in range(max_weight + 1)]
        for j in range(len(weights[i])):
            w_ij = weights[i][j]
            for k in range(w_ij, max_weight + 1):
                prev = k - w_ij
                if last_array[prev] >= 0:
                    new_val = last_array[prev] + values[i][j]
                    if current_array[k] < new_val:
                        current_array[k] = new_val
                        current_path[k] = copy.deepcopy(last_path[prev])
                        current_path[k].append((i, j))
            if pbar:
                pbar.update(1)
            if update_master:
                update_master(1)
        last_array = current_array
        last_path = current_path

    if pbar:
        pbar.close()

    best_score = max(last_array)
    best_idx = last_array.index(best_score)
    return best_score, last_path[best_idx]


def filter_players_knapsack(
    players_list: List[_KnapsackPlayer],
    formation: List[int],
) -> List[_KnapsackPlayer]:
    """
    Filter players by formation and per-position limits, keeping highest-value
    players per price bucket.

    Formation:
    - len==3: [DEF, MID, ATT], GK=1
    - len==4: [GK, DEF, MID, ATT]
    - else: [DEF, MID..., ATT], GK=1
    """
    # Shallow iteration - we don't mutate items, only build filtered list
    result = list(players_list)

    if len(formation) == 3:
        max_gk = 1
        max_def = formation[0]
        max_mid = formation[1]
        max_att = formation[2]
    elif len(formation) == 4:
        max_gk = formation[0]
        max_def = formation[1]
        max_mid = formation[2]
        max_att = formation[3]
    else:
        max_gk = 1
        max_def = formation[0]
        max_mid = sum(formation[1:-1])
        max_att = formation[-1]

    max_limits = {"GK": max_gk, "DEF": max_def, "MID": max_mid, "ATT": max_att}

    buckets = defaultdict(lambda: defaultdict(list))
    for p in result:
        buckets[p.position][p.price].append(p)

    filtered = []
    for position, price_dict in buckets.items():
        limit = max_limits.get(position)
        for group in price_dict.values():
            if limit is None:
                filtered.extend(group)
            else:
                top_n = sorted(group, key=lambda pl: pl.value, reverse=True)[:limit]
                filtered.extend(top_n)

    filtered.sort(key=lambda pl: pl.value, reverse=True)
    return filtered


def players_preproc(
    players_list: List[_KnapsackPlayer],
    formation: List[int],
) -> Tuple[List[List[float]], List[List[int]], List]:
    """
    Preprocess players into groups (GK, DEF, MID, ATT) with combinations.
    Returns (values, weights, indexes) per group for knapsack_multichoice_onepick.
    """
    if len(formation) == 3:
        max_gk = 1
        max_def = formation[0]
        max_mid = formation[1]
        max_att = formation[2]
    elif len(formation) == 4:
        max_gk = formation[0]
        max_def = formation[1]
        max_mid = formation[2]
        max_att = formation[3]
    else:
        max_gk = 1
        max_def = formation[0]
        max_mid = sum(formation[1:-1])
        max_att = formation[-1]

    def generate_group(full: List, pos: str):
        vals, wgts, idxs = [], [], []
        for i, item in enumerate(full):
            if item.position == pos:
                vals.append(item.value)
                wgts.append(item.price)
                idxs.append(i)
        return vals, wgts, idxs

    def group_preproc(gvals, gwgts, idxs, r: int):
        if r <= 0 or not idxs:
            return [], [], []
        combs_v = list(itertools.combinations(gvals, r))
        combs_w = list(itertools.combinations(gwgts, r))
        combs_i = list(itertools.combinations(idxs, r))
        return (
            [sum(c) for c in combs_v],
            [sum(c) for c in combs_w],
            list(combs_i),
        )

    gk_v, gk_w, gk_i = generate_group(players_list, "GK")
    gk_cv, gk_cw, gk_ci = group_preproc(gk_v, gk_w, gk_i, max_gk)

    def_v, def_w, def_i = generate_group(players_list, "DEF")
    def_cv, def_cw, def_ci = group_preproc(def_v, def_w, def_i, max_def)

    mid_v, mid_w, mid_i = generate_group(players_list, "MID")
    mid_cv, mid_cw, mid_ci = group_preproc(mid_v, mid_w, mid_i, max_mid)

    att_v, att_w, att_i = generate_group(players_list, "ATT")
    att_cv, att_cw, att_ci = group_preproc(att_v, att_w, att_i, max_att)

    all_values = [gk_cv, def_cv, mid_cv, att_cv]
    all_weights = [gk_cw, def_cw, mid_cw, att_cw]
    all_indexes = [gk_ci, def_ci, mid_ci, att_ci]

    # Skip if any required group is empty (cannot form valid 11)
    if any(
        not v or not w or not idx
        for v, w, idx in zip(all_values, all_weights, all_indexes)
    ):
        return [], [], []

    return all_values, all_weights, all_indexes


def best_full_teams(
    players: List[Player],
    formations: Optional[List[List[int]]] = None,
    budget: float = 300_000_000,
    speed_up: bool = True,
    verbose: int = 0,
    progress_callback: Optional[Callable[[float], None]] = None,
) -> List[Tuple[List[int], float, List[Player]]]:
    """
    Find best full teams (11 players) for each formation within budget.

    Args:
        players: List of Player objects.
        formations: List of [DEF, MID, ATT] or [GK, DEF, MID, ATT].
        budget: Max spend in euros.
        speed_up: Limit candidate list for faster computation.
        verbose: 0=quiet, 1=print, 2=verbose.
        progress_callback: Optional fn(percent: float) for UI progress.

    Returns:
        List of (formation, score, best_11_players) sorted by score descending.
    """
    formations = formations or FORMATIONS
    knapsack_players = _players_to_knapsack_format(players)
    budget_int = max(1, min(int(round(budget / _PRICE_SCALE)), 999_999))

    def limit_list(plist: List, formation: List[int]) -> List:
        if not speed_up:
            return plist
        # Limit candidates to keep combinations tractable (C(n,r) grows fast)
        if any(x >= 6 for x in formation):
            return plist[:70]
        if any(x >= 5 for x in formation):
            return plist[:80]
        if any(x >= 4 for x in formation):
            return plist[:100]
        return plist

    total_ops = 0
    precomputed = []
    for formation in formations:
        filtered = filter_players_knapsack(knapsack_players, formation)
        filtered = limit_list(filtered, formation)
        vals, wgts, idxs = players_preproc(filtered, formation)
        ops = sum(len(g) for g in (wgts or [[]])[1:]) if wgts else 0
        total_ops += ops
        precomputed.append((formation, filtered, vals, wgts, idxs))

    completed = [0]

    def make_update_master():
        def update(n: int):
            completed[0] += n
            pct = (completed[0] / total_ops) * 100 if total_ops else 100
            if progress_callback:
                progress_callback(pct)
            if STREAMLIT_ACTIVE:
                try:
                    progress_bar = getattr(st.session_state, "_knapsack_progress", None)
                    if progress_bar:
                        progress_bar.progress(min(1.0, completed[0] / total_ops))
                except Exception:
                    pass

        return update

    update_master = make_update_master() if total_ops else None

    results = []
    for formation, filtered, vals, wgts, idxs in precomputed:
        if not vals or not wgts or not idxs:
            continue
        score, path = _knapsack_multichoice_onepick(
            wgts,
            vals,
            budget_int,
            verbose=verbose >= 2,
            update_master=update_master,
        )
        result_players = []
        for (gi, ji) in path:
            for orig_idx in idxs[gi][ji]:
                result_players.append(filtered[orig_idx].player)
        results.append((formation, score, result_players))

    results.sort(key=lambda x: x[1], reverse=True)

    if verbose >= 1:
        for formation, score, team in results:
            total_price = sum(p.market_value or 0 for p in team)
            print(
                f"Formation {formation}: score={score:.0f} | price=€{total_price/1e6:.1f}M"
            )

    return results


def get_best_eleven(
    players: List[Player],
    budget: float = 300_000_000,
    formations: Optional[List[List[int]]] = None,
    progress_callback: Optional[Callable[[float], None]] = None,
) -> Tuple[List[Player], List[int]]:
    """
    Convenience: return best 11 and its formation.

    Returns:
        (best_11_players, formation e.g. [4, 3, 3])
    """
    formations = formations or FORMATIONS
    results = best_full_teams(
        players,
        formations=formations,
        budget=budget,
        progress_callback=progress_callback,
    )
    if not results:
        return [], []
    formation, _, best_11 = results[0]
    return best_11, formation
