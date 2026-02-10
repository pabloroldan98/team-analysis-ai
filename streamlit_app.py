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
from typing import Dict, List, Optional

import streamlit as st

# ── project root on sys.path ────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

from webapp.i18n import t, format_currency

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


def _get_available_seasons() -> List[str]:
    """Return sorted list of seasons for which teams_all_*.json exists."""
    if not DATA_DIR.exists():
        return []
    seasons = set()
    for f in DATA_DIR.glob("teams_all_*.json"):
        if "_OLD" not in f.name:
            s = f.stem.replace("teams_all_", "")
            seasons.add(s)
    return sorted(seasons, reverse=True)


def _get_clubs_for_season(season: str) -> List[Dict]:
    """Load teams_all_{season}.json sorted by league priority then market value."""
    fp = DATA_DIR / f"teams_all_{season}.json"
    if not fp.exists():
        return []
    with open(fp, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
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
# INPUT FORM
# =============================================================================

def render_inputs(lang: str):
    """Render season / club / budget inputs and return them."""
    seasons = _get_available_seasons()
    if not seasons:
        st.warning(t(lang, "step_loading") + " (no data found)")
        st.stop()

    col_season, col_club = st.columns(2)
    with col_season:
        season = st.selectbox(t(lang, "select_season"), options=seasons, index=0)
    with col_club:
        clubs_data = _get_clubs_for_season(season)
        club_names = [c.get("name", "") for c in clubs_data if c.get("name")]
        club_name = st.selectbox(t(lang, "select_club"), options=club_names)

    col_tb, col_sb, col_ul = st.columns([2, 2, 1])
    with col_ul:
        st.markdown("<br>", unsafe_allow_html=True)  # vertical align
        unlimited = st.checkbox(t(lang, "unlimited_budget"), value=False)
    with col_tb:
        transfer_budget = st.number_input(
            t(lang, "transfer_budget"), min_value=0, max_value=2000, value=100, step=10,
            disabled=unlimited,
        )
    with col_sb:
        salary_budget = st.number_input(
            t(lang, "salary_budget"), min_value=0, max_value=2000, value=50, step=10,
            disabled=unlimited,
        )

    st.caption(t(lang, "budget_first_note"))
    st.caption(t(lang, "budget_note"))

    return season, club_name, transfer_budget, salary_budget, unlimited, clubs_data


# =============================================================================
# SIMULATION RUNNER (with progress)
# =============================================================================

def run_simulation_with_progress(
    lang: str,
    club_name: str,
    season: str,
    transfer_budget: int,
    salary_budget: int,
    unlimited: bool,
):
    """Run TransferSimulator.run() while feeding a Streamlit progress bar + spinner."""
    from simulator.transfer_simulator import TransferSimulator, TransferResult

    progress = st.progress(0, text=t(lang, "step_loading"))
    hint = st.empty()
    hint.caption(t(lang, "sim_may_take"))

    def _step(pct: float, key: str):
        progress.progress(min(pct, 1.0), text=f"⏳ {t(lang, key)}")

    with st.spinner(""):
        # 1. Load data  (step 1/7 ≈ 14%)
        _step(0.05, "step_loading")
        sim = TransferSimulator(
            club_name=club_name,
            season=season,
            transfer_budget=transfer_budget if not unlimited else 999_999,
            salary_budget=salary_budget if not unlimited else 999_999,
        )
        players_dict = sim._load_players_for_season()
        valuations = sim._load_valuations_for_season()

        # 2. Update data  (step 2/7 ≈ 28%)
        _step(0.20, "step_team")
        all_players = sim._update_players_with_valuations(players_dict, valuations)
        sim.all_players = all_players

        # 3. Club players  (step 3/7 ≈ 42%)
        _step(0.35, "step_team_values")
        club_players = sim._get_club_players(all_players)
        if not club_players:
            progress.empty()
            st.error(f"No players found for **{club_name}** in season **{season}**.")
            st.stop()

        # 4. Team market values + sell phase  (step 4/7 ≈ 56%)
        _step(0.55, "step_selling")
        sim.team_market_values = sim._calculate_team_market_values(all_players)
        sold_players, formation_needed = sim._sell_random_players(club_players)
        actually_sold = [sp for sp in sold_players if sp.was_sold]
        sales_revenue = sum((sp.player.market_value or 0) for sp in actually_sold) / 1_000_000
        total_budget = sim.budget + int(sales_revenue)

        # 5. Predict values  (step 5/7 ≈ 70%)
        _step(0.70, "step_predicting")
        sold_player_ids = {sp.player.player_id for sp in sold_players}
        available_players = sim._get_available_players(all_players, club_players)
        available_players = [p for p in available_players if p.player_id not in sold_player_ids]
        available_players = sim._predict_values(available_players, verbose=False)

        # 6. Knapsack optimisation  (step 6/7 ≈ 84%)
        _step(0.85, "step_knapsack")
        from simulator.knapsack_solver import best_full_teams

        gk_n, def_n, mid_n, att_n = formation_needed
        custom_formation = (
            [[gk_n, def_n, mid_n, att_n]] if gk_n > 0
            else [[def_n, mid_n, att_n]]
        )
        results = best_full_teams(
            available_players,
            formations=custom_formation,
            budget=total_budget * 1_000_000,
            use_predicted_value=True,
            verbose=0,
            unlimited_budget=unlimited,
        )

        recommended_signings = []
        recommended_formation = []
        if results:
            recommended_formation, _, recommended_signings = results[0]

        # 7. Build result  (step 7/7 ≈ 100%)
        result = TransferResult(
            club_name=club_name,
            season=season,
            initial_budget=sim.budget,
            sales_revenue=int(sales_revenue),
            total_budget=total_budget,
            players_sold=sold_players,
            formation_needed=formation_needed,
            recommended_signings=recommended_signings,
            recommended_formation=recommended_formation,
            total_signing_cost=int(sum((p.market_value or 0) for p in recommended_signings) / 1e6),
            total_predicted_value=0.0,
            current_squad=club_players,
        )

    progress.progress(1.0, text=f"✅ {t(lang, 'step_done')}")
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
    title_html += (
        f'<span style="font-size:1.6rem;font-weight:700;vertical-align:middle;">'
        f'{t(lang, "simulation_title", club=result.club_name, season=result.season)}'
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
        fm = result.formation_needed
        pos_labels = ", ".join(
            f"{t(lang, POS_KEYS[pos])}: {fm[i]}"
            for i, pos in enumerate(POS_ORDER) if fm[i] > 0
        )
        st.subheader(t(lang, "players_bought"))
        st.caption(pos_labels)

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
    m4.metric(
        t(lang, "net_benefit"),
        format_currency(net_benefit),
        delta=format_currency(net_benefit),
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
                        f'<div class="{wrapper_cls}">'
                        f'<span style="font-size:0.82rem;">{p.name}{badge}</span><br>'
                        f'<span style="font-size:0.75rem;color:#aaa;">{mv_str}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

    return final_squad


# =============================================================================
# AI ANALYSIS SECTION
# =============================================================================

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
        with st.spinner(t(lang, "generating")):
            summary = result.generate_llm_summary(
                provider=provider, api_key=api_key, language=lang,
            )
        if summary:
            st.session_state["llm_summaries"][lang] = summary
            st.rerun()
        else:
            st.warning(t(lang, "ai_error"))


# =============================================================================
# MAIN
# =============================================================================

def main():
    st.set_page_config(
        page_title="Team Transfers Simulator",
        page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else "⚽",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    # Inject compact CSS
    st.markdown(
        """
        <style>
        /* tighter player cards */
        .stMarkdown img { vertical-align: middle; }
        section[data-testid="stSidebar"] { display: none; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    lang = header_language()

    st.caption(t(lang, "subtitle"))

    # ── Inputs ──────────────────────────────────────────────────────────────
    season, club_name, tb, sb, unlimited, clubs_data = render_inputs(lang)

    # ── Simulate button ─────────────────────────────────────────────────────
    if st.button(t(lang, "run_simulation"), type="primary", use_container_width=True):
        result = run_simulation_with_progress(lang, club_name, season, tb, sb, unlimited)
        st.session_state["sim_result"] = result
        st.session_state["sim_clubs_data"] = clubs_data
        st.session_state["llm_summaries"] = {}  # reset AI cache for new simulation

    # ── Results (persisted in session_state) ────────────────────────────────
    if "sim_result" in st.session_state:
        result = st.session_state["sim_result"]
        clubs_data_saved = st.session_state.get("sim_clubs_data", clubs_data)
        render_results(lang, result, clubs_data_saved)
        render_ai_section(lang, result)

    # ── Footer ──────────────────────────────────────────────────────────────
    st.markdown("---")
    st.caption(t(lang, "footer"))


if __name__ == "__main__":
    main()
