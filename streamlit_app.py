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

    def _on_progress(pct: float, key: str):
        progress.progress(min(pct, 1.0), text=f"⏳ {t(lang, key)}")

    sim = TransferSimulator(
        club_name=club_name,
        season=season,
        transfer_budget=0,
        salary_budget=0,
    )
    try:
        squad = sim.preload_data(verbose=False, progress_callback=_on_progress)
    except ValueError as exc:
        progress.empty()
        st.error(str(exc))
        return

    progress.empty()

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
    return f"{p.name}  ({pos}, {mv})"


# =============================================================================
# STEP 3 – SELECT PLAYERS TO SELL
# =============================================================================

def render_sell_selection(lang: str, squad) -> Optional[List[str]]:
    """Render multiselects to choose which players to sell.

    Returns list of player_id strings, or None if nothing selected.
    """
    st.subheader(t(lang, "select_players_to_sell"))
    st.caption(t(lang, "sell_selection_help"))

    by_pos = {pos: [] for pos in POS_ORDER}
    for p in squad:
        pos = p.position if p.position in by_pos else "DEF"
        by_pos[pos].append(p)
    for pos in by_pos:
        by_pos[pos].sort(key=lambda p: p.market_value or 0, reverse=True)

    selected_ids: list = []
    for pos in POS_ORDER:
        players_in_pos = by_pos[pos]
        if not players_in_pos:
            continue
        options = {_squad_label(p, lang): p.player_id for p in players_in_pos}
        chosen = st.multiselect(
            t(lang, POS_KEYS[pos]),
            options=list(options.keys()),
            key=f"sell_{pos}",
        )
        selected_ids.extend(options[label] for label in chosen)

    return selected_ids if selected_ids else None


# =============================================================================
# STEP 4 – SIGNINGS PER POSITION
# =============================================================================

def render_buy_counts(lang: str) -> Dict[str, int]:
    """Render number inputs for how many players to sign per position (0-3)."""
    st.subheader(t(lang, "signings_per_position"))
    st.caption(t(lang, "signings_per_pos_help"))

    buy_counts: Dict[str, int] = {}
    cols = st.columns(len(POS_ORDER))
    for i, pos in enumerate(POS_ORDER):
        with cols[i]:
            buy_counts[pos] = st.number_input(
                t(lang, POS_KEYS[pos]),
                min_value=0,
                max_value=3,
                value=1,
                key=f"buy_count_{pos}",
            )
    return buy_counts


# =============================================================================
# STEP 5 – BUDGET
# =============================================================================

def render_budget(lang: str):
    """Render budget inputs. Returns (transfer_budget, salary_budget, unlimited)."""
    st.subheader(t(lang, "budget_title"))
    st.caption(t(lang, "budget_extra_note"))
    col_tb, col_sb, col_ul = st.columns([2, 2, 1])
    with col_ul:
        st.markdown("<br>", unsafe_allow_html=True)
        unlimited = st.checkbox(t(lang, "unlimited_budget"), value=False)
    with col_tb:
        transfer_budget = st.number_input(
            t(lang, "transfer_budget"), min_value=-2000, max_value=2000, value=0, step=10,
            disabled=unlimited,
        )
    with col_sb:
        salary_budget = st.number_input(
            t(lang, "salary_budget"), min_value=-2000, max_value=2000, value=0, step=1,
            disabled=unlimited,
        )

    st.caption(t(lang, "budget_first_note"))
    st.caption(t(lang, "budget_note"))
    st.caption(t(lang, "budget_example"))

    return transfer_budget, salary_budget, unlimited


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
    players_to_sell: Optional[List[str]] = None,
    buy_counts: Optional[Dict[str, int]] = None,
):
    """Run TransferSimulator.run() while feeding a Streamlit progress bar + spinner."""
    progress = st.progress(0, text=t(lang, "step_loading"))
    hint = st.empty()
    hint.caption(t(lang, "sim_may_take"))

    def _on_progress(pct: float, key: str):
        icon = "✅" if pct >= 1.0 else "⏳"
        progress.progress(min(pct, 1.0), text=f"{icon} {t(lang, key)}")

    sim = st.session_state["preloaded_sim"]
    sim.budget = min(
        transfer_budget if not unlimited else 999_999,
        (salary_budget if not unlimited else 999_999) * 10,
    )

    with st.spinner(""):
        try:
            result = sim.run(
                verbose=False,
                generate_summary=False,
                progress_callback=_on_progress,
                unlimited_budget=unlimited,
                players_to_sell=players_to_sell,
                buy_counts=buy_counts,
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
            for i, pos in enumerate(POS_ORDER) if fm[i] > 0
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
            for pos in POS_ORDER if bought_counts[pos] > 0
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

    # ── Step 3: Select players to sell ───────────────────────────────────────
    players_to_sell = render_sell_selection(lang, squad)

    # ── Step 4: Signings per position ────────────────────────────────────────
    buy_counts = render_buy_counts(lang)

    # ── Step 5: Budget ───────────────────────────────────────────────────────
    tb, sb, unlimited = render_budget(lang)

    # ── Step 6: Simulate ─────────────────────────────────────────────────────
    if st.button(t(lang, "run_simulation"), type="primary", use_container_width=True):
        result = run_simulation_with_progress(
            lang, club_name, season, tb, sb, unlimited,
            players_to_sell=players_to_sell,
            buy_counts=buy_counts,
        )
        st.session_state["sim_result"] = result
        st.session_state["sim_clubs_data"] = clubs_data
        st.session_state["llm_summaries"] = {}

    # ── Results ──────────────────────────────────────────────────────────────
    if "sim_result" in st.session_state:
        result = st.session_state["sim_result"]
        clubs_data_saved = st.session_state.get("sim_clubs_data", clubs_data)
        render_results(lang, result, clubs_data_saved)
        render_ai_section(lang, result)

    _render_footer(lang)


if __name__ == "__main__":
    main()

# Auto-update trigger: 2026-02-18 00:25:16 UTC
