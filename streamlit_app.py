# streamlit_app.py
"""
Team Analysis AI - Streamlit Application

Football team analysis and transfer strategy simulator with AI integration.
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import pandas as pd
import streamlit as st
from PIL import Image

# Add project root to path
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

from webapp.i18n import t, format_currency, get_position_name, get_transfer_type_name
from player import Player
from team import Team
from scraping.utils.helpers import read_dict_data, DATA_DIR, ensure_data_dir

# =============================================================================
# CONFIG
# =============================================================================
ASSETS_DIR = ROOT_DIR / "assets"
TEAM_LOGOS_DIR = ASSETS_DIR / "team_logos"
LANG_DIR = ASSETS_DIR / "language"

LEAGUES = {
    "LaLiga": "laliga",
    "Premier League": "premier",
    "Serie A": "seriea",
    "Bundesliga": "bundesliga",
    "Ligue 1": "ligue1",
    "Liga Portugal": "liga portugal",
    "Eredivisie": "eredivisie",
    "Segunda División": "segunda",
    "Championship": "championship",
}

# =============================================================================
# HELPERS
# =============================================================================

def st_svg(svg_path: Path, width: int = 40):
    """Render SVG inline."""
    if not svg_path.exists():
        return
    svg_bytes = svg_path.read_bytes()
    b64 = base64.b64encode(svg_bytes).decode("utf-8")
    st.markdown(
        f'<img src="data:image/svg+xml;base64,{b64}" width="{width}"/>',
        unsafe_allow_html=True,
    )


def load_team_logo(team_name: str) -> Optional[Image.Image]:
    """Load team logo image."""
    safe_name = team_name.replace("/", "_").replace(" ", "_")
    candidates = [
        f"{team_name}.png", f"{safe_name}.png",
        f"{team_name}.PNG", f"{safe_name}.PNG",
        f"{team_name}.jpg", f"{safe_name}.jpg",
    ]
    for c in candidates:
        p = TEAM_LOGOS_DIR / c
        if p.exists():
            return Image.open(p).convert("RGBA")
    return None


def get_available_data_files() -> List[Dict[str, Any]]:
    """Get list of available data files."""
    ensure_data_dir()
    files = []
    
    if DATA_DIR.exists():
        for f in DATA_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                file_info = {
                    "name": f.stem,
                    "path": f,
                    "has_team": "team" in data or "teams" in data,
                    "has_players": "players" in data,
                    "has_transfers": "transfers" in data,
                    "has_valuations": "valuations" in data,
                }
                files.append(file_info)
            except Exception:
                continue
    
    return files


def load_data_file(file_path: Path) -> Dict[str, Any]:
    """Load data from JSON file."""
    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def df_to_excel_bytes(df: pd.DataFrame, sheet_name: str = "Sheet1") -> bytes:
    """Convert DataFrame to Excel bytes."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    return output.getvalue()


def players_to_dataframe(players: List[Dict], lang: str) -> pd.DataFrame:
    """Convert players list to DataFrame."""
    rows = []
    for p in players:
        rows.append({
            t(lang, "player_name"): p.get("name", ""),
            t(lang, "position"): get_position_name(lang, p.get("position", "")),
            t(lang, "age"): p.get("age", ""),
            t(lang, "nationality"): p.get("nationality", ""),
            t(lang, "market_value"): format_currency(p.get("current_market_value")),
            t(lang, "shirt_number"): p.get("shirt_number", ""),
        })
    return pd.DataFrame(rows)


def transfers_to_dataframe(transfers: List[Dict], lang: str) -> pd.DataFrame:
    """Convert transfers list to DataFrame."""
    rows = []
    for tr in transfers:
        rows.append({
            t(lang, "transfer_player"): tr.get("player_name", ""),
            t(lang, "from_club"): tr.get("from_club", ""),
            t(lang, "to_club"): tr.get("to_club", ""),
            t(lang, "transfer_fee"): format_currency(tr.get("transfer_fee")),
            t(lang, "transfer_date"): tr.get("transfer_date", ""),
            t(lang, "transfer_type"): get_transfer_type_name(lang, tr.get("transfer_type", "")),
        })
    return pd.DataFrame(rows)


# =============================================================================
# PAGES
# =============================================================================

def page_header(lang: str):
    """Render page header with language selector."""
    c_title, c_es, c_en = st.columns([6.0, 1.5, 1.5], vertical_alignment="center")
    
    with c_title:
        st.title(t(lang, "title"))
        st.caption(t(lang, "subtitle"))
    
    with c_es:
        if LANG_DIR.exists():
            st_svg(LANG_DIR / "es.svg", width=35)
        if st.button(t("es", "spanish"), key="btn_lang_es", use_container_width=True):
            st.session_state.lang = "es"
            st.rerun()
    
    with c_en:
        if LANG_DIR.exists():
            st_svg(LANG_DIR / "en.svg", width=35)
        if st.button(t("en", "english"), key="btn_lang_en", use_container_width=True):
            st.session_state.lang = "en"
            st.rerun()


def page_scraper(lang: str):
    """Scraper page - Extract data from Transfermarkt."""
    st.header(t(lang, "scraper_title"))
    st.write(t(lang, "scraper_description"))
    
    st.divider()
    
    # Input mode
    mode = st.radio(
        t(lang, "input_mode"),
        options=["team", "league"],
        format_func=lambda x: t(lang, f"mode_{x}"),
        horizontal=True,
    )
    
    col1, col2 = st.columns(2)
    
    with col1:
        if mode == "team":
            team_name = st.text_input(
                t(lang, "team_name"),
                placeholder=t(lang, "team_name_placeholder"),
            )
        else:
            league = st.selectbox(
                t(lang, "league_name"),
                options=list(LEAGUES.keys()),
            )
    
    with col2:
        current_year = datetime.now().year
        default_season = f"{current_year-1}-{current_year}"
        season = st.text_input(
            t(lang, "season"),
            value=default_season,
            placeholder=t(lang, "season_placeholder"),
        )
    
    st.subheader(t(lang, "scrape_options"))
    
    col_opt1, col_opt2, col_opt3 = st.columns(3)
    
    with col_opt1:
        include_details = st.checkbox(t(lang, "include_player_details"), value=True)
    with col_opt2:
        include_transfers = st.checkbox(t(lang, "include_transfers"), value=True)
    with col_opt3:
        include_valuations = st.checkbox(t(lang, "include_valuations"), value=False)
    
    st.divider()
    
    # Start button
    if st.button(t(lang, "start_scraping"), type="primary", use_container_width=True):
        
        if mode == "team" and not team_name:
            st.error(f"{t(lang, 'error')}: {t(lang, 'team_name')}")
            return
        
        progress_bar = st.progress(0, text=t(lang, "scraping_progress"))
        status_text = st.empty()
        
        try:
            scraper = TransfermarktScraper(
                season=season,
                delay=2.0,
                verbose=False,
            )
            
            if mode == "team":
                status_text.text(f"{t(lang, 'scraping_team')}: {team_name}")
                
                def progress_cb(current, total):
                    progress_bar.progress(
                        min(1.0, current / total),
                        text=f"{t(lang, 'scraping_progress')}: {current}/{total}"
                    )
                
                data = scraper.scrape_team_full(
                    team_name=team_name,
                    include_player_details=include_details,
                    include_transfers=include_transfers,
                    include_valuations=include_valuations,
                    progress_cb=progress_cb,
                )
            else:
                league_code = LEAGUES[league]
                
                def progress_cb(current, total, team):
                    progress_bar.progress(
                        min(1.0, current / total),
                        text=f"{t(lang, 'scraping_team')}: {team} ({current}/{total})"
                    )
                
                data = scraper.scrape_league_full(
                    league=league_code,
                    include_player_details=include_details,
                    include_transfers=include_transfers,
                    include_valuations=include_valuations,
                    progress_cb=progress_cb,
                )
            
            # Save results
            scraper.save_results(data)
            
            progress_bar.progress(1.0, text=t(lang, "scraping_complete"))
            st.success(t(lang, "scraping_complete"))
            
            # Show summary
            if mode == "team" and data.get("team"):
                team = data["team"]
                st.subheader(team.name if hasattr(team, "name") else team.get("name", ""))
                
                col_s1, col_s2, col_s3 = st.columns(3)
                with col_s1:
                    st.metric(t(lang, "squad_size"), len(data.get("players", [])))
                with col_s2:
                    st.metric(t(lang, "arrivals"), len(data.get("arrivals", [])))
                with col_s3:
                    st.metric(t(lang, "departures"), len(data.get("departures", [])))
            
            elif mode == "league" and data.get("teams"):
                st.metric(f"{t(lang, 'squad_size')} ({league})", len(data["teams"]))
            
        except Exception as e:
            st.error(f"{t(lang, 'scraping_error')}: {str(e)}")


def page_team_analysis(lang: str):
    """Team analysis page."""
    st.header(t(lang, "analysis_title"))
    st.write(t(lang, "analysis_description"))
    
    # Get available data files
    data_files = get_available_data_files()
    
    if not data_files:
        st.warning(t(lang, "no_data"))
        return
    
    # Filter files with player data
    player_files = [f for f in data_files if f["has_players"]]
    
    if not player_files:
        st.warning(t(lang, "no_data"))
        return
    
    # Team selector
    file_names = [f["name"] for f in player_files]
    selected_file = st.selectbox(
        t(lang, "select_team"),
        options=file_names,
    )
    
    if not selected_file:
        return
    
    # Load data
    file_info = next(f for f in player_files if f["name"] == selected_file)
    data = load_data_file(file_info["path"])
    
    if not data:
        st.error(t(lang, "error"))
        return
    
    st.divider()
    
    # Team overview
    players = data.get("players", [])
    transfers = data.get("transfers", [])
    
    if not players:
        st.warning(t(lang, "no_results"))
        return
    
    # Metrics
    st.subheader(t(lang, "team_overview"))
    
    total_value = sum(p.get("current_market_value", 0) or 0 for p in players)
    ages = [p.get("age") for p in players if p.get("age")]
    avg_age = sum(ages) / len(ages) if ages else 0
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric(t(lang, "squad_size"), len(players))
    with col2:
        st.metric(t(lang, "squad_value"), format_currency(total_value))
    with col3:
        st.metric(t(lang, "average_age"), f"{avg_age:.1f}")
    
    st.divider()
    
    # Tabs
    tab_squad, tab_charts, tab_transfers = st.tabs([
        t(lang, "squad_list"),
        t(lang, "chart_value_by_position"),
        t(lang, "recent_transfers"),
    ])
    
    with tab_squad:
        # Squad table
        df = players_to_dataframe(players, lang)
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Download buttons
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button(
                t(lang, "btn_download_csv"),
                data=df.to_csv(index=False).encode("utf-8"),
                file_name=f"{selected_file}_players.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with col_dl2:
            st.download_button(
                t(lang, "btn_download_excel"),
                data=df_to_excel_bytes(df, "Players"),
                file_name=f"{selected_file}_players.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
    
    with tab_charts:
        # Position distribution
        positions = [p.get("position", "N/A") for p in players]
        pos_counts = pd.Series(positions).value_counts()
        
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            st.subheader(t(lang, "position_distribution"))
            st.bar_chart(pos_counts)
        
        with col_chart2:
            st.subheader(t(lang, "chart_age_distribution"))
            if ages:
                age_df = pd.DataFrame({"Age": ages})
                st.bar_chart(age_df["Age"].value_counts().sort_index())
        
        # Value by position
        st.subheader(t(lang, "chart_value_by_position"))
        value_by_pos = {}
        for p in players:
            pos = p.get("position", "N/A")
            val = p.get("current_market_value", 0) or 0
            value_by_pos[pos] = value_by_pos.get(pos, 0) + val
        
        if value_by_pos:
            value_df = pd.DataFrame([
                {"Position": k, "Value (M€)": v / 1_000_000}
                for k, v in value_by_pos.items()
            ])
            st.bar_chart(value_df.set_index("Position"))
        
        # Top valued players
        st.subheader(t(lang, "top_valued_players"))
        sorted_players = sorted(
            players,
            key=lambda x: x.get("current_market_value", 0) or 0,
            reverse=True
        )[:10]
        
        top_df = pd.DataFrame([
            {
                t(lang, "player_name"): p.get("name", ""),
                t(lang, "position"): p.get("position", ""),
                t(lang, "market_value"): format_currency(p.get("current_market_value")),
            }
            for p in sorted_players
        ])
        st.dataframe(top_df, use_container_width=True, hide_index=True)
    
    with tab_transfers:
        if transfers:
            df_transfers = transfers_to_dataframe(transfers, lang)
            st.dataframe(df_transfers, use_container_width=True, hide_index=True)
            
            # Transfer balance
            total_in = sum(
                t.get("transfer_fee", 0) or 0
                for t in transfers
                if t.get("transfer_type") != "loan"
            )
            st.metric(
                t(lang, "transfer_balance"),
                format_currency(total_in)
            )
        else:
            st.info(t(lang, "no_results"))


def page_simulator(lang: str):
    """Transfer strategy simulator page."""
    st.header(t(lang, "simulator_title"))
    st.write(t(lang, "simulator_description"))
    
    st.divider()
    
    # Inputs
    col1, col2 = st.columns(2)
    
    with col1:
        club_name = st.text_input(
            t(lang, "club_name"),
            placeholder=t(lang, "team_name_placeholder"),
        )
        transfer_budget = st.number_input(
            t(lang, "transfer_budget") + " (€M)",
            min_value=0,
            max_value=1000,
            value=100,
            step=10,
        )
    
    with col2:
        current_year = datetime.now().year
        starting_season = st.selectbox(
            t(lang, "starting_season"),
            options=[f"{y}-{y+1}" for y in range(current_year-5, current_year+1)],
            index=5,
        )
        salary_budget = st.number_input(
            t(lang, "salary_budget") + " (€M)",
            min_value=0,
            max_value=2000,
            value=300,
            step=50,
        )
    
    st.divider()
    
    # Load team data if available
    data_files = get_available_data_files()
    team_files = [f for f in data_files if f["has_players"]]
    
    selected_data = None
    if team_files and club_name:
        matching = [f for f in team_files if club_name.lower() in f["name"].lower()]
        if matching:
            selected_data = load_data_file(matching[0]["path"])
    
    # Simulation button
    if st.button(t(lang, "run_simulation"), type="primary", use_container_width=True):
        
        if not club_name:
            st.error(f"{t(lang, 'error')}: {t(lang, 'club_name')}")
            return
        
        with st.spinner(t(lang, "loading")):
            # Mock simulation logic
            st.subheader(t(lang, "simulation_results"))
            
            # If we have real data, use it
            if selected_data and selected_data.get("players"):
                players = selected_data["players"]
                total_value = sum(p.get("current_market_value", 0) or 0 for p in players)
                
                # Simple mock: buy young players, sell old ones
                young_players = [p for p in players if (p.get("age") or 30) < 25]
                old_players = [p for p in players if (p.get("age") or 0) > 30]
                
                st.subheader(t(lang, "season_summary") + f" {starting_season}")
                
                col_r1, col_r2, col_r3 = st.columns(3)
                
                with col_r1:
                    st.metric(t(lang, "squad_size"), len(players))
                with col_r2:
                    st.metric(t(lang, "squad_valuation"), format_currency(total_value))
                with col_r3:
                    potential_sales = sum(p.get("current_market_value", 0) or 0 for p in old_players[:3])
                    net = transfer_budget * 1_000_000 - potential_sales
                    st.metric(t(lang, "net_benefit"), format_currency(abs(net)))
                
                # Suggested sales
                st.subheader(t(lang, "players_sold") + " (sugeridos)")
                if old_players:
                    sales_df = pd.DataFrame([
                        {
                            t(lang, "player_name"): p.get("name", ""),
                            t(lang, "age"): p.get("age", ""),
                            t(lang, "market_value"): format_currency(p.get("current_market_value")),
                        }
                        for p in old_players[:5]
                    ])
                    st.dataframe(sales_df, use_container_width=True, hide_index=True)
                
                # Young talents to keep
                st.subheader(t(lang, "current_squad") + " (jovenes a mantener)")
                if young_players:
                    keep_df = pd.DataFrame([
                        {
                            t(lang, "player_name"): p.get("name", ""),
                            t(lang, "age"): p.get("age", ""),
                            t(lang, "position"): p.get("position", ""),
                            t(lang, "market_value"): format_currency(p.get("current_market_value")),
                        }
                        for p in sorted(young_players, key=lambda x: x.get("current_market_value", 0) or 0, reverse=True)[:10]
                    ])
                    st.dataframe(keep_df, use_container_width=True, hide_index=True)
            
            else:
                # No data - show placeholder
                st.info(t(lang, "no_data"))
                
                st.write("""
                **Mock Simulation Results:**
                
                This is a simplified simulation. With real team data:
                - AI would analyze squad weaknesses
                - Suggest optimal transfers within budget
                - Project value changes over seasons
                - Generate natural language summaries
                """)
            
            # AI Summary section
            st.divider()
            st.subheader(t(lang, "ai_summary"))
            
            if st.button(t(lang, "generate_summary"), use_container_width=True):
                with st.spinner(t(lang, "loading_ai")):
                    # Mock AI response
                    if lang == "es":
                        summary = f"""
                        **Análisis de la temporada {starting_season} para {club_name}:**
                        
                        Con un presupuesto de fichajes de €{transfer_budget}M y un presupuesto salarial de €{salary_budget}M, 
                        el club tiene margen para realizar movimientos estratégicos.
                        
                        **Recomendaciones:**
                        - Priorizar la contratación de jugadores sub-23 con alto potencial
                        - Considerar ventas de jugadores mayores de 30 años con contratos largos
                        - Invertir en posiciones clave según las debilidades del equipo
                        
                        **Proyección:** Con una gestión eficiente, el valor de la plantilla podría aumentar 
                        un 15-20% en las próximas 2-3 temporadas.
                        """
                    else:
                        summary = f"""
                        **Season {starting_season} Analysis for {club_name}:**
                        
                        With a transfer budget of €{transfer_budget}M and a salary budget of €{salary_budget}M, 
                        the club has room for strategic moves.
                        
                        **Recommendations:**
                        - Prioritize signing U-23 players with high potential
                        - Consider selling players over 30 with long contracts
                        - Invest in key positions based on squad weaknesses
                        
                        **Projection:** With efficient management, squad value could increase 
                        by 15-20% over the next 2-3 seasons.
                        """
                    
                    st.markdown(summary)


def page_about(lang: str):
    """About page."""
    st.header(t(lang, "about_title"))
    st.write(t(lang, "about_description"))
    
    st.divider()
    
    st.subheader(t(lang, "about_features"))
    
    features = [
        t(lang, "about_feature_1"),
        t(lang, "about_feature_2"),
        t(lang, "about_feature_3"),
        t(lang, "about_feature_4"),
    ]
    
    for f in features:
        st.write(f"- {f}")
    
    st.divider()
    
    st.subheader(t(lang, "about_tech"))
    
    tech = [
        "**Python 3.10+**",
        "**Streamlit** - Web framework",
        "**Pandas** - Data manipulation",
        "**BeautifulSoup4** - Web scraping",
        "**Matplotlib** - Visualizations",
    ]
    
    for tech_item in tech:
        st.write(f"- {tech_item}")
    
    st.divider()
    
    st.subheader(t(lang, "about_source"))
    st.write("[GitHub Repository](https://github.com/pabloroldan98/team-analysis-ai)")
    
    st.divider()
    
    st.caption(t(lang, "footer_data_source"))
    st.caption(t(lang, "footer_disclaimer"))


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main application entry point."""
    st.set_page_config(
        page_title="Team Analysis AI",
        page_icon="⚽",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    # Ensure directories exist
    ensure_data_dir()
    TEAM_LOGOS_DIR.mkdir(parents=True, exist_ok=True)
    LANG_DIR.mkdir(parents=True, exist_ok=True)
    
    # Initialize language
    if "lang" not in st.session_state:
        st.session_state.lang = "es"
    
    lang = st.session_state.lang
    
    # Sidebar navigation
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/football2--v1.png", width=80)
        st.title("Team Analysis AI")
        
        pages = {
            "nav_scraper": "🔍 " + t(lang, "nav_scraper"),
            "nav_team_analysis": "📊 " + t(lang, "nav_team_analysis"),
            "nav_simulator": "🎮 " + t(lang, "nav_simulator"),
            "nav_about": "ℹ️ " + t(lang, "nav_about"),
        }
        
        selected_page = st.radio(
            t(lang, "language"),
            options=list(pages.keys()),
            format_func=lambda x: pages[x],
            label_visibility="collapsed",
        )
        
        st.divider()
        
        # Language buttons in sidebar
        col_es, col_en = st.columns(2)
        with col_es:
            if st.button("🇪🇸 ES", use_container_width=True, 
                        type="primary" if lang == "es" else "secondary"):
                st.session_state.lang = "es"
                st.rerun()
        with col_en:
            if st.button("🇬🇧 EN", use_container_width=True,
                        type="primary" if lang == "en" else "secondary"):
                st.session_state.lang = "en"
                st.rerun()
    
    # Render selected page
    if selected_page == "nav_scraper":
        page_scraper(lang)
    elif selected_page == "nav_team_analysis":
        page_team_analysis(lang)
    elif selected_page == "nav_simulator":
        page_simulator(lang)
    elif selected_page == "nav_about":
        page_about(lang)


if __name__ == "__main__":
    main()
