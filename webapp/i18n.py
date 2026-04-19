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
        "unlimited_budget": "Presupuesto ilimitado",
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
        "ai_supported_providers": "Proveedores soportados: ChatGPT, Claude y Gemini.",
        "llm_api_key": "API Key del LLM",
        "llm_api_key_help": "Se detecta automáticamente: sk-... = ChatGPT, sk-ant-... = Claude, otro = Gemini",
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
        "sell_recommendations": "Recomendaciones de venta",
        "sell_rec_help": "Basado en las predicciones de valor futuro del modelo ML.",
        "sell_rec_peak": "Pico financiero alcanzado",
        "sell_rec_peak_desc": "Jugadores cuyo valor predicho es menor que su valor de mercado actual. Han alcanzado su máximo y se espera que pierdan valor.",
        "sell_rec_decline": "Máxima caída de valor esperada",
        "sell_rec_decline_desc": "Jugadores ordenados por mayor caída esperada (valor actual − predicho).",
        "sell_rec_delta": "Caída esperada",
        "sell_rec_select_all_peak": "Seleccionar todos los de pico",
        "sell_rec_select_all_decline": "Seleccionar top caída",
        "sell_rec_no_peak": "Ningún jugador de la plantilla ha alcanzado su pico financiero.",
        "sell_rec_no_decline": "No se detectan caídas de valor significativas.",
        "signings_per_position": "Fichajes por posición",
        "buy_mode_exact": "Número exacto",
        "buy_mode_range": "Rango (mín–máx)",
        "buy_mode_total": "Total de fichajes",
        "signings_exact_help": "Elige cuántos jugadores fichar en cada posición.",
        "signings_range_help": "Elige el rango por posición. Se probará cada combinación y se elegirá la mejor.",
        "signings_total_help": "Elige cuántos jugadores fichar en total. Se probarán todas las combinaciones de posiciones (máx. 3 por posición) y se elegirá la mejor.",
        "total_players": "Jugadores a fichar",
        "buy_min": "Mín",
        "buy_max": "Máx",
        "budget_title": "Presupuesto adicional",
        "budget_extra_note": "Este presupuesto es adicional al dinero obtenido por las ventas.",

        # Approaches
        "approach_title": "Estrategia de fichajes",
        "approach_max_value": "Todos los jugadores",
        "approach_max_value_help": "Sin filtro: todos los jugadores elegibles son candidatos.",
        "approach_young_talents": "Jóvenes promesas",
        "approach_young_talents_help": "Solo considera jugadores de 23 años o menos. Ideal para construir un proyecto a largo plazo.",
        "approach_veteran_players": "Veteranos",
        "approach_veteran_players_help": "Solo considera jugadores de 30 años o más. Ideal para fichajes de experiencia e impacto inmediato.",
        "approach_balanced": "Equilibrado",
        "approach_balanced_help": "Prioriza jugadores en su mejor edad (25-29) con alto valor predicho. Equilibra rendimiento inmediato y valor.",

        # Optimisation objective
        "objective_title": "Parámetro a maximizar",
        "objective_smv": "Valor Futuro (SMV)",
        "objective_smv_help": "Maximiza el valor de mercado futuro total de los fichajes.",
        "objective_net_benefit": "Beneficio Neto",
        "objective_net_benefit_help": "Maximiza la diferencia absoluta entre valor futuro y coste (valor predicho − precio de fichaje).",
        "objective_roi": "ROI Total",
        "objective_roi_help": "Maximiza el retorno de inversión porcentual ((valor predicho − coste) / coste).",
        "objective_value_growth": "Crecimiento de Valor",
        "objective_value_growth_help": "Maximiza la diferencia absoluta entre valor futuro y valor actual de cada jugador.",
        "objective_growth_pct": "% Crecimiento",
        "objective_growth_pct_help": "Maximiza el porcentaje de crecimiento del valor de cada jugador (valor futuro / valor actual).",

        # Simulation speed
        "sim_speed_title": "Velocidad de simulación",
        "sim_speed_local": "Más rápida",
        "sim_speed_local_help": "Ejecución más rápida con poda agresiva de candidatos. Resultados aceptables.",
        "sim_speed_fast": "Rápida",
        "sim_speed_fast_help": "Equilibrio entre velocidad y calidad de resultados.",
        "sim_speed_standard": "Estándar",
        "sim_speed_standard_help": "Computación completa sin recortes. Mejores resultados posibles.",

        # Advanced filters
        "filters_title": "Filtros avanzados",
        "filters_collapsed": "Mostrar filtros avanzados",
        "league_filter": "Filtrar por ligas",
        "league_filter_help": "Selecciona las ligas de las que se pueden fichar jugadores. Vacío = todas.",
        "banned_clubs": "Clubes excluidos",
        "banned_clubs_help": "Nombres de clubes de los que no se puede fichar (separados por coma).",
        "banned_clubs_placeholder": "Ej: Real Madrid, Manchester City",
        "exclude_top_n": "Excluir top N clubes",
        "exclude_top_n_help": "Excluir los N clubes más ricos (por valor de mercado) como fuente de fichajes.",
        "min_market_value_title": "Valor mínimo de mercado (€M)",
        "min_market_value_help": "Solo considerar jugadores con valor de mercado superior a este umbral.",
        "horizon_title": "Horizonte temporal (años)",
        "horizon_help": "Horizonte de predicción: 1, 2 o 3 años. El modelo de 1 año se extrapola iterativamente.",
        "horizon_1": "1 año",
        "horizon_2": "2 años",
        "horizon_3": "3 años",

        # Analytics
        "xgrowth_title": "Top xGrowth proyectado",
        "xgrowth_help": "Jugadores con mayor crecimiento de valor esperado (predicho / actual − 1).",
        "xgrowth_col_player": "Jugador",
        "xgrowth_col_value": "Valor actual",
        "xgrowth_col_predicted": "Predicción",
        "xgrowth_col_growth": "xGrowth",
        "xgrowth_col_fair": "Precio justo",
        "similar_title": "Jugadores similares (financiero)",
        "similar_help": "Alternativas financieramente similares para cada fichaje recomendado.",
        "similar_col_similarity": "Similitud",
        "fair_price_title": "Precio justo de compra",
        "fair_price_help": "El precio justo es el valor predicho del jugador: punto de equilibrio para el comprador.",
        "analytics_section": "Análisis e Inteligencia",
        "no_analytics": "Ejecuta una simulación para ver el análisis avanzado.",

        # Player search
        "search_title": "Buscador de jugadores",
        "search_placeholder": "Buscar por nombre...",
        "search_position": "Posición",
        "search_min_value": "Valor mín. (€M)",
        "search_max_value": "Valor máx. (€M)",
        "search_min_age": "Edad mín.",
        "search_max_age": "Edad máx.",
        "search_results": "resultados",
        "search_help": "Busca jugadores por nombre, posición, rango de valor o edad.",
        "search_no_results": "No se encontraron jugadores.",
        "search_col_name": "Nombre",
        "search_col_team": "Equipo",
        "search_col_pos": "Pos",
        "search_col_age": "Edad",
        "search_col_value": "Valor",
        "search_col_predicted": "Predicción",
        "search_col_xgrowth": "xGrowth",
        "search_col_fair": "Precio justo",

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
        "unlimited_budget": "Unlimited budget",
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
        "ai_supported_providers": "Supported providers: ChatGPT, Claude and Gemini.",
        "llm_api_key": "LLM API Key",
        "llm_api_key_help": "Auto-detected: sk-... = ChatGPT, sk-ant-... = Claude, other = Gemini",
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
        "sell_recommendations": "Sale recommendations",
        "sell_rec_help": "Based on the ML model's predicted future values.",
        "sell_rec_peak": "Financial peak reached",
        "sell_rec_peak_desc": "Players whose predicted value is below their current market value. They have peaked and are expected to decline.",
        "sell_rec_decline": "Largest expected value drops",
        "sell_rec_decline_desc": "Players sorted by largest expected decline (current value − predicted).",
        "sell_rec_delta": "Expected drop",
        "sell_rec_select_all_peak": "Select all peaked",
        "sell_rec_select_all_decline": "Select top declines",
        "sell_rec_no_peak": "No squad player has reached their financial peak.",
        "sell_rec_no_decline": "No significant value drops detected.",
        "signings_per_position": "Signings per position",
        "buy_mode_exact": "Exact number",
        "buy_mode_range": "Range (min–max)",
        "buy_mode_total": "Total signings",
        "signings_exact_help": "Choose how many players to sign per position.",
        "signings_range_help": "Choose the range per position. Every combination will be tested and the best one selected.",
        "signings_total_help": "Choose how many players to sign in total. All position combinations (max 3 per position) will be tested and the best one selected.",
        "total_players": "Players to sign",
        "buy_min": "Min",
        "buy_max": "Max",
        "budget_title": "Additional budget",
        "budget_extra_note": "This budget is on top of the money obtained from player sales.",

        # Approaches
        "approach_title": "Signing strategy",
        "approach_max_value": "All players",
        "approach_max_value_help": "No filter: all eligible players are candidates.",
        "approach_young_talents": "Young talents",
        "approach_young_talents_help": "Only considers players aged 23 or under. Great for building a long-term project.",
        "approach_veteran_players": "Veterans",
        "approach_veteran_players_help": "Only considers players aged 30 or older. Ideal for experienced signings with immediate impact.",
        "approach_balanced": "Balanced",
        "approach_balanced_help": "Prioritizes prime-age players (25-29) with high predicted value. Balances immediate performance and value.",

        # Optimisation objective
        "objective_title": "Parameter to maximise",
        "objective_smv": "Future Value (SMV)",
        "objective_smv_help": "Maximises the total predicted future market value of signings.",
        "objective_net_benefit": "Net Benefit",
        "objective_net_benefit_help": "Maximises the absolute difference between predicted value and signing cost.",
        "objective_roi": "Total ROI",
        "objective_roi_help": "Maximises the percentage return on investment ((predicted − cost) / cost).",
        "objective_value_growth": "Value Growth",
        "objective_value_growth_help": "Maximises the absolute value growth of each player (future − current).",
        "objective_growth_pct": "Growth %",
        "objective_growth_pct_help": "Maximises the value growth percentage of each player (future / current).",

        # Simulation speed
        "sim_speed_title": "Simulation speed",
        "sim_speed_local": "Faster",
        "sim_speed_local_help": "Fastest execution with aggressive candidate pruning. Acceptable results.",
        "sim_speed_fast": "Fast",
        "sim_speed_fast_help": "Balance between speed and result quality.",
        "sim_speed_standard": "Standard",
        "sim_speed_standard_help": "Full computation without cuts. Best possible results.",

        # Advanced filters
        "filters_title": "Advanced filters",
        "filters_collapsed": "Show advanced filters",
        "league_filter": "Filter by leagues",
        "league_filter_help": "Select the leagues from which players can be signed. Empty = all.",
        "banned_clubs": "Excluded clubs",
        "banned_clubs_help": "Club names from which signings are not allowed (comma-separated).",
        "banned_clubs_placeholder": "e.g. Real Madrid, Manchester City",
        "exclude_top_n": "Exclude top N clubs",
        "exclude_top_n_help": "Exclude the N richest clubs (by market value) as signing sources.",
        "min_market_value_title": "Minimum market value (€M)",
        "min_market_value_help": "Only consider players whose market value exceeds this threshold.",
        "horizon_title": "Prediction horizon (years)",
        "horizon_help": "Prediction horizon: 1, 2 or 3 years. The 1-year model is iteratively extrapolated.",
        "horizon_1": "1 year",
        "horizon_2": "2 years",
        "horizon_3": "3 years",

        # Analytics
        "xgrowth_title": "Top Projected xGrowth",
        "xgrowth_help": "Players with the highest expected value growth (predicted / current − 1).",
        "xgrowth_col_player": "Player",
        "xgrowth_col_value": "Current Value",
        "xgrowth_col_predicted": "Prediction",
        "xgrowth_col_growth": "xGrowth",
        "xgrowth_col_fair": "Fair Price",
        "similar_title": "Similar Players (Financial)",
        "similar_help": "Financially similar alternatives for each recommended signing.",
        "similar_col_similarity": "Similarity",
        "fair_price_title": "Fair Purchase Price",
        "fair_price_help": "The fair price is the player's predicted value: the break-even point for the buyer.",
        "analytics_section": "Analytics & Intelligence",
        "no_analytics": "Run a simulation to see the advanced analysis.",

        # Player search
        "search_title": "Player Search",
        "search_placeholder": "Search by name...",
        "search_position": "Position",
        "search_min_value": "Min value (€M)",
        "search_max_value": "Max value (€M)",
        "search_min_age": "Min age",
        "search_max_age": "Max age",
        "search_results": "results",
        "search_help": "Search players by name, position, value range or age.",
        "search_no_results": "No players found.",
        "search_col_name": "Name",
        "search_col_team": "Team",
        "search_col_pos": "Pos",
        "search_col_age": "Age",
        "search_col_value": "Value",
        "search_col_predicted": "Prediction",
        "search_col_xgrowth": "xGrowth",
        "search_col_fair": "Fair Price",

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
