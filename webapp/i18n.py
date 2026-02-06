# webapp/i18n.py
"""
Internationalization module for team-analysis-ai
Supports Spanish and English
"""

TEXT = {
    "es": {
        # General
        "title": "Simulador de Estrategias de Fichajes",
        "subtitle": "Analiza equipos, jugadores y simula estrategias de fichajes con IA",
        "language": "Idioma",
        "spanish": "Español",
        "english": "English",
        
        # Navigation
        "nav_home": "Inicio",
        "nav_scraper": "Extraer Datos",
        "nav_team_analysis": "Análisis de Equipo",
        "nav_simulator": "Simulador",
        "nav_about": "Acerca de",
        
        # Scraper page
        "scraper_title": "Extractor de Datos de Transfermarkt",
        "scraper_description": "Extrae información de equipos, jugadores, transferencias y valoraciones desde Transfermarkt.",
        "input_mode": "Modo de entrada",
        "mode_team": "Equipo individual",
        "mode_league": "Liga completa",
        "team_name": "Nombre del equipo",
        "team_name_placeholder": "Ej: Real Madrid, Barcelona, Manchester United...",
        "league_name": "Liga",
        "season": "Temporada",
        "season_placeholder": "Ej: 2024-2025",
        "scrape_options": "Opciones de extracción",
        "include_player_details": "Incluir detalles de jugadores",
        "include_transfers": "Incluir historial de transferencias",
        "include_valuations": "Incluir historial de valoraciones",
        "start_scraping": "Iniciar extracción",
        "scraping_progress": "Progreso de extracción",
        "scraping_team": "Extrayendo equipo",
        "scraping_complete": "Extracción completada",
        "scraping_error": "Error durante la extracción",
        
        # Team analysis page
        "analysis_title": "Análisis de Equipo",
        "analysis_description": "Explora los datos del equipo, plantilla, y valoraciones.",
        "select_team": "Seleccionar equipo",
        "no_data": "No hay datos disponibles. Primero extrae datos de un equipo.",
        "team_overview": "Resumen del equipo",
        "squad_list": "Plantilla",
        "squad_value": "Valor de la plantilla",
        "average_age": "Edad media",
        "squad_size": "Tamaño de plantilla",
        "foreigners": "Extranjeros",
        "national_players": "Jugadores internacionales",
        "position_distribution": "Distribución por posición",
        "top_valued_players": "Jugadores más valiosos",
        "recent_transfers": "Transferencias recientes",
        "arrivals": "Llegadas",
        "departures": "Salidas",
        "transfer_balance": "Balance de transferencias",
        "value_evolution": "Evolución de valoración",
        
        # Player table headers
        "player_name": "Nombre",
        "position": "Posición",
        "age": "Edad",
        "nationality": "Nacionalidad",
        "market_value": "Valor de mercado",
        "contract_expires_date": "Fin de contrato",
        "shirt_number": "Dorsal",
        "preferred_foot": "Pie preferido",
        "height": "Altura",
        
        # Transfer table headers
        "transfer_player": "Jugador",
        "from_club": "Desde",
        "to_club": "Hacia",
        "transfer_fee": "Coste",
        "transfer_date": "Fecha",
        "transfer_type": "Tipo",
        
        # Simulator page
        "simulator_title": "Simulador de Estrategias de Fichajes",
        "simulator_description": "Simula diferentes estrategias de fichajes y analiza el impacto en tu equipo.",
        "club_name": "Nombre del club",
        "starting_season": "Temporada inicial",
        "transfer_budget": "Presupuesto de fichajes",
        "salary_budget": "Presupuesto salarial",
        "run_simulation": "Ejecutar simulación",
        "simulation_results": "Resultados de la simulación",
        "season_summary": "Resumen de la temporada",
        "players_bought": "Jugadores fichados",
        "players_sold": "Jugadores vendidos",
        "current_squad": "Plantilla actual",
        "squad_valuation": "Valoración de la plantilla",
        "net_benefit": "Beneficio neto",
        "ai_summary": "Resumen generado por IA",
        "generate_summary": "Generar resumen con IA",
        "loading_ai": "Generando resumen...",
        
        # Charts
        "chart_value_by_position": "Valor por posición",
        "chart_age_distribution": "Distribución de edades",
        "chart_value_evolution": "Evolución del valor",
        "chart_transfer_timeline": "Línea temporal de transferencias",
        
        # Buttons
        "btn_download_csv": "Descargar CSV",
        "btn_download_json": "Descargar JSON",
        "btn_download_excel": "Descargar Excel",
        "btn_refresh": "Actualizar",
        "btn_reset": "Reiniciar",
        "btn_apply": "Aplicar",
        "btn_cancel": "Cancelar",
        
        # Messages
        "loading": "Cargando...",
        "success": "Éxito",
        "error": "Error",
        "warning": "Advertencia",
        "info": "Información",
        "no_results": "Sin resultados",
        "confirm_action": "¿Confirmar acción?",
        
        # Positions
        "pos_gk": "Portero",
        "pos_def": "Defensa",
        "pos_mid": "Centrocampista",
        "pos_att": "Delantero",
        
        # Transfer types
        "type_purchase": "Compra",
        "type_loan": "Cesión",
        "type_free": "Libre",
        "type_loan_return": "Fin de cesión",
        
        # About page
        "about_title": "Acerca de",
        "about_description": "Team Analysis AI es una herramienta de análisis de equipos de fútbol con integración de IA.",
        "about_features": "Características",
        "about_feature_1": "Extracción de datos de Transfermarkt",
        "about_feature_2": "Análisis detallado de plantillas",
        "about_feature_3": "Simulación de estrategias de fichajes",
        "about_feature_4": "Resúmenes generados por IA",
        "about_tech": "Tecnologías utilizadas",
        "about_source": "Código fuente",
        "about_author": "Desarrollado por",
        
        # Footer
        "footer_data_source": "Datos extraídos de Transfermarkt",
        "footer_disclaimer": "Esta herramienta es solo para fines educativos y de análisis.",
        
        # Advice
        "advice_click_twice": "Aviso: algunas veces hay que pulsar los botones más de una vez.",
    },
    "en": {
        # General
        "title": "Transfer Strategies Simulator",
        "subtitle": "Analyze teams, players and simulate transfer strategies with AI",
        "language": "Language",
        "spanish": "Español",
        "english": "English",
        
        # Navigation
        "nav_home": "Home",
        "nav_scraper": "Extract Data",
        "nav_team_analysis": "Team Analysis",
        "nav_simulator": "Simulator",
        "nav_about": "About",
        
        # Scraper page
        "scraper_title": "Transfermarkt Data Extractor",
        "scraper_description": "Extract team, player, transfer and valuation data from Transfermarkt.",
        "input_mode": "Input mode",
        "mode_team": "Single team",
        "mode_league": "Full league",
        "team_name": "Team name",
        "team_name_placeholder": "E.g.: Real Madrid, Barcelona, Manchester United...",
        "league_name": "League",
        "season": "Season",
        "season_placeholder": "E.g.: 2024-2025",
        "scrape_options": "Scraping options",
        "include_player_details": "Include player details",
        "include_transfers": "Include transfer history",
        "include_valuations": "Include valuation history",
        "start_scraping": "Start extraction",
        "scraping_progress": "Extraction progress",
        "scraping_team": "Extracting team",
        "scraping_complete": "Extraction completed",
        "scraping_error": "Error during extraction",
        
        # Team analysis page
        "analysis_title": "Team Analysis",
        "analysis_description": "Explore team data, squad, and valuations.",
        "select_team": "Select team",
        "no_data": "No data available. First extract data from a team.",
        "team_overview": "Team overview",
        "squad_list": "Squad",
        "squad_value": "Squad value",
        "average_age": "Average age",
        "squad_size": "Squad size",
        "foreigners": "Foreigners",
        "national_players": "International players",
        "position_distribution": "Position distribution",
        "top_valued_players": "Most valuable players",
        "recent_transfers": "Recent transfers",
        "arrivals": "Arrivals",
        "departures": "Departures",
        "transfer_balance": "Transfer balance",
        "value_evolution": "Value evolution",
        
        # Player table headers
        "player_name": "Name",
        "position": "Position",
        "age": "Age",
        "nationality": "Nationality",
        "market_value": "Market value",
        "contract_expires_date": "Contract expires",
        "shirt_number": "Number",
        "preferred_foot": "Preferred foot",
        "height": "Height",
        
        # Transfer table headers
        "transfer_player": "Player",
        "from_club": "From",
        "to_club": "To",
        "transfer_fee": "Fee",
        "transfer_date": "Date",
        "transfer_type": "Type",
        
        # Simulator page
        "simulator_title": "Transfer Strategies Simulator",
        "simulator_description": "Simulate different transfer strategies and analyze the impact on your team.",
        "club_name": "Club name",
        "starting_season": "Starting season",
        "transfer_budget": "Transfer budget",
        "salary_budget": "Salary budget",
        "run_simulation": "Run simulation",
        "simulation_results": "Simulation results",
        "season_summary": "Season summary",
        "players_bought": "Players bought",
        "players_sold": "Players sold",
        "current_squad": "Current squad",
        "squad_valuation": "Squad valuation",
        "net_benefit": "Net benefit",
        "ai_summary": "AI-generated summary",
        "generate_summary": "Generate AI summary",
        "loading_ai": "Generating summary...",
        
        # Charts
        "chart_value_by_position": "Value by position",
        "chart_age_distribution": "Age distribution",
        "chart_value_evolution": "Value evolution",
        "chart_transfer_timeline": "Transfer timeline",
        
        # Buttons
        "btn_download_csv": "Download CSV",
        "btn_download_json": "Download JSON",
        "btn_download_excel": "Download Excel",
        "btn_refresh": "Refresh",
        "btn_reset": "Reset",
        "btn_apply": "Apply",
        "btn_cancel": "Cancel",
        
        # Messages
        "loading": "Loading...",
        "success": "Success",
        "error": "Error",
        "warning": "Warning",
        "info": "Information",
        "no_results": "No results",
        "confirm_action": "Confirm action?",
        
        # Positions
        "pos_gk": "Goalkeeper",
        "pos_def": "Defender",
        "pos_mid": "Midfielder",
        "pos_att": "Forward",
        
        # Transfer types
        "type_purchase": "Purchase",
        "type_loan": "Loan",
        "type_free": "Free",
        "type_loan_return": "End of loan",
        
        # About page
        "about_title": "About",
        "about_description": "Team Analysis AI is a football team analysis tool with AI integration.",
        "about_features": "Features",
        "about_feature_1": "Data extraction from Transfermarkt",
        "about_feature_2": "Detailed squad analysis",
        "about_feature_3": "Transfer strategy simulation",
        "about_feature_4": "AI-generated summaries",
        "about_tech": "Technologies used",
        "about_source": "Source code",
        "about_author": "Developed by",
        
        # Footer
        "footer_data_source": "Data extracted from Transfermarkt",
        "footer_disclaimer": "This tool is for educational and analysis purposes only.",
        
        # Advice
        "advice_click_twice": "Note: sometimes you may need to click buttons more than once.",
    }
}


def t(lang: str, key: str) -> str:
    """
    Get translated text for a key.
    
    Args:
        lang: Language code ("es" or "en")
        key: Translation key
    
    Returns:
        Translated text or key if not found
    """
    lang = (lang or "en").lower()
    return TEXT.get(lang, TEXT["en"]).get(key, key)


def get_position_name(lang: str, pos_code: str) -> str:
    """Get translated position name."""
    pos_map = {
        "GK": "pos_gk",
        "DEF": "pos_def",
        "MID": "pos_mid",
        "ATT": "pos_att",
    }
    key = pos_map.get(pos_code.upper(), pos_code)
    translated = t(lang, key)
    return translated if translated != key else pos_code


def get_transfer_type_name(lang: str, type_code: str) -> str:
    """Get translated transfer type name."""
    type_map = {
        "purchase": "type_purchase",
        "loan": "type_loan",
        "free": "type_free",
        "loan_return": "type_loan_return",
    }
    key = type_map.get(type_code.lower(), type_code)
    translated = t(lang, key)
    return translated if translated != key else type_code


def format_currency(value: float, lang: str = "en") -> str:
    """Format currency value."""
    if value is None:
        return "N/A"
    
    if value >= 1_000_000_000:
        return f"€{value/1_000_000_000:.2f}B"
    elif value >= 1_000_000:
        return f"€{value/1_000_000:.1f}M"
    elif value >= 1_000:
        return f"€{value/1_000:.0f}K"
    else:
        return f"€{value:.0f}"
