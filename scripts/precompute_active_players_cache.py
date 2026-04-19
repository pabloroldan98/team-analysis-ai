#!/usr/bin/env python3
"""
Precompute ALL season-level data and save to a single cache file.

Everything that depends only on the season (not the club or simulation params)
is computed here so the simulator can load it instantly:
  - Active players with ML predicted values
  - Team market values (team_name -> total_market_value)
  - Athletic-eligible player IDs (for Athletic Bilbao buy/sell policy)

For "today": the file is named ``_today.json`` and includes a ``computed_date``
field.  The simulator checks freshness: if the difference between today and
computed_date is > 1 day, the cache is considered stale and recomputed on the fly.

Output: data/json/cache/season_data_{season}.json
        data/json/cache/season_data_today.json  (for --season today)

Usage:
  python scripts/precompute_active_players_cache.py --season today
  python scripts/precompute_active_players_cache.py --season today --date 2026-02-24
  python scripts/precompute_active_players_cache.py --season 2024-2025
  python scripts/precompute_active_players_cache.py --all-seasons
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from tqdm import tqdm

from scraping.utils.helpers import DATA_DIR, list_json_bases, load_json
from simulator.data_loader import get_active_players_at_season_start
from ml.feature_engineering import (
    build_prediction_context,
    build_prediction_dataset,
    compute_fair_prices,
    load_team_league_mapping,
    _load_all_transfers,
)
from ml.value_predictor import ValuePredictor, SegmentedValuePredictor, MODELS_DIR
from entities.valuation import Valuation
from entities.transfer import Transfer

# Re-use the constants from the simulator
from simulator.transfer_simulator import ATHLETIC_FAMILY_IDS, ATHLETIC_FAMILY_NAMES

CACHE_DIR = DATA_DIR / "cache"
CACHE_PREFIX = "season_data"


def _load_all_valuations(verbose: bool = False) -> List[Valuation]:
    """Load all valuations from every valuations_all_*.json file."""
    all_vals: List[Valuation] = []
    bases = list(list_json_bases("valuations_all_*.json"))
    for base in tqdm(bases, desc="Loading valuations", disable=not verbose):
        data = load_json(base)
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    all_vals.append(Valuation.from_dict(item))
    return all_vals


def _calculate_team_market_values(players) -> Dict[str, float]:
    """Build {team_name: total_market_value} from all active players."""
    team_values: Dict[str, float] = {}
    for p in players:
        if p.team:
            team_values[p.team] = team_values.get(p.team, 0) + (p.market_value or 0)
    return team_values


def _extract_athletic_eligible_ids(all_transfers: List[Transfer]) -> Set[str]:
    """Extract Athletic-eligible player IDs from already-loaded Transfer objects."""
    eligible: Set[str] = set()
    for t in all_transfers:
        from_id = str(t.from_club_id or "")
        from_name = (t.from_club_name or "").lower()
        to_id = str(t.to_club_id or "")
        to_name = (t.to_club_name or "").lower()
        if (from_id in ATHLETIC_FAMILY_IDS or from_name in ATHLETIC_FAMILY_NAMES
                or to_id in ATHLETIC_FAMILY_IDS or to_name in ATHLETIC_FAMILY_NAMES):
            pid = t.player_id
            if pid:
                eligible.add(str(pid))
    return eligible


def _get_previous_season(season: str) -> Optional[str]:
    """Return the season string for the previous season, or None for 'today'."""
    if season.lower() == "today":
        now = datetime.now()
        if now.month >= 7:
            start = now.year
        else:
            start = now.year - 1
        prev_start = start - 1
        return f"{prev_start}-{prev_start + 1}"
    start_year = int(season.split("-")[0])
    prev_start = start_year - 1
    return f"{prev_start}-{prev_start + 1}"


def _get_cutoff_date(season: str, override_date: Optional[str] = None) -> datetime:
    """Return cutoff datetime for a season."""
    if season.lower() == "today":
        if override_date:
            return datetime.strptime(override_date, "%Y-%m-%d")
        return datetime.now()
    start_year = int(season.split("-")[0])
    return datetime(start_year, 7, 1)


def precompute_and_save(
    season: str,
    verbose: bool = True,
    override_date: Optional[str] = None,
) -> Path:
    """
    Compute everything for a season and save to a single JSON cache file.

    Args:
        season: e.g. "2024-2025" or "today"
        verbose: progress output
        override_date: YYYY-MM-DD string; used as "today" in GitHub Actions
                       so the cache knows what date it represents.

    Returns:
        Path to the saved cache file.
    """
    cutoff_date = _get_cutoff_date(season, override_date)

    if season.lower() == "today":
        model_path = ValuePredictor.get_latest_model()
    else:
        model_path = ValuePredictor.find_model_with_fallback(season)

    if model_path is None or not Path(model_path).exists():
        raise FileNotFoundError(
            f"No model for season '{season}' (also checked previous seasons). "
            f"Run: python -m ml.train_pipeline --season {season}"
        )

    if verbose:
        print(f"=== Precomputing season data for '{season}' ===")
        print(f"  Cutoff date : {cutoff_date.strftime('%Y-%m-%d')}")
        print(f"  Model       : {model_path}")

    # ── 1. Active players ────────────────────────────────────────────────
    if verbose:
        print("\n[1/5] Loading active players...")
    players = get_active_players_at_season_start(season, verbose=verbose)
    if not players:
        raise ValueError(f"No active players found for season '{season}'")
    if verbose:
        print(f"  → {len(players)} active players")

    # ── 2. Team market values ────────────────────────────────────────────
    if verbose:
        print("\n[2/5] Calculating team market values...")
    team_market_values = _calculate_team_market_values(players)
    if verbose:
        print(f"  → {len(team_market_values)} teams")

    # ── 3. Load transfers once (shared by Athletic scan + prediction context)
    if verbose:
        print("\n[3/5] Loading transfers + Athletic eligibility (single pass)...")
    all_transfers = _load_all_transfers(verbose=verbose)
    athletic_eligible_ids = _extract_athletic_eligible_ids(all_transfers)
    if verbose:
        print(f"  → {len(all_transfers)} transfers, {len(athletic_eligible_ids)} Athletic-eligible players")

    # ── 4. ML predictions ────────────────────────────────────────────────
    if verbose:
        print("\n[4/5] Loading valuations + building prediction features...")
    all_valuations = _load_all_valuations(verbose=verbose)
    team_league_mapping = load_team_league_mapping(verbose=verbose)
    transfer_map, by_player, team_total_values, injury_intervals_by_player = build_prediction_context(
        all_valuations, cutoff_date, all_transfers=all_transfers, verbose=verbose
    )

    player_dict = {p.player_id: p for p in players}
    features = build_prediction_dataset(
        all_valuations,
        cutoff_date,
        players=player_dict,
        team_league_mapping=team_league_mapping,
        transfer_map=transfer_map,
        by_player=by_player,
        team_total_values=team_total_values,
        injury_intervals_by_player=injury_intervals_by_player,
        verbose=verbose,
    )

    predictor = None
    # Try segmented models: exact season first, then fall back
    seg_seasons = [season]
    if season.lower() != "today":
        start_yr = int(season.split("-")[0])
        seg_seasons += [f"{start_yr - i}-{start_yr - i + 1}" for i in range(1, 6)]
    for seg_s in seg_seasons:
        try:
            seg = SegmentedValuePredictor(seg_s)
            if seg.is_trained:
                predictor = seg
                if verbose:
                    segs = list(seg.segment_models.keys())
                    print(f"  Using segmented predictor ({seg_s}) with {len(segs)} segments: {segs}")
                break
        except Exception:
            continue
    if predictor is None:
        predictor = ValuePredictor(model_path)

    predictions = predictor.predict_batch(features)
    pred_map = {f.player_id: pred for f, pred in zip(features, predictions)}

    for p in players:
        p.predicted_value = pred_map.get(p.player_id, p.market_value)

    if verbose:
        print(f"  → Predicted values for {len(pred_map)} / {len(players)} players")

    # ── 4b. Fair price (linear extrapolation from last 2 valuations) ───
    if verbose:
        print(f"\n[4b] Computing fair prices (linear extrapolation, cutoff {cutoff_date.strftime('%Y-%m-%d')})...")
    fair_price_map = compute_fair_prices(by_player, cutoff_date)
    for p in players:
        fp = fair_price_map.get(p.player_id)
        if fp is not None:
            p.fair_price = fp

    if verbose:
        print(f"  → Fair prices for {len(fair_price_map)} / {len(players)} players")

    # ── 4c. Multi-horizon predictions (2y, 3y) — incremental ──────────
    from copy import copy
    from ml.value_predictor import clamp_prediction
    from ml.feature_engineering import _compute_trend, _compute_pct, _compute_diff
    import numpy as np_util

    if season.lower() == "today":
        pred_cutoff = cutoff_date
    else:
        start_yr = int(season.split("-")[0])
        pred_cutoff = datetime(start_yr + 1, 7, 1)

    feat_map = {f.player_id: f for f in features}
    horizon_data: Dict[int, Dict[str, float]] = {}

    current = {
        pid: (feat_map[pid], clamp_prediction(pred_map[pid], feat_map[pid].current_value))
        for pid in pred_map if pid in feat_map
    }

    max_horizon = 3
    for year_offset in range(1, max_horizon):
        hz = year_offset + 1
        if verbose:
            print(f"\n[4c] Computing horizon {hz}y predictions (year {year_offset}→{year_offset+1})...")

        next_feats = []
        pids_order = []
        july_year = pred_cutoff.year + year_offset
        new_last_val_num = july_year + (7 - 1) / 12.0

        for pid, (feat, prev_pred) in current.items():
            nf = copy(feat)
            old_cv = nf.current_value

            nf.current_value = prev_pred
            nf.last_valuation_date_num = new_last_val_num
            nf.age = nf.age + 1.0

            nf.value_5y_ago = nf.value_4y_ago
            nf.value_4y_ago = nf.value_3y_ago
            nf.value_3y_ago = nf.value_2y_ago
            nf.value_2y_ago = nf.value_1y_ago
            nf.value_1y_ago = old_cv

            nf.trend_1y = _compute_trend(nf.current_value, nf.value_1y_ago)
            nf.trend_2y = _compute_trend(nf.current_value, nf.value_2y_ago)
            nf.trend_4y = _compute_trend(nf.current_value, nf.value_4y_ago)
            nf.trend_5y = _compute_trend(nf.current_value, nf.value_5y_ago)

            nf.pct_1y = _compute_pct(nf.current_value, nf.value_1y_ago)
            nf.pct_2y = _compute_pct(nf.current_value, nf.value_2y_ago)
            nf.pct_4y = _compute_pct(nf.current_value, nf.value_4y_ago)
            nf.pct_5y = _compute_pct(nf.current_value, nf.value_5y_ago)

            nf.diff_1y = _compute_diff(nf.current_value, nf.value_1y_ago)
            nf.diff_2y = _compute_diff(nf.current_value, nf.value_2y_ago)
            nf.diff_4y = _compute_diff(nf.current_value, nf.value_4y_ago)
            nf.diff_5y = _compute_diff(nf.current_value, nf.value_5y_ago)

            nf.value_acceleration = nf.trend_1y - nf.trend_2y
            nf.max_value = max(nf.max_value, nf.current_value)
            nf.peak_ratio = nf.current_value / max(nf.max_value, 1.0)
            nf.log_current_value = float(np_util.log10(max(nf.current_value, 1.0)))
            if np_util.isnan(nf.age):
                nf.age_value_ratio = float("nan")
            else:
                age_sq = max(nf.age, 1.0) ** 2
                nf.age_value_ratio = (nf.current_value / 1_000_000) / (age_sq / 100.0) if age_sq > 0 else 0.0
            nf.num_valuations += 1
            nf.months_of_history += 12

            next_feats.append(nf)
            pids_order.append(pid)

        preds = predictor.predict_batch(next_feats)
        new_current = {}
        for pid, nf, pred in zip(pids_order, next_feats, preds):
            clamped = clamp_prediction(pred, nf.current_value)
            new_current[pid] = (nf, clamped)
        current = new_current

        hz_pv = {pid: round(pred, 2) for pid, (_, pred) in current.items()}
        hz_cutoff = datetime(pred_cutoff.year + hz - 1, pred_cutoff.month, pred_cutoff.day)
        hz_fp = compute_fair_prices(by_player, hz_cutoff)
        hz_fp = {pid: round(v, 2) for pid, v in hz_fp.items()}

        horizon_data[hz] = {"predicted_values": hz_pv, "fair_prices": hz_fp}
        if verbose:
            print(f"  → Horizon {hz}y: {len(hz_pv)} predictions, {len(hz_fp)} fair prices")

    # ── 5. Save ──────────────────────────────────────────────────────────
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    if season.lower() == "today":
        cache_path = CACHE_DIR / f"{CACHE_PREFIX}_today.json"
    else:
        cache_path = CACHE_DIR / f"{CACHE_PREFIX}_{season}.json"

    computed_date_str = (
        override_date
        if override_date
        else datetime.now().strftime("%Y-%m-%d")
    )

    payload = {
        "season": season,
        "computed_date": computed_date_str,
        "player_count": len(players),
        "team_count": len(team_market_values),
        "athletic_eligible_count": len(athletic_eligible_ids),
        "players": [p.to_dict() for p in players],
        "team_market_values": team_market_values,
        "athletic_eligible_ids": sorted(athletic_eligible_ids),
        "horizon_predictions": {
            str(hz): data for hz, data in horizon_data.items()
        },
    }

    if verbose:
        print(f"\n[5/5] Saving to {cache_path} ...")

    import numpy as np

    class _NumpyEncoder(json.JSONEncoder):
        def default(self, obj):
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            return super().default(obj)

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, cls=_NumpyEncoder)

    size_mb = cache_path.stat().st_size / (1024 * 1024)
    if verbose:
        print(f"  → Saved ({size_mb:.1f} MB)")

    return cache_path


def main():
    parser = argparse.ArgumentParser(
        description="Precompute all season-level data (players, predictions, team values, athletic eligibility)"
    )
    parser.add_argument(
        "--season", type=str, default=None,
        help="Season to precompute (e.g. 2024-2025) or 'today'",
    )
    parser.add_argument(
        "--all-seasons", action="store_true",
        help="Precompute for every season found in teams_all_*.json",
    )
    parser.add_argument(
        "--include-next", action="store_true",
        help="With --all-seasons, also compute the next future season (e.g. 2026-2027)",
    )
    parser.add_argument(
        "--date", type=str, default=None,
        help="Override 'today' date (YYYY-MM-DD). Passed from GitHub Actions.",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="Reduce output",
    )
    args = parser.parse_args()
    verbose = not args.quiet

    if args.all_seasons:
        season_set = {
            base.replace("teams_all_", "")
            for base in list_json_bases("teams_all_*.json")
            if base.startswith("teams_all_")
        }
        if args.include_next and season_set:
            latest_start = max(int(s.split("-")[0]) for s in season_set)
            nxt = latest_start + 1
            season_set.add(f"{nxt}-{nxt + 1}")
        seasons = sorted(season_set, reverse=True)
        if verbose:
            print(f"Precomputing {len(seasons)} seasons: {seasons}\n")
        for s in seasons:
            try:
                precompute_and_save(s, verbose=verbose)
            except FileNotFoundError as e:
                if verbose:
                    print(f"  ⚠ Skipping {s}: {e}\n")
            except Exception as e:
                print(f"  ✗ Error for {s}: {e}")
                raise
    elif args.season:
        precompute_and_save(args.season, verbose=verbose, override_date=args.date)
    else:
        parser.error("Specify --season or --all-seasons")


if __name__ == "__main__":
    main()
