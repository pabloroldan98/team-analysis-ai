# streamlit_app.py
"""
Team Transfers Simulator – Streamlit frontend.

Connects directly to the TransferSimulator engine, which:
  1. Sells random players and finds destination teams
  2. Predicts future values with an XGBoost model
  3. Optimises signings via knapsack
  4. (Optionally) generates an AI narrative through an LLM
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import streamlit as st

# ── project root on sys.path ────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

from webapp.i18n import t, format_currency
from scraping.utils.helpers import list_json_bases, load_json

# ── constants ────────────────────────────────────────────────────────────────
ASSETS_DIR = ROOT_DIR / "assets"
LANG_DIR = ASSETS_DIR / "language"
ARROW_DOWN = ASSETS_DIR / "arrows" / "Down_red_arrow.png"
ARROW_UP = ASSETS_DIR / "arrows" / "Up_green_arrow.png"
LOGO_PATH = ASSETS_DIR / "logo.png"
DATA_DIR = ROOT_DIR / "data" / "json"

POS_ORDER = ["GK", "DEF", "MID", "ATT"]
POS_KEYS = {"GK": "pos_gk", "DEF": "pos_def", "MID": "pos_mid", "ATT": "pos_att"}

# League sort priority for the club selector (lower = first)
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


# =============================================================================
# HELPERS
# =============================================================================

def _img_to_b64(path: Path, mime: str = "image/png") -> str:
    """Read a local image and return an HTML <img> base-64 data-URI."""
    if not path.exists():
        return ""
    b64 = base64.b64encode(path.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


def st_svg(svg_path: Path, width: int = 40):
    """Render an SVG file inline."""
    if not svg_path.exists():
        return
    b64 = base64.b64encode(svg_path.read_bytes()).decode()
    st.markdown(
        f'<img src="data:image/svg+xml;base64,{b64}" width="{width}"/>',
        unsafe_allow_html=True,
    )


TODAY_SEASON = "today"


def _get_available_seasons(lang: str = "en") -> List[str]:
    """Return sorted list of seasons with 'Today' prepended. Supports multi-part files."""
    seasons = []
    for base in list_json_bases("teams_all_*.json"):
        s = base.replace("teams_all_", "")
        if s and s not in seasons:
            seasons.append(s)
    return sorted(seasons, reverse=True)


def _get_clubs_for_season(season: str) -> List[Dict]:
    """Load teams_all_{season}.json sorted by league priority then market value.
    Supports multi-part files when >90MB.

    When *season* is ``"today"``, loads the most recent teams file available.
    """
    if season.lower() == TODAY_SEASON:
        bases = list_json_bases("teams_all_*.json")
        base = bases[-1] if bases else None
    else:
        base = f"teams_all_{season}"

    if base is None:
        return []
    data = load_json(base)
    if data is None or not isinstance(data, list):
        return []
    # Sort: first by league priority, then by total_market_value descending
    data.sort(key=lambda c: (
        LEAGUE_PRIORITY.get((c.get("league") or "").lower(), 99),
        -(c.get("total_market_value") or 0),
    ))
    return data


def _detect_llm_provider(api_key: str) -> str:
    """Guess provider from key prefix."""
    k = (api_key or "").strip()
    if k.startswith("sk-ant-"):
        return "anthropic"
    if k.startswith("sk-"):
        return "openai"
    return "gemini"


def _player_card_html(
    name: str,
    img_url: str,
    detail: str,
    arrow_b64: str = "",
) -> str:
    """Return HTML for one player card (image + name + detail + optional arrow)."""
    img_tag = (
        f'<img src="{img_url}" width="40" height="40" '
        f'style="border-radius:50%;object-fit:cover;background:#222;" '
        f'onerror="this.style.display=\'none\'" />'
        if img_url else
        '<div style="width:40px;height:40px;border-radius:50%;background:#333;"></div>'
    )
    arrow_tag = (
        f'<img src="{arrow_b64}" width="18" height="18" style="margin-left:6px;" />'
        if arrow_b64 else ""
    )
    return (
        f'<div style="display:flex;align-items:center;gap:8px;padding:4px 0;">'
        f'  {img_tag}'
        f'  <div style="flex:1;min-width:0;">'
        f'    <div style="font-weight:600;font-size:0.92rem;white-space:nowrap;'
        f'         overflow:hidden;text-overflow:ellipsis;">{name}{arrow_tag}</div>'
        f'    <div style="font-size:0.78rem;color:#aaa;">{detail}</div>'
        f'  </div>'
        f'</div>'
    )


# =============================================================================
# LANGUAGE HEADER
# =============================================================================

def header_language() -> str:
    if "lang" not in st.session_state:
        st.session_state.lang = "es"

    lang = st.session_state.lang
    c_title, c_es, c_en = st.columns([6.0, 1.6, 1.6], vertical_alignment="center")

    with c_title:
        st.title(t(lang, "title"))

    with c_es:
        st_svg(LANG_DIR / "es.svg", width=40)
        if st.button(t("es", "spanish"), key="btn_lang_es", use_container_width=True):
            st.session_state.lang = "es"
            st.rerun()

    with c_en:
        st_svg(LANG_DIR / "en.svg", width=40)
        if st.button(t("en", "english"), key="btn_lang_en", use_container_width=True):
            st.session_state.lang = "en"
            st.rerun()

    return st.session_state.lang


# =============================================================================
# STEP 1 – SEASON & CLUB
# =============================================================================

def render_season_club(lang: str):
    """Render season + club selectors."""
    seasons = _get_available_seasons()
    if not seasons:
        st.warning(t(lang, "step_loading") + " (no data found)")
        st.stop()

    today_label = t(lang, "today_option")
    display_seasons = [today_label] + seasons
    default_idx = 1 if len(display_seasons) > 1 else 0

    col_season, col_club = st.columns(2)
    with col_season:
        selected = st.selectbox(
            t(lang, "select_season"), options=display_seasons, index=default_idx,
        )
        season = TODAY_SEASON if selected == today_label else selected
    with col_club:
        clubs_data = _get_clubs_for_season(season)
        club_names = [c.get("name", "") for c in clubs_data if c.get("name")]
        club_name = st.selectbox(t(lang, "select_club"), options=club_names)

    return season, club_name, clubs_data


# =============================================================================
# STEP 2 – LOAD TEAM DATA
# =============================================================================

def _preload_team_data(lang: str, club_name: str, season: str):
    """Create a TransferSimulator, run preload_data(), store in session_state."""
    from simulator.transfer_simulator import TransferSimulator

    progress = st.progress(0, text=t(lang, "loading_data"))
    hint = st.empty()
    hint.caption(t(lang, "sim_may_take"))

    def _on_progress(pct: float, key: str):
        icon = "✅" if pct >= 1.0 else "⏳"
        progress.progress(min(pct, 1.0), text=f"{icon} {t(lang, key)}")

    sim = TransferSimulator(
        club_name=club_name,
        season=season,
        transfer_budget=0,
    )
    with st.spinner(""):
        try:
            squad = sim.preload_data(verbose=False, progress_callback=_on_progress)
        except ValueError as exc:
            progress.empty()
            hint.empty()
            st.error(str(exc))
            return

    progress.empty()
    hint.empty()

    # Clear stale sell-selection widget keys
    for pos in POS_ORDER:
        st.session_state.pop(f"sell_{pos}", None)

    st.session_state["preloaded_sim"] = sim
    st.session_state["preloaded_squad"] = squad
    st.session_state["preloaded_club"] = club_name
    st.session_state["preloaded_season"] = season


def _squad_label(p, lang: str) -> str:
    """Build a display label for a player in the multiselect."""
    pos = t(lang, POS_KEYS.get(p.position, "pos_def"))
    mv = format_currency(p.market_value) if p.market_value else "?"
    pv = getattr(p, "predicted_value", None)
    if pv is not None and p.market_value is not None:
        if pv > p.market_value:
            arrow = " ↑"
        elif pv < p.market_value:
            arrow = " ↓"
        else:
            arrow = ""
        return f"{p.name}  ({pos}, {mv}) → {format_currency(pv)} {arrow}"
    return f"{p.name}  ({pos}, {mv})"


# =============================================================================
# STEP 3 – SELECT PLAYERS TO SELL  (recommendations + manual selection)
# =============================================================================

def _compute_sell_recommendations(squad) -> dict:
    """Analyse the squad and return sale recommendations.

    Returns dict with:
        peak_players:    list of players whose predicted_value < market_value
                         (have peaked, expected to decline), sorted by absolute
                         decline descending.
        decline_players: same list as peak_players but may include near-zero
                         deltas that are still negative.  Kept separate so the
                         UI can present two tabs.
    """
    peak = []
    for p in squad:
        mv = p.market_value or 0
        pv = getattr(p, "predicted_value", None)
        if pv is None or mv <= 0:
            continue
        if p.on_loan:
            continue
        delta = mv - pv  # positive means decline
        if delta > 0:
            peak.append((p, delta, delta / mv))
    peak.sort(key=lambda t: t[1], reverse=True)
    return {
        "peak_players": peak,
    }


def _render_sell_recommendations(lang: str, squad) -> set:
    """Render the sale-recommendation panel.  Returns set of player_ids
    that the user chose to auto-select from the recommendations."""
    recs = _compute_sell_recommendations(squad)
    peak = recs["peak_players"]

    auto_ids: set = set()

    st.subheader(t(lang, "sell_recommendations"))
    st.caption(t(lang, "sell_rec_help"))

    # ── Tab 1: peak ──────────────────────────────────────────────────────
    tab_peak, tab_decline = st.tabs([
        t(lang, "sell_rec_peak"),
        t(lang, "sell_rec_decline"),
    ])

    with tab_peak:
        st.caption(t(lang, "sell_rec_peak_desc"))
        if not peak:
            st.info(t(lang, "sell_rec_no_peak"))
        else:
            if st.button(t(lang, "sell_rec_select_all_peak"), key="btn_peak"):
                for p, _, _ in peak:
                    auto_ids.add(p.player_id)

            for p, delta, pct in peak:
                pos = t(lang, POS_KEYS.get(p.position, "pos_def"))
                mv = format_currency(p.market_value)
                pv = format_currency(p.predicted_value)
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(
                        f"**{p.name}** ({pos}, {p.age or '?'}) · {mv} → {pv}"
                    )
                with col2:
                    st.markdown(
                        f"<span style='color:#cc0000'>▼ {format_currency(delta)} "
                        f"({pct:.0%})</span>",
                        unsafe_allow_html=True,
                    )

    # ── Tab 2: decline (top 5 biggest drops) ─────────────────────────────
    with tab_decline:
        st.caption(t(lang, "sell_rec_decline_desc"))
        top_n = peak[:5]
        if not top_n:
            st.info(t(lang, "sell_rec_no_decline"))
        else:
            if st.button(t(lang, "sell_rec_select_all_decline"), key="btn_decline"):
                for p, _, _ in top_n:
                    auto_ids.add(p.player_id)

            for rank, (p, delta, pct) in enumerate(top_n, 1):
                pos = t(lang, POS_KEYS.get(p.position, "pos_def"))
                mv = format_currency(p.market_value)
                pv = format_currency(p.predicted_value)
                st.markdown(
                    f"**{rank}.** {p.name} ({pos}, {p.age or '?'}) · {mv} → {pv} "
                    f"— <span style='color:#cc0000'>▼ {format_currency(delta)} "
                    f"({pct:.0%})</span>",
                    unsafe_allow_html=True,
                )

    return auto_ids


def render_sell_selection(lang: str, squad) -> Optional[List[str]]:
    """Render sale recommendations + multiselects to choose players to sell.

    Returns list of player_id strings, or None if nothing selected.
    """
    # Recommendations panel (before manual selection)
    auto_ids = _render_sell_recommendations(lang, squad)

    st.subheader(t(lang, "select_players_to_sell"))
    st.caption(t(lang, "sell_selection_help"))

    by_pos = {pos: [] for pos in POS_ORDER}
    for p in squad:
        pos = p.position if p.position in by_pos else "DEF"
        by_pos[pos].append(p)
    for pos in by_pos:
        by_pos[pos].sort(key=lambda p: p.market_value or 0, reverse=True)

    # Build label→id maps and compute defaults from recommendations
    selected_ids: list = []
    for pos in POS_ORDER:
        players_in_pos = by_pos[pos]
        if not players_in_pos:
            continue
        options = {_squad_label(p, lang): p.player_id for p in players_in_pos}
        default_labels = [
            lbl for lbl, pid in options.items() if pid in auto_ids
        ]
        chosen = st.multiselect(
            t(lang, POS_KEYS[pos]),
            options=list(options.keys()),
            default=default_labels,
            key=f"sell_{pos}",
        )
        selected_ids.extend(options[label] for label in chosen)

    return selected_ids


# =============================================================================
# STEP 4 – SIGNINGS PER POSITION
# =============================================================================

def _total_combinations(total: int, max_per_pos: int = 3) -> List[List[int]]:
    """Return all 4-element arrays [GK, DEF, MID, ATT] that sum to *total*
    with each element in [0, max_per_pos]."""
    combos = []
    for gk in range(min(total, max_per_pos) + 1):
        for df in range(min(total - gk, max_per_pos) + 1):
            for mid in range(min(total - gk - df, max_per_pos) + 1):
                att = total - gk - df - mid
                if 0 <= att <= max_per_pos:
                    combos.append([gk, df, mid, att])
    return combos


def render_buy_counts(lang: str) -> Dict[str, Tuple[int, int]]:
    """Render exact, range or total inputs for how many players to sign per position.

    Returns dict mapping position -> (min, max).  In exact mode min == max.
    For 'total' mode the key ``_formations`` holds the pre-computed list of
    formation arrays so the caller can pass them directly.
    """
    st.subheader(t(lang, "signings_per_position"))

    mode = st.radio(
        "mode",
        options=["exact", "range", "total"],
        format_func=lambda m: t(lang, f"buy_mode_{m}"),
        horizontal=True,
        key="buy_mode",
        label_visibility="collapsed",
    )

    buy_counts: Dict[str, Tuple[int, int]] = {}

    if mode == "exact":
        st.caption(t(lang, "signings_exact_help"))
        cols = st.columns(len(POS_ORDER))
        for i, pos in enumerate(POS_ORDER):
            with cols[i]:
                n = st.number_input(
                    t(lang, POS_KEYS[pos]),
                    min_value=0,
                    max_value=3,
                    value=1,
                    key=f"buy_exact_{pos}",
                )
                buy_counts[pos] = (n, n)
    elif mode == "range":
        st.caption(t(lang, "signings_range_help"))
        cols = st.columns(len(POS_ORDER))
        for i, pos in enumerate(POS_ORDER):
            with cols[i]:
                st.markdown(f"**{t(lang, POS_KEYS[pos])}**")
                lo = st.number_input(
                    t(lang, "buy_min"),
                    min_value=0,
                    max_value=2,
                    value=0,
                    key=f"buy_min_{pos}",
                )
                hi = st.number_input(
                    t(lang, "buy_max"),
                    min_value=lo,
                    max_value=2,
                    value=max(lo, 2),
                    key=f"buy_max_{pos}",
                )
                buy_counts[pos] = (lo, hi)
    else:
        st.caption(t(lang, "signings_total_help"))
        total = st.number_input(
            t(lang, "total_players"),
            min_value=0,
            max_value=10,
            value=5,
            key="buy_total",
        )
        combos = _total_combinations(total)
        buy_counts["_formations"] = combos

    return buy_counts


# =============================================================================
# STEP 5 – BUDGET
# =============================================================================

def render_budget(lang: str):
    """Render budget inputs. Returns (transfer_budget, unlimited)."""
    st.subheader(t(lang, "budget_title"))
    st.caption(t(lang, "budget_extra_note"))
    col_tb, col_ul = st.columns([3, 1])
    with col_ul:
        st.markdown("<br>", unsafe_allow_html=True)
        unlimited = st.checkbox(t(lang, "unlimited_budget"), value=False)
    with col_tb:
        transfer_budget = st.number_input(
            t(lang, "transfer_budget"), min_value=-2000, max_value=2000, value=0, step=10,
            disabled=unlimited,
        )

    return transfer_budget, unlimited


# =============================================================================
# STEP 6 – SIGNING APPROACH
# =============================================================================

APPROACHES = ["max_value", "young_talents", "veteran_players", "balanced"]
OBJECTIVES = ["smv", "net_benefit", "roi", "value_growth", "growth_pct"]
SIM_SPEEDS = ["local", "fast", "standard"]


def render_approach(lang: str) -> str:
    """Render signing-approach selector. Returns the chosen approach key."""
    st.subheader(t(lang, "approach_title"))

    approach = st.radio(
        "approach",
        options=APPROACHES,
        format_func=lambda a: t(lang, f"approach_{a}"),
        horizontal=True,
        key="approach",
        label_visibility="collapsed",
    )

    st.caption(t(lang, f"approach_{approach}_help"))
    return approach


def render_objective(lang: str) -> str:
    """Render optimisation-objective selector. Returns the chosen objective key."""
    st.subheader(t(lang, "objective_title"))

    objective = st.radio(
        "objective",
        options=OBJECTIVES,
        format_func=lambda o: t(lang, f"objective_{o}"),
        horizontal=True,
        key="objective",
        label_visibility="collapsed",
    )

    st.caption(t(lang, f"objective_{objective}_help"))
    return objective


def render_sim_speed(lang: str) -> str:
    """Render simulation speed selector. Returns the chosen speed key."""
    st.subheader(t(lang, "sim_speed_title"))

    speed = st.radio(
        "sim_speed",
        options=SIM_SPEEDS,
        index=2,
        format_func=lambda s: t(lang, f"sim_speed_{s}"),
        horizontal=True,
        key="sim_speed",
        label_visibility="collapsed",
    )

    st.caption(t(lang, f"sim_speed_{speed}_help"))
    return speed


# =============================================================================
# =============================================================================
# STEP 9 – ADVANCED FILTERS
# =============================================================================

def render_advanced_filters(lang: str, clubs_data: List[Dict]):
    """Render collapsible advanced-filter panel.

    Returns (league_filter, banned_clubs, exclude_top_n, min_market_value, horizon).
    """
    with st.expander(t(lang, "filters_title"), expanded=False):
        # ── League filter ────────────────────────────────────────────────
        all_leagues: Dict[str, str] = {}
        for c in clubs_data:
            lid = c.get("league_id", "") or ""
            lname = c.get("league", "") or lid
            if lid and lid not in all_leagues:
                all_leagues[lid] = lname
        league_options = sorted(all_leagues.items(), key=lambda kv: kv[1])
        selected_leagues = st.multiselect(
            t(lang, "league_filter"),
            options=[lid for lid, _ in league_options],
            format_func=lambda lid: all_leagues.get(lid, lid),
            help=t(lang, "league_filter_help"),
            key="league_filter",
        )
        league_filter = selected_leagues or None

        # ── Banned clubs ──────────────────────────────────────────────────
        banned_text = st.text_input(
            t(lang, "banned_clubs"),
            placeholder=t(lang, "banned_clubs_placeholder"),
            help=t(lang, "banned_clubs_help"),
            key="banned_clubs",
        )
        banned_clubs = (
            [c.strip() for c in banned_text.split(",") if c.strip()]
            if banned_text else None
        )

        # ── Exclude top N ─────────────────────────────────────────────────
        exclude_top_n = st.number_input(
            t(lang, "exclude_top_n"),
            min_value=0, max_value=50, value=0, step=1,
            help=t(lang, "exclude_top_n_help"),
            key="exclude_top_n",
        )

        col1, col2 = st.columns(2)
        with col1:
            # ── Min market value ──────────────────────────────────────────
            min_val = st.number_input(
                t(lang, "min_market_value_title"),
                min_value=0.0, max_value=200.0, value=0.1, step=0.5,
                help=t(lang, "min_market_value_help"),
                key="min_market_value",
            )
            min_market_value = min_val * 1_000_000 if min_val > 0 else None

        with col2:
            # ── Prediction horizon ────────────────────────────────────────
            horizon_labels = {1: t(lang, "horizon_1"), 2: t(lang, "horizon_2"), 3: t(lang, "horizon_3")}
            horizon = st.radio(
                t(lang, "horizon_title"),
                options=[1, 2, 3],
                format_func=lambda h: horizon_labels[h],
                horizontal=True,
                help=t(lang, "horizon_help"),
                key="horizon",
            )

    return league_filter, banned_clubs, exclude_top_n, min_market_value, horizon


# SIMULATION RUNNER (with progress)
# =============================================================================

def run_simulation_with_progress(
    lang: str,
    club_name: str,
    season: str,
    transfer_budget: int,
    unlimited: bool,
    players_to_sell: Optional[List[str]] = None,
    buy_counts: Optional[Dict[str, Tuple[int, int]]] = None,
    approach: str = "max_value",
    objective: str = "smv",
    sim_speed: str = "standard",
    league_filter: Optional[List[str]] = None,
    banned_clubs: Optional[List[str]] = None,
    exclude_top_n: int = 0,
    min_market_value: Optional[float] = None,
    horizon: int = 1,
):
    """Run TransferSimulator.run() while feeding a Streamlit progress bar + spinner."""
    progress = st.progress(0, text=t(lang, "step_loading"))
    hint = st.empty()
    hint.caption(t(lang, "sim_may_take"))

    def _on_progress(pct: float, key: str):
        icon = "✅" if pct >= 1.0 else "⏳"
        progress.progress(min(pct, 1.0), text=f"{icon} {t(lang, key)}")

    sim = st.session_state["preloaded_sim"]
    sim.budget = transfer_budget if not unlimited else 999_999

    with st.spinner(""):
        try:
            result = sim.run(
                verbose=False,
                generate_summary=False,
                progress_callback=_on_progress,
                unlimited_budget=unlimited,
                players_to_sell=players_to_sell,
                buy_counts=buy_counts,
                approach=approach,
                objective=objective,
                sim_speed=sim_speed,
                league_filter=league_filter,
                banned_clubs=banned_clubs,
                exclude_top_n=exclude_top_n,
                min_market_value=min_market_value,
                horizon=horizon,
            )
        except ValueError as exc:
            progress.empty()
            hint.empty()
            st.error(str(exc))
            st.stop()

    hint.empty()
    time.sleep(0.5)
    progress.empty()

    return result


# =============================================================================
# OUTPUT RENDERING
# =============================================================================

def render_results(lang: str, result, clubs_data: List[Dict]):
    """Render the full simulation output."""
    from simulator.transfer_simulator import SoldPlayer

    # Build team→logo lookup
    team_logo: Dict[str, str] = {}
    for c in clubs_data:
        name = c.get("name", "")
        logo = c.get("logo_url", "")
        if name and logo:
            team_logo[name.lower()] = logo

    # Arrow data-URIs
    arrow_down_b64 = _img_to_b64(ARROW_DOWN) if ARROW_DOWN.exists() else ""
    arrow_up_b64 = _img_to_b64(ARROW_UP) if ARROW_UP.exists() else ""

    st.markdown("---")

    # ── Title with club logo ────────────────────────────────────────────────
    club_logo_url = team_logo.get(result.club_name.lower(), "")
    title_html = ""
    if club_logo_url:
        title_html += (
            f'<img src="{club_logo_url}" width="44" '
            f'style="vertical-align:middle;margin-right:10px;object-fit:contain;" />'
        )
    display_season = (
        t(lang, "today_option") if result.season.lower() == TODAY_SEASON
        else result.season
    )
    title_html += (
        f'<span style="font-size:1.6rem;font-weight:700;vertical-align:middle;">'
        f'{t(lang, "simulation_title", club=result.club_name, season=display_season)}'
        f'</span>'
    )
    st.markdown(title_html, unsafe_allow_html=True)

    # ── Budget metrics ──────────────────────────────────────────────────────
    is_unlimited = result.initial_budget >= 999_000
    st.subheader(t(lang, "budget_section"))
    b1, b2, b3 = st.columns(3)
    b1.metric(t(lang, "initial_budget"), "€∞" if is_unlimited else f"€{result.initial_budget}M")
    b2.metric(t(lang, "sales_revenue"), f"+€{result.sales_revenue}M")
    b3.metric(t(lang, "total_budget"), "€∞" if is_unlimited else f"€{result.total_budget}M")

    # ── Sold / Bought columns ───────────────────────────────────────────────
    col_sold, col_bought = st.columns(2)
    
    # -- Sold --
    with col_sold:
        sold_count = sum(1 for sp in result.players_sold if sp.was_sold)
        unsold_count = len(result.players_sold) - sold_count
        header_sold = t(lang, "players_sold")
        if unsold_count:
            header_sold += f"  ({sold_count} ✔, {unsold_count} ✘)"
        st.subheader(header_sold)
        fm = result.formation_needed
        sold_labels = ", ".join(
            f"{t(lang, POS_KEYS[pos])}: {fm[i]}"
            # for i, pos in enumerate(POS_ORDER) if fm[i] > 0
            for i, pos in enumerate(POS_ORDER)
        )
        st.caption(sold_labels)

        for sp in result.players_sold:
            p = sp.player
            mv = format_currency(p.market_value or 0)
            if sp.was_sold:
                detail = f"{t(lang, 'pos_' + (p.position or 'def').lower(), **{})} · {mv} {t(lang, 'to_team', team=sp.destination_team)}"
            else:
                detail = f"{t(lang, 'pos_' + (p.position or 'def').lower(), **{})} · {mv} — {t(lang, 'no_buyer')}"
            html = _player_card_html(
                name=p.name,
                img_url=p.img_url or "",
                detail=detail,
                arrow_b64=arrow_down_b64,
            )
            st.markdown(html, unsafe_allow_html=True)

    # -- Bought --
    with col_bought:
        st.subheader(t(lang, "players_bought"))
        # Compute actual positions from recommended signings
        bought_counts = {pos: 0 for pos in POS_ORDER}
        for p in result.recommended_signings:
            if p.position in bought_counts:
                bought_counts[p.position] += 1
        bought_labels = ", ".join(
            f"{t(lang, POS_KEYS[pos])}: {bought_counts[pos]}"
            # for pos in POS_ORDER if bought_counts[pos] > 0
            for pos in POS_ORDER
        )
        st.caption(bought_labels)

        if not result.recommended_signings:
            st.info(t(lang, "no_signings"))
        else:
            for p in result.recommended_signings:
                mv = format_currency(p.market_value or 0)
                pv = format_currency(p.predicted_value or 0)
                pos_label = t(lang, POS_KEYS.get(p.position, "pos_def"))
                detail = (
                    f"{pos_label} · {mv} → {pv} {t(lang, 'predicted')} · "
                    f"{t(lang, 'from_team', team=p.team or '?')}"
                )
                html = _player_card_html(
                    name=p.name,
                    img_url=p.img_url or "",
                    detail=detail,
                    arrow_b64=arrow_up_b64,
                )
                st.markdown(html, unsafe_allow_html=True)

    # ── Financial summary ───────────────────────────────────────────────────
    st.markdown("---")
    st.subheader(t(lang, "market_info"))

    actual_cost = sum((p.market_value or 0) for p in result.recommended_signings)
    actual_predicted = sum((p.predicted_value or 0) for p in result.recommended_signings)
    remaining = result.total_budget * 1e6 - actual_cost
    net_benefit = actual_predicted - actual_cost

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(t(lang, "total_cost"), format_currency(actual_cost))
    m2.metric(t(lang, "remaining_budget"), "€∞" if is_unlimited else format_currency(remaining))
    m3.metric(t(lang, "predicted_value_1y"), format_currency(actual_predicted))
    # Delta string must start with the sign so Streamlit detects direction
    if net_benefit >= 0:
        net_delta_str = f"+{format_currency(net_benefit)}"
    else:
        net_delta_str = f"-{format_currency(abs(net_benefit))}"
    m4.metric(
        t(lang, "net_benefit"),
        format_currency(net_benefit),
        delta=net_delta_str,
        delta_color="normal",
    )

    # ── Final squad ─────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader(t(lang, "final_squad"))

    sold_ids = {sp.player.player_id for sp in result.players_sold if sp.was_sold}
    remaining_squad = [p for p in result.current_squad if p.player_id not in sold_ids]
    new_ids = {p.player_id for p in result.recommended_signings}
    final_squad = remaining_squad + result.recommended_signings

    # Group by position, sorted by market_value descending
    by_pos: Dict[str, List] = {pos: [] for pos in POS_ORDER}
    for p in final_squad:
        pos = p.position if p.position in by_pos else "DEF"
        by_pos[pos].append(p)
    for pos in by_pos:
        by_pos[pos].sort(key=lambda p: p.market_value or 0, reverse=True)

    # CSS for the "NEW" badge
    st.markdown(
        """
        <style>
        .new-badge {
            display:inline-block; background:#22c55e; color:#fff;
            font-size:0.6rem; font-weight:700; padding:1px 5px;
            border-radius:4px; margin-left:4px; vertical-align:middle;
            letter-spacing:0.5px;
        }
        .squad-card-new {
            border-left: 3px solid #22c55e;
            padding-left: 6px;
            margin-bottom: 2px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    for pos in POS_ORDER:
        players = by_pos[pos]
        if not players:
            continue
        st.markdown(
            f"**{t(lang, POS_KEYS[pos])}** ({len(players)})",
        )
        # Render in rows of 6
        row_size = 6
        for i in range(0, len(players), row_size):
            chunk = players[i : i + row_size]
            cols = st.columns(row_size)
            for j, p in enumerate(chunk):
                with cols[j]:
                    is_new = p.player_id in new_ids
                    if p.img_url:
                        st.image(p.img_url, width=52)
                    else:
                        st.write("")
                    mv_str = format_currency(p.market_value) if p.market_value else ""
                    badge = '<span class="new-badge">NEW</span>' if is_new else ""
                    wrapper_cls = "squad-card-new" if is_new else ""
                    st.markdown(
                        f'<div class="{wrapper_cls}" style="margin-top:-10px;margin-bottom:14px;">'
                        f'<span style="font-size:0.82rem;">{p.name}{badge}</span><br>'
                        f'<span style="font-size:0.75rem;color:#aaa;">{mv_str}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

    return final_squad


# =============================================================================
# AI ANALYSIS SECTION
# =============================================================================

def _xgrowth(p) -> float:
    mv = p.market_value or 1
    pv = getattr(p, "predicted_value", None) or mv
    return (pv / mv) - 1 if mv > 0 else 0.0


def _fair_price(p) -> float:
    return getattr(p, "predicted_value", None) or p.market_value or 0


def _similarity(a, b) -> float:
    if (a.position or "") != (b.position or ""):
        return 0.0
    mv_a, mv_b = a.market_value or 1, b.market_value or 1
    age_a, age_b = a.age or 25, b.age or 25
    xg_a = _xgrowth(a)
    xg_b = _xgrowth(b)
    val_sim = 1 - min(abs(mv_a - mv_b) / max(mv_a, mv_b), 1)
    age_sim = 1 - min(abs(age_a - age_b) / 10, 1)
    xg_sim = 1 - min(abs(xg_a - xg_b) / max(abs(xg_a) + 0.01, abs(xg_b) + 0.01), 1)
    return 0.35 * val_sim + 0.25 * age_sim + 0.40 * xg_sim


def render_player_search(lang: str):
    """Render full-text player search with filters."""
    st.markdown("---")
    st.subheader(t(lang, "search_title"))
    st.caption(t(lang, "search_help"))

    sim = st.session_state.get("preloaded_sim")
    if sim is None:
        return

    col_q, col_pos, col_val_min, col_val_max, col_age_min, col_age_max = st.columns([3, 1, 1, 1, 1, 1])
    with col_q:
        query = st.text_input(t(lang, "search_placeholder"), key="search_q")
    with col_pos:
        pos_filter = st.selectbox(
            t(lang, "search_position"),
            [""] + POS_ORDER,
            format_func=lambda x: t(lang, f"pos_{x.lower()}") if x else "—",
            key="search_pos",
        )
    with col_val_min:
        val_min = st.number_input(t(lang, "search_min_value"), min_value=0.0, value=0.0, step=1.0, key="search_vmin")
    with col_val_max:
        val_max = st.number_input(t(lang, "search_max_value"), min_value=0.0, value=0.0, step=10.0, key="search_vmax")
    with col_age_min:
        age_min = st.number_input(t(lang, "search_min_age"), min_value=0, value=0, step=1, key="search_amin")
    with col_age_max:
        age_max = st.number_input(t(lang, "search_max_age"), min_value=0, value=0, step=1, key="search_amax")

    q_lower = query.strip().lower()
    if not q_lower and not pos_filter and val_min <= 0 and val_max <= 0 and age_min <= 0 and age_max <= 0:
        return

    results = []
    for p in sim.all_players:
        if q_lower and q_lower not in (p.name or "").lower():
            continue
        if pos_filter and (p.position or "") != pos_filter:
            continue
        mv = (p.market_value or 0) / 1_000_000
        if val_min > 0 and mv < val_min:
            continue
        if val_max > 0 and mv > val_max:
            continue
        age = p.age or 0
        if age_min > 0 and age < age_min:
            continue
        if age_max > 0 and age > age_max:
            continue
        results.append(p)

    results.sort(key=lambda p: p.market_value or 0, reverse=True)
    st.markdown(f"**{len(results)}** {t(lang, 'search_results')}")

    if not results:
        st.info(t(lang, "search_no_results"))
        return

    rows = []
    for p in results[:50]:
        pv = getattr(p, "predicted_value", None)
        mv = p.market_value or 0
        xg = ""
        fp = ""
        if pv and mv > 0:
            xg = f"{((pv / mv) - 1):+.1%}"
            fp = format_currency(pv)
        rows.append({
            t(lang, "search_col_name"): p.name,
            t(lang, "search_col_team"): p.team or "?",
            t(lang, "search_col_pos"): p.position or "?",
            t(lang, "search_col_age"): p.age or "?",
            t(lang, "search_col_value"): format_currency(mv),
            t(lang, "search_col_predicted"): format_currency(pv) if pv else "—",
            "xGrowth": xg or "—",
            t(lang, "search_col_fair"): fp or "—",
        })
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_analytics(lang: str, result):
    """Render xGrowth ranking, similar players & fair price section."""
    st.markdown("---")
    st.subheader(t(lang, "analytics_section"))

    sim = st.session_state.get("preloaded_sim")
    if sim is None:
        st.info(t(lang, "no_analytics"))
        return

    all_players = sim.all_players
    club_ids = {p.player_id for p in sim.club_players}
    signing_ids = {p.player_id for p in result.recommended_signings}

    pool = [
        p for p in all_players
        if getattr(p, "predicted_value", None) is not None
        and (p.market_value or 0) > 0
        and not p.on_loan
        and p.player_id not in club_ids
    ]

    # ── Tab 1: xGrowth Ranking ───────────────────────────────────────────
    tab_xg, tab_sim, tab_fair = st.tabs([
        t(lang, "xgrowth_title"),
        t(lang, "similar_title"),
        t(lang, "fair_price_title"),
    ])

    with tab_xg:
        st.caption(t(lang, "xgrowth_help"))
        top = sorted(pool, key=_xgrowth, reverse=True)[:20]
        if not top:
            st.info(t(lang, "no_analytics"))
        else:
            rows = []
            for p in top:
                xg = _xgrowth(p)
                rows.append({
                    t(lang, "xgrowth_col_player"): p.name,
                    "Pos": p.position or "?",
                    t(lang, "xgrowth_col_value"): format_currency(p.market_value),
                    t(lang, "xgrowth_col_predicted"): format_currency(p.predicted_value),
                    "xGrowth": f"{xg:+.1%}",
                    t(lang, "xgrowth_col_fair"): format_currency(_fair_price(p)),
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)

    # ── Tab 2: Similar players ───────────────────────────────────────────
    with tab_sim:
        st.caption(t(lang, "similar_help"))
        for s in result.recommended_signings:
            xg_s = _xgrowth(s)
            st.markdown(
                f"**{s.name}** ({s.position}, {format_currency(s.market_value)}) "
                f"— xGrowth: **{xg_s:+.1%}** — {t(lang, 'fair_price_title')}: **{format_currency(_fair_price(s))}**"
            )
            candidates = [
                p for p in pool
                if p.player_id != s.player_id
                and p.player_id not in signing_ids
                and (p.position or "") == (s.position or "")
            ]
            scored = sorted(
                [(p, _similarity(s, p)) for p in candidates],
                key=lambda x: x[1], reverse=True,
            )[:5]
            if scored:
                sim_rows = []
                for p, sc in scored:
                    sim_rows.append({
                        t(lang, "xgrowth_col_player"): p.name,
                        "Equipo" if lang == "es" else "Team": p.team or "?",
                        t(lang, "xgrowth_col_value"): format_currency(p.market_value),
                        "xGrowth": f"{_xgrowth(p):+.1%}",
                        t(lang, "xgrowth_col_fair"): format_currency(_fair_price(p)),
                        t(lang, "similar_col_similarity"): f"{sc:.0%}",
                    })
                st.dataframe(sim_rows, use_container_width=True, hide_index=True)
            st.markdown("---")

    # ── Tab 3: Fair price ────────────────────────────────────────────────
    with tab_fair:
        st.caption(t(lang, "fair_price_help"))
        if result.recommended_signings:
            rows = []
            for p in result.recommended_signings:
                fp = _fair_price(p)
                mv = p.market_value or 0
                diff = fp - mv
                rows.append({
                    t(lang, "xgrowth_col_player"): p.name,
                    "Pos": p.position or "?",
                    t(lang, "xgrowth_col_value"): format_currency(mv),
                    t(lang, "xgrowth_col_fair"): format_currency(fp),
                    "Δ": format_currency(diff),
                    "xGrowth": f"{_xgrowth(p):+.1%}",
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)


def render_ai_section(lang: str, result):
    """LLM analysis: one summary per language, cached in session_state."""
    st.markdown("---")
    st.subheader(t(lang, "ai_analysis"))

    # Dict of summaries keyed by language: {"es": "...", "en": "..."}
    if "llm_summaries" not in st.session_state:
        st.session_state["llm_summaries"] = {}

    cached = st.session_state["llm_summaries"].get(lang)

    if cached:
        st.markdown(cached)
        return

    st.info(t(lang, "no_ai_key"))
    st.caption(t(lang, "ai_supported_providers"))

    api_key = st.text_input(
        t(lang, "llm_api_key"),
        type="password",
        help=t(lang, "llm_api_key_help"),
    )

    if st.button(t(lang, "generate_analysis"), type="primary", disabled=not api_key):
        provider = _detect_llm_provider(api_key)
        try:
            with st.spinner(t(lang, "generating")):
                summary = result.generate_llm_summary(
                    provider=provider, api_key=api_key, language=lang,
                )
            if summary:
                st.session_state["llm_summaries"][lang] = summary
                st.rerun()
            else:
                st.warning(t(lang, "ai_error"))
        except Exception as exc:
            st.error(f"{t(lang, 'ai_error')} — {exc}")


# =============================================================================
# MAIN
# =============================================================================

def _render_footer(lang: str):
    st.markdown("---")
    st.caption(t(lang, "footer"))
    linkedin_url = (
        "https://www.linkedin.com/in/pablo-roldanp/?locale=es-ES"
        if lang == "es"
        else "https://www.linkedin.com/in/pablo-roldanp/"
    )
    st.caption(t(lang, "created_by", url=linkedin_url))


def main():
    st.set_page_config(
        page_title="Team Transfers Simulator",
        page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else "⚽",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    st.markdown(
        """
        <style>
        .stMarkdown img { vertical-align: middle; }
        section[data-testid="stSidebar"] { display: none; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    lang = header_language()
    st.caption(t(lang, "subtitle"))

    # ── Step 1: Season & Club ────────────────────────────────────────────────
    season, club_name, clubs_data = render_season_club(lang)

    # ── Step 2: Load team data ───────────────────────────────────────────────
    preloaded_club = st.session_state.get("preloaded_club")
    preloaded_season = st.session_state.get("preloaded_season")
    data_loaded = (
        preloaded_club == club_name
        and preloaded_season == season
        and "preloaded_squad" in st.session_state
    )

    if st.button(t(lang, "load_data"), type="secondary", use_container_width=True):
        _preload_team_data(lang, club_name, season)
        st.rerun()

    if not data_loaded:
        st.caption(t(lang, "load_data_hint"))
        _render_footer(lang)
        st.stop()

    squad = st.session_state["preloaded_squad"]
    st.success(f"{t(lang, 'data_loaded')} — {t(lang, 'squad_loaded', count=len(squad))}")

    # ── Player search ────────────────────────────────────────────────────────
    render_player_search(lang)

    # ── Step 3: Select players to sell ───────────────────────────────────────
    players_to_sell = render_sell_selection(lang, squad)

    # ── Step 4: Signings per position ────────────────────────────────────────
    buy_counts = render_buy_counts(lang)

    # ── Step 5: Budget ───────────────────────────────────────────────────────
    tb, unlimited = render_budget(lang)

    # ── Step 6: Signing approach ─────────────────────────────────────────────
    approach = render_approach(lang)

    # ── Step 7: Optimisation objective ────────────────────────────────────────
    objective = render_objective(lang)

    # ── Step 8: Simulation speed ──────────────────────────────────────────────
    sim_speed = render_sim_speed(lang)

    # ── Step 9: Advanced filters ──────────────────────────────────────────────
    league_filter, banned_clubs, exclude_top_n, min_market_value, horizon = (
        render_advanced_filters(lang, clubs_data)
    )

    # ── Step 10: Simulate ────────────────────────────────────────────────────
    if st.button(t(lang, "run_simulation"), type="primary", use_container_width=True):
        result = run_simulation_with_progress(
            lang, club_name, season, tb, unlimited,
            players_to_sell=players_to_sell,
            buy_counts=buy_counts,
            approach=approach,
            objective=objective,
            sim_speed=sim_speed,
            league_filter=league_filter,
            banned_clubs=banned_clubs,
            exclude_top_n=exclude_top_n,
            min_market_value=min_market_value,
            horizon=horizon,
        )
        st.session_state["sim_result"] = result
        st.session_state["sim_clubs_data"] = clubs_data
        st.session_state["llm_summaries"] = {}

    # ── Results ──────────────────────────────────────────────────────────────
    if "sim_result" in st.session_state:
        result = st.session_state["sim_result"]
        clubs_data_saved = st.session_state.get("sim_clubs_data", clubs_data)
        render_results(lang, result, clubs_data_saved)
        render_analytics(lang, result)
        render_ai_section(lang, result)

    _render_footer(lang)


if __name__ == "__main__":
    main()

# Auto-update trigger: 2026-02-19 08:57:52 UTC
