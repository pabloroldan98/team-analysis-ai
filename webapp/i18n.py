# webapp/i18n.py
"""
Internationalization module for team-analysis-ai
Supports Spanish and English
"""

TEXT = {
    "es": {
        # General
        "title": "Simulador de Fichajes",
        "subtitle": "Simula ventanas de fichajes con IA",
        "language": "Idioma",
        "spanish": "Español",
        "english": "English",

        # Inputs
        "today_option": "Hoy",
        "select_season": "Temporada",
        "select_club": "Club",
        "transfer_budget": "Presupuesto de fichajes (€M)",
        "salary_budget": "Presupuesto salarial (€M/año)",
        "unlimited_budget": "Presupuesto ilimitado",
        "budget_first_note": "Presupuesto efectivo = mín(fichajes, salario × 10).",
        "budget_note": "Como los datos salariales de los jugadores no son públicos, asumimos que su salario anual ≈ 10% de su valor de mercado. Así, el factor limitante será el presupuesto de fichajes o el salarial, el que sea menor.",
        "budget_example": "(Ejemplo: €100M de fichajes = €10M de salario)",
        "run_simulation": "Simular ventana de fichajes",

        # Progress
        "step_loading": "Cargando datos de la temporada... [1/8]",
        "step_team": "Identificando plantilla del club... [2/8]",
        "step_team_values": "Calculando valores de equipos... [3/8]",
        "step_selling": "Vendiendo jugadores... [4/8]",
        "step_predicting": "Prediciendo valores futuros con ML... [5/8]",
        "step_knapsack": "Optimizando fichajes (Knapsack)... [6/8]",
        "step_summary": "Generando análisis con IA... [7/8]",
        "step_done": "¡Simulación completada! [8/8]",
        "sim_may_take": "Puede tardar unos minutos",

        # Output
        "simulation_title": "Simulación: {club} ({season})",
        "budget_section": "Presupuesto",
        "initial_budget": "Inicial",
        "sales_revenue": "Ventas",
        "total_budget": "Total",
        "players_sold": "Jugadores Vendidos",
        "players_bought": "Fichajes Recomendados",
        "no_buyer": "SIN COMPRADOR",
        "from_team": "desde {team}",
        "to_team": "→ {team}",
        "predicted": "predicción",
        "market_info": "Resumen Financiero",
        "budget_available": "Presupuesto disponible",
        "total_cost": "Coste total",
        "remaining_budget": "Presupuesto restante",
        "predicted_value_1y": "Valor predicho (1 año)",
        "net_benefit": "Beneficio neto esperado (1 año)",
        "final_squad": "Plantilla Final",
        "ai_analysis": "Análisis IA",
        "no_ai_key": "Introduce una API key de LLM para obtener análisis generado por IA.",
        "ai_supported_providers": "Proveedores soportados: OpenAI, Anthropic y Gemini.",
        "llm_api_key": "API Key del LLM",
        "llm_api_key_help": "Se detecta automáticamente: sk-... = OpenAI, sk-ant-... = Anthropic, otro = Gemini",
        "generate_analysis": "Generar análisis",
        "generating": "Generando análisis...",
        "ai_error": "No se pudo generar el análisis. Comprueba tu API key.",
        "no_signings": "No se encontraron fichajes óptimos para esta configuración.",

        # Team loading & sell/buy config
        "load_data": "Cargar datos del equipo",
        "loading_data": "Cargando datos...",
        "data_loaded": "Datos cargados correctamente",
        "squad_loaded": "plantilla de {count} jugadores cargada",
        "load_data_hint": "Carga los datos del equipo para poder configurar la simulación.",
        "select_players_to_sell": "Jugadores a vender",
        "sell_selection_help": "Elige qué jugadores quieres vender.",
        "signings_per_position": "Fichajes por posición",
        "buy_mode_exact": "Número exacto",
        "buy_mode_range": "Rango (mín–máx)",
        "signings_exact_help": "Elige cuántos jugadores fichar en cada posición.",
        "signings_range_help": "Elige el rango por posición. Se probará cada combinación y se elegirá la mejor.",
        "buy_min": "Mín",
        "buy_max": "Máx",
        "budget_title": "Presupuesto adicional",
        "budget_extra_note": "Este presupuesto es adicional al dinero obtenido por las ventas.",

        # Positions
        "pos_gk": "POR",
        "pos_def": "DEF",
        "pos_mid": "MED",
        "pos_att": "DEL",

        # Footer
        "footer": "Datos de Transfermarkt · Predicciones con XGBoost · Optimización con Knapsack",
        "created_by": "Creado por [Pablo Roldán]({url})",
    },
    "en": {
        # General
        "title": "Transfer Simulator",
        "subtitle": "Simulate transfer windows with AI",
        "language": "Language",
        "spanish": "Español",
        "english": "English",

        # Inputs
        "today_option": "Today",
        "select_season": "Season",
        "select_club": "Club",
        "transfer_budget": "Transfer budget (€M)",
        "salary_budget": "Salary budget (€M/year)",
        "unlimited_budget": "Unlimited budget",
        "budget_first_note": "Effective budget = min(transfer, salary × 10).",
        "budget_note": "Since player salary data is not public, we assume annual salary ≈ 10% of market value. Whichever budget is lower becomes the limiting factor.",
        "budget_example": "(Example: €100M transfer = €10M salary)",
        "run_simulation": "Simulate transfer window",

        # Progress
        "step_loading": "Loading season data... [1/8]",
        "step_team": "Identifying club squad... [2/8]",
        "step_team_values": "Calculating team values... [3/8]",
        "step_selling": "Selling players... [4/8]",
        "step_predicting": "Predicting future values with ML... [5/8]",
        "step_knapsack": "Optimizing signings (Knapsack)... [6/8]",
        "step_summary": "Generating AI analysis... [7/8]",
        "step_done": "Simulation complete! [8/8]",
        "sim_may_take": "This may take a few minutes",

        # Output
        "simulation_title": "Simulation: {club} ({season})",
        "budget_section": "Budget",
        "initial_budget": "Initial",
        "sales_revenue": "Sales",
        "total_budget": "Total",
        "players_sold": "Players Sold",
        "players_bought": "Recommended Signings",
        "no_buyer": "NO BUYER",
        "from_team": "from {team}",
        "to_team": "→ {team}",
        "predicted": "predicted",
        "market_info": "Financial Summary",
        "budget_available": "Budget available",
        "total_cost": "Total cost",
        "remaining_budget": "Remaining budget",
        "predicted_value_1y": "Predicted value (1 year)",
        "net_benefit": "Expected net benefit (1 year)",
        "final_squad": "Final Squad",
        "ai_analysis": "AI Analysis",
        "no_ai_key": "Enter an LLM API key to get an AI-generated analysis.",
        "ai_supported_providers": "Supported providers: OpenAI, Anthropic and Gemini.",
        "llm_api_key": "LLM API Key",
        "llm_api_key_help": "Auto-detected: sk-... = OpenAI, sk-ant-... = Anthropic, other = Gemini",
        "generate_analysis": "Generate analysis",
        "generating": "Generating analysis...",
        "ai_error": "Could not generate analysis. Check your API key.",
        "no_signings": "No optimal signings found for this configuration.",

        # Team loading & sell/buy config
        "load_data": "Load team data",
        "loading_data": "Loading data...",
        "data_loaded": "Data loaded successfully",
        "squad_loaded": "squad of {count} players loaded",
        "load_data_hint": "Load team data to configure the simulation.",
        "select_players_to_sell": "Players to sell",
        "sell_selection_help": "Choose which players you want to sell.",
        "signings_per_position": "Signings per position",
        "buy_mode_exact": "Exact number",
        "buy_mode_range": "Range (min–max)",
        "signings_exact_help": "Choose how many players to sign per position.",
        "signings_range_help": "Choose the range per position. Every combination will be tested and the best one selected.",
        "buy_min": "Min",
        "buy_max": "Max",
        "budget_title": "Additional budget",
        "budget_extra_note": "This budget is on top of the money obtained from player sales.",

        # Positions
        "pos_gk": "GK",
        "pos_def": "DEF",
        "pos_mid": "MID",
        "pos_att": "FWD",

        # Footer
        "footer": "Data from Transfermarkt · Predictions by XGBoost · Optimization with Knapsack",
        "created_by": "Created by [Pablo Roldán]({url})",
    },
}


def t(lang: str, key: str, **kwargs) -> str:
    """Get translated text for a key, with optional formatting."""
    lang = (lang or "en").lower()
    text = TEXT.get(lang, TEXT["en"]).get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text


def format_currency(value, decimals: int = 1) -> str:
    """Format currency value."""
    if value is None:
        return "N/A"
    value = float(value)
    if abs(value) >= 1_000_000_000:
        return f"€{value / 1_000_000_000:.{decimals}f}B"
    elif abs(value) >= 1_000_000:
        return f"€{value / 1_000_000:.{decimals}f}M"
    elif abs(value) >= 1_000:
        return f"€{value / 1_000:.0f}K"
    else:
        return f"€{value:.0f}"
