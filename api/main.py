"""
FastAPI backend for Team Transfers Simulator.

Exposes the same functionality as the Streamlit app through REST endpoints.
Includes SSE streaming for long-running operations (simulation progress).
"""
from __future__ import annotations

import json as _json
import os
import pickle
import unicodedata
import queue
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

from scraping.utils.helpers import list_json_bases, load_json
from webapp.i18n import format_currency


def _norm(s: str) -> str:
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()


TODAY_SEASON = "today"

LEAGUE_PRIORITY = {
    "laliga": 0, "la liga": 0,
    "premier league": 1,
    "serie a": 2, "seriea": 2,
    "bundesliga": 3,
    "ligue 1": 4, "ligue1": 4,
    "liga portugal": 5, "primeira liga": 5,
    "eredivisie": 6,
    "segunda división": 7, "segunda division": 7,
    "championship": 8,
}

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class PlayerOut(BaseModel):
    player_id: str
    name: str
    team: str = ""
    team_id: str = ""
    position: str = "N/A"
    age: Optional[int] = None
    nationality: str = ""
    market_value: Optional[float] = None
    predicted_value: Optional[float] = None
    fair_price: Optional[float] = None
    img_url: str = ""
    on_loan: bool = False

class ClubOut(BaseModel):
    name: str
    league: str = ""
    logo_url: str = ""
    total_market_value: Optional[float] = None

class LoadSquadRequest(BaseModel):
    club_name: str
    season: str

class SimulateRequest(BaseModel):
    club_name: str
    season: str
    transfer_budget: int = 0
    unlimited: bool = False
    players_to_sell: List[str] = []
    buy_counts: Optional[Dict[str, Any]] = None
    approach: str = "max_value"
    objective: str = "smv"
    sim_speed: str = "standard"
    # Advanced filters
    league_filter: Optional[List[str]] = None
    banned_clubs: Optional[List[str]] = None
    banned_players: Optional[List[str]] = None
    exclude_top_n: int = 0
    min_market_value: Optional[float] = None
    horizon: int = 1

class SoldPlayerOut(BaseModel):
    player_id: str
    name: str
    position: str
    market_value: Optional[float] = None
    destination_team: Optional[str] = None
    was_sold: bool
    img_url: str = ""

class SimulationResultOut(BaseModel):
    club_name: str
    season: str
    initial_budget: int
    sales_revenue: int
    total_budget: int
    players_sold: List[SoldPlayerOut]
    formation_needed: List[int]
    recommended_signings: List[PlayerOut]
    recommended_formation: List[int]
    total_signing_cost: int
    total_predicted_value: float

class SellRecommendation(BaseModel):
    player_id: str
    name: str
    position: str
    age: Optional[int]
    market_value: float
    predicted_value: float
    fair_price: Optional[float] = None
    decline: float
    decline_pct: float
    img_url: str = ""
    on_loan: bool = False

class SellRecommendationsOut(BaseModel):
    peak_players: List[SellRecommendation]

class XGrowthPlayer(BaseModel):
    player_id: str
    name: str
    position: str
    age: Optional[int]
    team: str
    league: str = ""
    nationality: str = ""
    other_nationalities: List[str] = []
    market_value: float
    predicted_value: float
    xgrowth: float
    fair_price: float
    net_benefit: float = 0
    roi: float = 0
    growth_pct: float = 0
    img_url: str = ""
    is_available: bool = True

class SimilarPlayerOut(BaseModel):
    player_id: str
    name: str
    position: str
    age: Optional[int]
    team: str
    market_value: float
    predicted_value: float
    xgrowth: float
    fair_price: float
    similarity: float
    img_url: str = ""

class PlayerAnalysisOut(BaseModel):
    player_id: str
    name: str
    position: str
    age: Optional[int]
    team: str
    market_value: float
    predicted_value: float
    xgrowth: float
    fair_price: float
    similar_players: List[SimilarPlayerOut]
    img_url: str = ""

class AnalyticsOut(BaseModel):
    xgrowth_ranking: List[XGrowthPlayer]
    signing_analysis: List[PlayerAnalysisOut]

class SearchPlayerOut(BaseModel):
    player_id: str
    name: str
    position: str
    age: Optional[int]
    team: str
    nationality: str
    market_value: float
    predicted_value: Optional[float]
    xgrowth: Optional[float]
    fair_price: Optional[float]
    img_url: str = ""

class SearchResults(BaseModel):
    players: List[SearchPlayerOut]
    total: int

class AISummaryRequest(BaseModel):
    api_key: str = ""
    language: str = "es"
    result_data: Optional[dict] = None

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Team Transfers Simulator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static assets mount — added at the bottom of the file to avoid
# conflicting with frontend/dist when the React build is present.
ASSETS_DIR = ROOT_DIR / "assets"

# In-memory cache for preloaded simulators
_sim_cache: Dict[str, Any] = {}
_last_result: Optional[Any] = None
_RESULT_CACHE_PATH = Path(tempfile.gettempdir()) / "team_analysis_last_result.pkl"


def _save_last_result(result: Any) -> None:
    """Persist result to disk so it survives server restarts."""
    global _last_result
    _last_result = result
    try:
        with open(_RESULT_CACHE_PATH, "wb") as f:
            pickle.dump(result, f)
    except Exception as exc:
        print(f"Warning: could not pickle last result: {exc}")


def _get_last_result() -> Optional[Any]:
    """Return in-memory result, or reload from disk if server was restarted."""
    global _last_result
    if _last_result is not None:
        return _last_result
    try:
        if _RESULT_CACHE_PATH.exists():
            with open(_RESULT_CACHE_PATH, "rb") as f:
                _last_result = pickle.load(f)
    except Exception as exc:
        print(f"Warning: could not unpickle last result: {exc}")
    return _last_result
# Cache horizon-extrapolated predicted values: key = "season|horizon"
_xgrowth_horizon_cache: Dict[str, Dict[str, float]] = {}


def _player_to_out(p) -> PlayerOut:
    return PlayerOut(
        player_id=p.player_id,
        name=p.name,
        team=p.team or "",
        team_id=p.team_id or "",
        position=p.position or "N/A",
        age=p.age,
        nationality=p.nationality or "",
        market_value=p.market_value,
        predicted_value=p.predicted_value,
        fair_price=round(_compute_fair_price(p), 0),
        img_url=p.img_url or "",
        on_loan=p.on_loan or False,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/seasons")
def get_seasons() -> List[str]:
    seasons: set[str] = set()
    for base in list_json_bases("teams_all_*.json"):
        s = base.replace("teams_all_", "")
        if s:
            seasons.add(s)
    # Also include seasons that have precomputed caches (e.g. future seasons)
    cache_dir = ROOT_DIR / "data" / "json" / "cache"
    if cache_dir.exists():
        for f in cache_dir.glob("season_data_*.json"):
            s = f.stem.replace("season_data_", "")
            if s and s != "today":
                seasons.add(s)
    return sorted(seasons, reverse=True)


@app.get("/api/clubs")
def get_clubs(season: str) -> List[ClubOut]:
    if season.lower() == TODAY_SEASON:
        bases = list_json_bases("teams_all_*.json")
        base = bases[-1] if bases else None
    else:
        base = f"teams_all_{season}"

    if base is None:
        return []
    data = load_json(base)
    # Fallback to latest available teams file (for future seasons without own data)
    if data is None or not isinstance(data, list):
        bases = list_json_bases("teams_all_*.json")
        base = bases[-1] if bases else None
        if base is None:
            return []
        data = load_json(base)
    if data is None or not isinstance(data, list):
        return []

    data.sort(key=lambda c: (
        LEAGUE_PRIORITY.get((c.get("league") or "").lower(), 99),
        -(c.get("total_market_value") or 0),
    ))

    return [
        ClubOut(
            name=c.get("name", ""),
            league=c.get("league", ""),
            logo_url=c.get("logo_url", ""),
            total_market_value=c.get("total_market_value"),
        )
        for c in data
        if c.get("name")
    ]


class LeagueOut(BaseModel):
    league_id: str
    name: str
    country: str = ""


@app.get("/api/leagues")
def get_leagues(season: str) -> List[LeagueOut]:
    """Return distinct leagues available for a season (from teams data)."""
    if season.lower() == TODAY_SEASON:
        bases = list_json_bases("teams_all_*.json")
        base = bases[-1] if bases else None
    else:
        base = f"teams_all_{season}"

    if base is None:
        return []
    data = load_json(base)
    if data is None or not isinstance(data, list):
        bases = list_json_bases("teams_all_*.json")
        base = bases[-1] if bases else None
        if base is None:
            return []
        data = load_json(base)
    if data is None or not isinstance(data, list):
        return []

    seen: Dict[str, LeagueOut] = {}
    for team in data:
        lid = team.get("league_id", "") or ""
        if lid and lid not in seen:
            seen[lid] = LeagueOut(
                league_id=lid,
                name=team.get("league", "") or lid,
                country=team.get("country", ""),
            )
    result = sorted(seen.values(), key=lambda l: l.name)
    return result


@app.get("/api/nationalities")
def get_nationalities() -> List[str]:
    """Return distinct nationalities across all cached simulators' player pools."""
    nats: set = set()
    for sim in _sim_cache.values():
        for p in sim.all_players:
            if p.nationality:
                nats.add(p.nationality)
            for n in (p.other_nationalities or []):
                if n:
                    nats.add(n)
    return sorted(nats)


@app.post("/api/load-squad")
def load_squad(req: LoadSquadRequest) -> List[PlayerOut]:
    from simulator.transfer_simulator import TransferSimulator

    cache_key = f"{req.club_name}|{req.season}"
    sim = TransferSimulator(
        club_name=req.club_name,
        season=req.season,
        transfer_budget=0,
    )
    try:
        squad = sim.preload_data(verbose=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    _sim_cache[cache_key] = sim
    _xgrowth_horizon_cache.clear()
    return [_player_to_out(p) for p in squad]


@app.get("/api/sell-recommendations")
def sell_recommendations(club_name: str, season: str) -> SellRecommendationsOut:
    """Return sale recommendations for the loaded squad."""
    cache_key = f"{club_name}|{season}"
    sim = _sim_cache.get(cache_key)
    if sim is None:
        raise HTTPException(status_code=400, detail="Load squad first")

    squad = sim.club_players
    peak: List[SellRecommendation] = []
    for p in squad:
        mv = p.market_value or 0
        pv = getattr(p, "predicted_value", None)
        if pv is None or mv <= 0:
            continue
        delta = mv - pv
        peak.append(SellRecommendation(
            player_id=p.player_id,
            name=p.name,
            position=p.position or "N/A",
            age=p.age,
            market_value=mv,
            predicted_value=pv,
            fair_price=round(_compute_fair_price(p), 0),
            decline=delta,
            decline_pct=delta / mv if mv else 0,
            img_url=p.img_url or "",
            on_loan=bool(p.on_loan),
        ))
    peak.sort(key=lambda r: r.decline, reverse=True)
    return SellRecommendationsOut(peak_players=peak)


def _compute_xgrowth(p) -> float:
    mv = p.market_value or 1
    pv = p.predicted_value or mv
    return (pv / mv) - 1 if mv > 0 else 0.0


def _compute_fair_price(p) -> float:
    """Fair price from linear extrapolation, stored in p.fair_price by precompute."""
    fp = getattr(p, "fair_price", None)
    if fp is not None:
        return min(250_000_000, max(0, fp))
    return p.predicted_value or p.market_value or 0


def _player_similarity(a, b) -> float:
    """0-1 financial similarity score between two players."""
    if (a.position or "") != (b.position or ""):
        return 0.0
    mv_a, mv_b = a.market_value or 1, b.market_value or 1
    age_a, age_b = a.age or 25, b.age or 25
    xg_a = ((a.predicted_value or mv_a) / mv_a) - 1 if mv_a > 0 else 0
    xg_b = ((b.predicted_value or mv_b) / mv_b) - 1 if mv_b > 0 else 0
    val_sim = 1 - min(abs(mv_a - mv_b) / max(mv_a, mv_b), 1)
    age_sim = 1 - min(abs(age_a - age_b) / 10, 1)
    xg_sim = 1 - min(abs(xg_a - xg_b) / max(abs(xg_a) + 0.01, abs(xg_b) + 0.01), 1)
    return 0.35 * val_sim + 0.25 * age_sim + 0.40 * xg_sim


@app.get("/api/analytics")
def get_analytics(club_name: str, season: str) -> AnalyticsOut:
    """Return xGrowth ranking and signing analysis with similar players."""
    cache_key = f"{club_name}|{season}"
    sim = _sim_cache.get(cache_key)
    if sim is None:
        raise HTTPException(status_code=400, detail="Load squad first")

    all_players = sim.all_players
    _lr = _get_last_result()
    signings = _lr.recommended_signings if _lr else []
    signing_ids = {p.player_id for p in signings}
    club_ids = {p.player_id for p in sim.club_players}

    # xGrowth ranking: top players by growth potential from the full pool
    pool = [
        p for p in all_players
        if p.predicted_value is not None
        and (p.market_value or 0) > 0
        and not p.on_loan
        and p.player_id not in club_ids
    ]
    pool.sort(key=lambda p: _compute_xgrowth(p), reverse=True)
    xgrowth_ranking = [
        XGrowthPlayer(
            player_id=p.player_id,
            name=p.name,
            position=p.position or "N/A",
            age=p.age,
            team=p.team or "",
            market_value=p.market_value or 0,
            predicted_value=p.predicted_value or 0,
            xgrowth=round(_compute_xgrowth(p), 4),
            fair_price=round(_compute_fair_price(p), 0),
            img_url=p.img_url or "",
        )
        for p in pool[:30]
    ]

    # Signing analysis: for each recommended signing, find similar players
    signing_analysis = []
    for s in signings:
        candidates = [
            p for p in pool
            if p.player_id != s.player_id
            and p.player_id not in signing_ids
            and (p.position or "") == (s.position or "")
        ]
        scored = [(p, _player_similarity(s, p)) for p in candidates]
        scored.sort(key=lambda t: t[1], reverse=True)
        similar = [
            SimilarPlayerOut(
                player_id=p.player_id,
                name=p.name,
                position=p.position or "N/A",
                age=p.age,
                team=p.team or "",
                market_value=p.market_value or 0,
                predicted_value=p.predicted_value or 0,
                xgrowth=round(_compute_xgrowth(p), 4),
                fair_price=round(_compute_fair_price(p), 0),
                similarity=round(sim_score, 3),
                img_url=p.img_url or "",
            )
            for p, sim_score in scored[:5]
        ]
        signing_analysis.append(PlayerAnalysisOut(
            player_id=s.player_id,
            name=s.name,
            position=s.position or "N/A",
            age=s.age,
            team=s.team or "",
            market_value=s.market_value or 0,
            predicted_value=s.predicted_value or 0,
            xgrowth=round(_compute_xgrowth(s), 4),
            fair_price=round(_compute_fair_price(s), 0),
            similar_players=similar,
            img_url=s.img_url or "",
        ))

    return AnalyticsOut(
        xgrowth_ranking=xgrowth_ranking,
        signing_analysis=signing_analysis,
    )


class XGrowthRanges(BaseModel):
    age: List[int] = [0, 50]
    market_value: List[float] = [0, 0]
    predicted_value: List[float] = [0, 0]
    fair_price: List[float] = [0, 0]
    xgrowth: List[float] = [0, 0]
    net_benefit: List[float] = [0, 0]
    roi: List[float] = [0, 0]
    growth_pct: List[float] = [0, 0]

class XGrowthResults(BaseModel):
    players: List[XGrowthPlayer]
    total: int
    ranges: XGrowthRanges = XGrowthRanges()


def _get_horizon_pv(sim, season: str, horizon: int) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Return ({player_id: predicted_value}, {player_id: fair_price}) for horizon.

    For horizon=1: predicted_value comes from precomputed player data;
                   fair_price comes from precomputed player data.
    For horizon>1: first tries to read from precomputed cache; otherwise
                   falls back to chained ML predictions at runtime.

    Caches results so repeated xGrowth requests with the same season+horizon
    don't recompute.
    """
    cache_key = f"{season}|{horizon}"
    if cache_key in _xgrowth_horizon_cache:
        return _xgrowth_horizon_cache[cache_key]

    from copy import copy
    from ml.value_predictor import clamp_prediction
    from ml.feature_engineering import (
        build_prediction_context,
        build_prediction_dataset,
        compute_fair_prices,
        load_team_league_mapping,
        _compute_trend,
        _compute_pct,
        _compute_diff,
    )
    from datetime import datetime
    import numpy as _np

    # Try precomputed horizon data from season cache (horizon >= 2)
    if horizon >= 2:
        from simulator.data_loader import load_season_cache
        cached = load_season_cache(season, max_age_days=30)
        if cached and "horizon_predictions" in cached:
            hz_key = str(horizon)
            hz_data = cached["horizon_predictions"].get(hz_key)
            if hz_data:
                pv_map = {k: float(v) for k, v in hz_data.get("predicted_values", {}).items()}
                fp_map = {k: float(v) for k, v in hz_data.get("fair_prices", {}).items()}
                if pv_map:
                    result = (pv_map, fp_map)
                    _xgrowth_horizon_cache[cache_key] = result
                    return result

    # Horizon 1: just return existing values
    if horizon <= 1:
        pv_map: Dict[str, float] = {}
        fp_map: Dict[str, float] = {}
        for p in sim.all_players:
            if p.predicted_value is not None and (p.market_value or 0) > 0:
                pv_map[p.player_id] = p.predicted_value
            fp = getattr(p, "fair_price", None)
            if fp is not None:
                fp_map[p.player_id] = fp
        result = (pv_map, fp_map)
        _xgrowth_horizon_cache[cache_key] = result
        return result

    # Build features using END of season cutoff (same as predicted_value)
    if season.lower() == "today":
        cutoff_date = datetime.now()
    else:
        start_year = int(season.split("-")[0])
        cutoff_date = datetime(start_year + 1, 7, 1)

    predictor = sim.predictor
    if not predictor:
        try:
            sim._load_predictor()
        except FileNotFoundError:
            from ml.value_predictor import ValuePredictor, SegmentedValuePredictor
            loaded = False
            if season.lower() != "today":
                start_yr = int(season.split("-")[0])
                for offset in range(6):
                    s = f"{start_yr - offset}-{start_yr - offset + 1}"
                    try:
                        seg = SegmentedValuePredictor(s)
                        if seg.is_trained:
                            sim.predictor = seg
                            loaded = True
                            break
                    except Exception:
                        continue
            if not loaded:
                fb = ValuePredictor.find_model_with_fallback(season) if season.lower() != "today" else ValuePredictor.get_latest_model()
                if fb and fb.exists():
                    sim.predictor = ValuePredictor(model_path=fb)
                else:
                    result = ({}, {})
                    _xgrowth_horizon_cache[cache_key] = result
                    return result
        predictor = sim.predictor

    all_valuations = sim._load_all_valuations(verbose=False)
    team_league_mapping = load_team_league_mapping(verbose=False)
    transfer_map, by_player, team_total_values = build_prediction_context(
        all_valuations, cutoff_date, verbose=False
    )

    player_dict = {p.player_id: p for p in sim.all_players
                   if (p.market_value or 0) > 0}
    base_features = build_prediction_dataset(
        all_valuations, cutoff_date,
        players=player_dict,
        team_league_mapping=team_league_mapping,
        transfer_map=transfer_map,
        by_player=by_player,
        team_total_values=team_total_values,
        verbose=False,
    )
    if not base_features:
        result = ({}, {})
        _xgrowth_horizon_cache[cache_key] = result
        return result

    # Year 1 predictions
    preds_y1 = predictor.predict_batch(base_features)
    feat_by_id = {}
    for feat, pred in zip(base_features, preds_y1):
        mv = feat.current_value
        clamped = clamp_prediction(pred, mv)
        feat_by_id[feat.player_id] = (feat, clamped)

    # Chain incrementally for years 2..horizon, caching intermediate horizons
    current_features = feat_by_id
    for year_offset in range(1, horizon):
        hz = year_offset + 1
        next_features_list = []
        player_ids_order = []
        july_year = cutoff_date.year + year_offset
        new_last_val_num = july_year + (7 - 1) / 12.0

        for pid, (feat, prev_pred) in current_features.items():
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
            nf.log_current_value = float(_np.log10(max(nf.current_value, 1.0)))
            if _np.isnan(nf.age):
                nf.age_value_ratio = float("nan")
            else:
                age_sq = max(nf.age, 1.0) ** 2
                nf.age_value_ratio = (nf.current_value / 1_000_000) / (age_sq / 100.0) if age_sq > 0 else 0.0
            nf.num_valuations += 1
            nf.months_of_history += 12

            next_features_list.append(nf)
            player_ids_order.append(pid)

        preds = predictor.predict_batch(next_features_list)
        new_current = {}
        for pid, nf, pred in zip(player_ids_order, next_features_list, preds):
            clamped = clamp_prediction(pred, nf.current_value)
            new_current[pid] = (nf, clamped)
        current_features = new_current

        # Cache intermediate horizon so horizon=2 is reusable when computing horizon=3
        hz_cache_key = f"{season}|{hz}"
        if hz_cache_key not in _xgrowth_horizon_cache:
            hz_pv = {pid: pred for pid, (_, pred) in current_features.items()}
            hz_cutoff = datetime(cutoff_date.year + hz - 1, cutoff_date.month, cutoff_date.day)
            hz_fp = compute_fair_prices(by_player, hz_cutoff)
            _xgrowth_horizon_cache[hz_cache_key] = (hz_pv, hz_fp)

    result = _xgrowth_horizon_cache[cache_key]
    return result


@app.get("/api/xgrowth")
def get_xgrowth(
    season: str = "",
    position: Optional[str] = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    min_age: Optional[int] = None,
    max_age: Optional[int] = None,
    club_name: Optional[str] = None,
    horizon: int = 1,
    league_filter: Optional[str] = None,
    exclude_top_n: int = 0,
    min_market_value: Optional[float] = None,
    sort_by: str = "xgrowth",
    limit: int = 50,
    # Slider filters (applied after range computation)
    f_age_min: Optional[int] = None,
    f_age_max: Optional[int] = None,
    f_mv_min: Optional[float] = None,
    f_mv_max: Optional[float] = None,
    f_pv_min: Optional[float] = None,
    f_pv_max: Optional[float] = None,
    f_fp_min: Optional[float] = None,
    f_fp_max: Optional[float] = None,
    f_xg_min: Optional[float] = None,
    f_nb_min: Optional[float] = None,
    f_roi_min: Optional[float] = None,
    f_gp_min: Optional[float] = None,
    team_query: Optional[str] = None,
    nationality_filter: Optional[str] = None,
    include_second_nationality: bool = False,
) -> XGrowthResults:
    """Top players by projected xGrowth with advanced filters."""
    sim = None
    for k, v in _sim_cache.items():
        if season and season in k:
            sim = v
            break
    if sim is None:
        for k, v in _sim_cache.items():
            sim = v
            break
    if sim is None:
        raise HTTPException(status_code=400, detail="Load squad first")

    # Club availability set (always computed for is_available flag, never used to filter)
    available_set: Optional[set] = None
    for _ck, _sv in _sim_cache.items():
        if season and season in _ck:
            _target_sim = _sv
            break
    else:
        _target_sim = sim
    if hasattr(_target_sim, "_get_available_players"):
        available_set = {
            p.player_id
            for p in _target_sim._get_available_players(
                _target_sim.all_players,
                _target_sim.club_players,
                is_athletic=getattr(_target_sim, "_is_athletic", False),
                athletic_eligible_ids=getattr(_target_sim, "_athletic_eligible_ids", None),
            )
        }

    # League filter set
    league_set: Optional[set] = None
    if league_filter:
        league_set = {lid.strip() for lid in league_filter.split(",") if lid.strip()}

    # Nationality filter set
    nat_set: Optional[set] = None
    if nationality_filter:
        nat_set = {n.strip() for n in nationality_filter.split(",") if n.strip()}

    # Exclude top N clubs by market value
    excluded_clubs: Optional[set] = None
    if exclude_top_n > 0 and hasattr(sim, "team_market_values") and sim.team_market_values:
        sorted_teams = sorted(
            sim.team_market_values.items(), key=lambda kv: kv[1], reverse=True,
        )
        excluded_clubs = {name.lower() for name, _ in sorted_teams[:exclude_top_n]}

    # Team league mapping (always loaded – used for league field in response)
    from ml.feature_engineering import load_team_league_mapping
    team_league_map = load_team_league_mapping()

    # Horizon-extrapolated predicted values and fair prices
    horizon_pv, horizon_fp = _get_horizon_pv(sim, season, horizon)

    club_ids = {p.player_id for p in sim.club_players}
    min_mv_euros = (min_market_value or 0) * 1_000_000

    pool = []
    for p in sim.all_players:
        if p.player_id not in horizon_pv:
            continue
        if (p.market_value or 0) <= 0 or p.on_loan:
            continue
        if p.player_id in club_ids:
            continue

        mv = p.market_value or 0

        if min_mv_euros and mv < min_mv_euros:
            continue
        if position and (p.position or "") != position:
            continue
        if min_value is not None and mv < min_value * 1_000_000:
            continue
        if max_value is not None and mv > max_value * 1_000_000:
            continue

        age = p.age or 0
        if min_age is not None and age < min_age:
            continue
        if max_age is not None and age > max_age:
            continue

        if excluded_clubs and (p.team or "").lower() in excluded_clubs:
            continue

        pool.append(p)

    def _fp(p):
        return horizon_fp.get(p.player_id, _compute_fair_price(p))

    def _metrics(p):
        mv = p.market_value or 0
        pv = horizon_pv.get(p.player_id, p.predicted_value or mv)
        if mv > 0:
            xg = (pv / mv) - 1
            roi = (pv - mv) / mv
            gp = pv / mv
        else:
            xg = 9999.0 if pv > 0 else 0.0
            roi = 9999.0 if pv > 0 else 0.0
            gp = 9999.0 if pv > 0 else 0.0
        nb = pv - mv
        return pv, xg, nb, roi, gp

    sort_keys = {
        "xgrowth": lambda p: _metrics(p)[1],
        "predicted_value": lambda p: _metrics(p)[0],
        "net_benefit": lambda p: _metrics(p)[2],
        "roi": lambda p: _metrics(p)[3],
        "growth_pct": lambda p: _metrics(p)[4],
        "market_value": lambda p: p.market_value or 0,
    }
    key_fn = sort_keys.get(sort_by, sort_keys["xgrowth"])
    pool.sort(key=key_fn, reverse=True)

    # Compute ranges from the full pool before applying limit
    ranges = XGrowthRanges()
    if pool:
        ages = [p.age for p in pool if p.age]
        mvs = [p.market_value or 0 for p in pool]
        all_metrics = [_metrics(p) for p in pool]
        pvs = [m[0] for m in all_metrics]
        xgs = [m[1] for m in all_metrics]
        nbs = [m[2] for m in all_metrics]
        rois = [m[3] for m in all_metrics]
        gps = [m[4] for m in all_metrics]
        fps = [_fp(p) for p in pool]
        ranges = XGrowthRanges(
            age=[min(ages) if ages else 15, max(ages) if ages else 45],
            market_value=[min(mvs), max(mvs)],
            predicted_value=[min(pvs), max(pvs)],
            fair_price=[min(fps), max(fps)],
            xgrowth=[round(min(xgs), 4), round(max(xgs), 4)],
            net_benefit=[round(min(nbs), 0), round(max(nbs), 0)],
            roi=[round(min(rois), 4), round(max(rois), 4)],
            growth_pct=[round(min(gps), 4), round(max(gps), 4)],
        )

    # Apply slider filters (after ranges, so ranges stay stable)
    tq = (team_query or "").lower().strip()
    filtered = []
    for p in pool:
        pv, xg, nb, roi_v, gp_v = _metrics(p)
        fp = _fp(p)
        age = p.age or 0
        mv = p.market_value or 0
        if position and (p.position or "") != position:
            continue
        if tq and tq not in (p.team or "").lower():
            continue
        if f_age_min is not None and age < f_age_min:
            continue
        if f_age_max is not None and age > f_age_max:
            continue
        if f_mv_min is not None and mv < f_mv_min:
            continue
        if f_mv_max is not None and mv > f_mv_max:
            continue
        if f_pv_min is not None and pv < f_pv_min:
            continue
        if f_pv_max is not None and pv > f_pv_max:
            continue
        if f_fp_min is not None and fp < f_fp_min:
            continue
        if f_fp_max is not None and fp > f_fp_max:
            continue
        if f_xg_min is not None and xg < f_xg_min:
            continue
        if f_nb_min is not None and nb < f_nb_min:
            continue
        if f_roi_min is not None and roi_v < f_roi_min:
            continue
        if f_gp_min is not None and gp_v < f_gp_min:
            continue
        filtered.append(p)

    total = len(filtered)
    subset = filtered[:limit] if limit > 0 else filtered
    def _player_league(p) -> str:
        if team_league_map:
            return (
                team_league_map
                .get((p.team_id or "").strip(), {})
                .get(sim.season, {})
                .get("league_id", "")
            )
        return ""

    results = []
    for p in subset:
        mv = p.market_value or 1
        pv, xg, nb, roi_v, gp_v = _metrics(p)
        results.append(XGrowthPlayer(
            player_id=p.player_id,
            name=p.name,
            position=p.position or "N/A",
            age=p.age,
            team=p.team or "",
            league=_player_league(p),
            nationality=p.nationality or "",
            other_nationalities=list(p.other_nationalities or []),
            market_value=p.market_value or 0,
            predicted_value=round(pv, 0),
            xgrowth=round(xg, 4),
            fair_price=round(_fp(p), 0),
            net_benefit=round(nb, 0),
            roi=round(roi_v, 4),
            growth_pct=round(gp_v, 4),
            img_url=p.img_url or "",
            is_available=available_set is None or p.player_id in available_set,
        ))
    return XGrowthResults(players=results, total=total, ranges=ranges)


@app.get("/api/search-players")
def search_players(
    q: str = "",
    season: str = "",
    position: Optional[str] = None,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    min_age: Optional[int] = None,
    max_age: Optional[int] = None,
    limit: int = 50,
) -> SearchResults:
    """Full-text player search with filters."""
    cache_key = None
    sim = None
    for k, v in _sim_cache.items():
        if season and season in k:
            sim = v
            cache_key = k
            break
    if sim is None:
        for k, v in _sim_cache.items():
            sim = v
            cache_key = k
            break
    if sim is None:
        raise HTTPException(status_code=400, detail="Load squad first")

    query_norm = _norm(q.strip())
    results = []
    for p in sim.all_players:
        if query_norm and query_norm not in _norm(p.name or ""):
            continue
        if position and (p.position or "") != position:
            continue
        mv = p.market_value or 0
        if min_value is not None and mv < min_value * 1_000_000:
            continue
        if max_value is not None and mv > max_value * 1_000_000:
            continue
        age = p.age or 0
        if min_age is not None and age < min_age:
            continue
        if max_age is not None and age > max_age:
            continue
        pv = p.predicted_value
        xg = None
        fp = round(_compute_fair_price(p), 0)
        if pv is not None and mv > 0:
            xg = round((pv / mv) - 1, 4)
        results.append(SearchPlayerOut(
            player_id=p.player_id,
            name=p.name,
            position=p.position or "N/A",
            age=p.age,
            team=p.team or "",
            nationality=p.nationality or "",
            market_value=mv,
            predicted_value=pv,
            xgrowth=xg,
            fair_price=fp,
            img_url=p.img_url or "",
        ))
    results.sort(key=lambda x: x.market_value, reverse=True)
    total = len(results)
    return SearchResults(players=results[:limit] if limit > 0 else results, total=total)


@app.post("/api/simulate")
def simulate(req: SimulateRequest):
    from simulator.transfer_simulator import TransferSimulator

    cache_key = f"{req.club_name}|{req.season}"
    sim = _sim_cache.get(cache_key)
    if sim is None:
        sim = TransferSimulator(
            club_name=req.club_name,
            season=req.season,
            transfer_budget=req.transfer_budget,
        )
        try:
            sim.preload_data(verbose=False)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        _sim_cache[cache_key] = sim

    sim.budget = req.transfer_budget if not req.unlimited else 999_999

    buy_counts = None
    if req.buy_counts:
        if "_formations" in req.buy_counts:
            buy_counts = {"_formations": req.buy_counts["_formations"]}
        else:
            buy_counts = {}
            for pos in ("GK", "DEF", "MID", "ATT"):
                if pos in req.buy_counts:
                    val = req.buy_counts[pos]
                    if isinstance(val, list) and len(val) == 2:
                        buy_counts[pos] = (val[0], val[1])

    try:
        result = sim.run(
            verbose=False,
            generate_summary=False,
            unlimited_budget=req.unlimited,
            players_to_sell=req.players_to_sell if req.players_to_sell is not None else None,
            buy_counts=buy_counts,
            approach=req.approach,
            objective=req.objective,
            sim_speed=req.sim_speed,
            league_filter=req.league_filter,
            banned_clubs=req.banned_clubs,
            banned_players=req.banned_players,
            exclude_top_n=req.exclude_top_n,
            min_market_value=req.min_market_value,
            horizon=req.horizon,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    _save_last_result(result)
    return _build_result_dict(result, sim=sim)


def _build_result_dict(result, sim=None) -> dict:
    """Serialize a TransferResult into the same shape as SimulationResultOut."""
    sold_out = []
    for sp in result.players_sold:
        p = sp.player
        sold_out.append({
            "player_id": p.player_id,
            "name": p.name,
            "position": p.position or "N/A",
            "market_value": p.market_value,
            "destination_team": sp.destination_team,
            "was_sold": sp.was_sold,
            "img_url": p.img_url or "",
        })

    signing_ids = {p.player_id for p in result.recommended_signings}
    signings_out = []
    for p in result.recommended_signings:
        out = _player_to_out(p).model_dump()
        if sim is not None:
            try:
                alts = sim.get_alternatives(p, exclude_ids=signing_ids, n=5)
                out["alternatives"] = [_player_to_out(a).model_dump() for a in alts]
            except Exception as exc:
                print(f"[WARN] Failed to compute alternatives for {p.name}: {exc}")
                out["alternatives"] = []
        else:
            out["alternatives"] = []
        signings_out.append(out)

    return {
        "club_name": result.club_name,
        "season": result.season,
        "initial_budget": result.initial_budget,
        "sales_revenue": result.sales_revenue,
        "total_budget": result.total_budget,
        "players_sold": sold_out,
        "formation_needed": result.formation_needed,
        "recommended_signings": signings_out,
        "recommended_formation": result.recommended_formation,
        "total_signing_cost": result.total_signing_cost,
        "total_predicted_value": result.total_predicted_value,
    }


@app.post("/api/simulate-stream")
def simulate_stream(req: SimulateRequest):
    """SSE endpoint: streams progress events, then the final result."""
    from simulator.transfer_simulator import TransferSimulator

    q: queue.Queue = queue.Queue()

    def _run():
        try:
            cache_key = f"{req.club_name}|{req.season}"
            sim = _sim_cache.get(cache_key)
            if sim is None:
                sim = TransferSimulator(
                    club_name=req.club_name,
                    season=req.season,
                    transfer_budget=req.transfer_budget,
                )
                sim.preload_data(verbose=False)
                _sim_cache[cache_key] = sim

            sim.budget = req.transfer_budget if not req.unlimited else 999_999

            buy_counts = None
            if req.buy_counts:
                if "_formations" in req.buy_counts:
                    buy_counts = {"_formations": req.buy_counts["_formations"]}
                else:
                    buy_counts = {}
                    for pos in ("GK", "DEF", "MID", "ATT"):
                        if pos in req.buy_counts:
                            val = req.buy_counts[pos]
                            if isinstance(val, list) and len(val) == 2:
                                buy_counts[pos] = (val[0], val[1])

            def on_progress(pct: float, step_key: str):
                q.put({"type": "progress", "percent": round(pct * 100), "step": step_key})

            result = sim.run(
                verbose=False,
                generate_summary=False,
                progress_callback=on_progress,
                unlimited_budget=req.unlimited,
                players_to_sell=req.players_to_sell if req.players_to_sell is not None else None,
                buy_counts=buy_counts,
                approach=req.approach,
                objective=req.objective,
                sim_speed=req.sim_speed,
                league_filter=req.league_filter,
                banned_clubs=req.banned_clubs,
                banned_players=req.banned_players,
                exclude_top_n=req.exclude_top_n,
                min_market_value=req.min_market_value,
                horizon=req.horizon,
            )
            _save_last_result(result)
            q.put({"type": "result", "data": _build_result_dict(result, sim=sim)})
        except Exception as exc:
            q.put({"type": "error", "detail": str(exc)})
        finally:
            q.put(None)

    threading.Thread(target=_run, daemon=True).start()

    def _event_stream():
        while True:
            msg = q.get()
            if msg is None:
                break
            yield f"data: {_json.dumps(msg)}\n\n"

    return StreamingResponse(_event_stream(), media_type="text/event-stream")


@app.post("/api/ai-summary")
def ai_summary(req: AISummaryRequest) -> Dict[str, str]:
    from simulator.llm_summarizer import _build_detailed_prompt, _build_prompt_from_result, _call_openai, _call_anthropic, _call_gemini

    # --- resolve API key / provider ---
    k = (req.api_key or "").strip()
    if k:
        if k.startswith("sk-ant-"):
            provider = "anthropic"
        elif k.startswith("sk-"):
            provider = "openai"
        else:
            provider = "gemini"
    else:
        provider = os.getenv("LLM_PROVIDER", "openai")
        env_keys = {
            "openai": os.getenv("OPENAI_API_KEY", ""),
            "anthropic": os.getenv("ANTHROPIC_API_KEY", ""),
            "gemini": os.getenv("GEMINI_API_KEY", ""),
        }
        k = env_keys.get(provider, "") or ""
        if not k:
            for fallback_prov in ("openai", "anthropic", "gemini"):
                fk = env_keys.get(fallback_prov, "")
                if fk:
                    provider, k = fallback_prov, fk
                    break
        if not k:
            raise HTTPException(
                status_code=400,
                detail="No API key provided. Enter a key or configure OPENAI_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY in .env",
            )

    def _call_llm(prompt: str) -> str:
        """Call the resolved LLM provider. Raises on any error."""
        if provider == "anthropic":
            summary = _call_anthropic(prompt, api_key=k, raise_on_error=True)
        elif provider == "gemini":
            summary = _call_gemini(prompt, api_key=k, raise_on_error=True)
        else:
            summary = _call_openai(prompt, api_key=k, raise_on_error=True)
        if not summary:
            raise RuntimeError("LLM returned an empty response")
        return summary

    # --- build prompt from result_data (frontend) or cached result (server) ---
    prompt: Optional[str] = None
    rd = req.result_data

    if rd is not None:
        sold_info = []
        for sp in rd.get("players_sold", []):
            mv = (sp.get("market_value") or 0) / 1e6
            name = sp.get("name", "?")
            pos = sp.get("position", "?")
            dest = sp.get("destination_team", "?")
            if sp.get("was_sold", True):
                sold_info.append(f"  - {name} ({pos}): €{mv:.1f}M -> {dest}")
            else:
                sold_info.append(f"  - {name} ({pos}): €{mv:.1f}M (no buyer found)")

        bought_info = []
        for p in rd.get("recommended_signings", []):
            mv = (p.get("market_value") or 0) / 1e6
            pv = (p.get("predicted_value") or 0) / 1e6
            team = p.get("team", "?")
            bought_info.append(f"  - {p.get('name','?')} ({p.get('position','?')}, from {team}): €{mv:.1f}M -> €{pv:.1f}M predicted")

        sold_total = sum((s.get("market_value") or 0) for s in rd.get("players_sold", [])) / 1e6
        bought_total = sum((p.get("market_value") or 0) for p in rd.get("recommended_signings", [])) / 1e6
        bought_pred = sum((p.get("predicted_value") or 0) for p in rd.get("recommended_signings", [])) / 1e6
        total_budget = rd.get("total_budget", 0)

        prompt = _build_detailed_prompt(
            club_name=rd.get("club_name", "Unknown"),
            season=rd.get("season", "?"),
            initial_budget=rd.get("initial_budget", 0),
            sales_revenue=rd.get("sales_revenue", 0),
            total_budget=total_budget,
            sold_info=sold_info,
            bought_info=bought_info,
            rest_squad_info=[],
            sold_total_value=sold_total,
            sold_total_predicted=0,
            bought_total_value=bought_total,
            bought_total_predicted=bought_pred,
            rest_squad_total_value=0,
            rest_squad_total_predicted=0,
            total_cost=bought_total,
            total_predicted=bought_pred,
            net_benefit=bought_pred - bought_total,
            remaining_budget=total_budget - bought_total,
            language=req.language,
        )

    if prompt is None:
        result = _get_last_result()
        if result is None:
            raise HTTPException(
                status_code=400,
                detail="No simulation result available. Run a simulation first.",
            )
        prompt = _build_prompt_from_result(result, language=req.language)

    try:
        return {"summary": _call_llm(prompt)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM error ({provider}): {exc}")


# Serve compiled frontend (production) or fall back to root assets
_FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
elif ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
