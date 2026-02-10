"""LLM integration for season summary."""
from __future__ import annotations

import os
from typing import Optional, List, TYPE_CHECKING

from dotenv import load_dotenv
try:
    load_dotenv()
except ImportError:
    pass

if TYPE_CHECKING:
    from simulator.transfer_simulator import TransferResult, SoldPlayer
    from player import Player


def generate_summary_from_result(
    result: "TransferResult",
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    language: Optional[str] = None,
) -> Optional[str]:
    """
    Generate AI summary from a TransferResult object.
    
    Args:
        result: TransferResult from the simulation
        provider: LLM provider ("openai", "anthropic", "gemini")
        api_key: Optional API key override
        language: Response language ("es" for Spanish, "en" for English, etc.)
    
    Returns:
        AI-generated summary text, or None if no API key is available
    """
    # Build detailed info about sold players
    sold_info = []
    for sp in result.players_sold:
        p = sp.player
        mv = (p.market_value or 0) / 1e6
        if sp.was_sold:
            sold_info.append(f"  - {p.name} ({p.position}): €{mv:.1f}M -> {sp.destination_team}")
        else:
            sold_info.append(f"  - {p.name} ({p.position}): €{mv:.1f}M (no buyer found)")
    
    # Build detailed info about bought players
    bought_info = []
    for p in result.recommended_signings:
        mv = (p.market_value or 0) / 1e6
        pv = (p.predicted_value or 0) / 1e6
        bought_info.append(f"  - {p.name} ({p.position}, from {p.team}): €{mv:.1f}M -> €{pv:.1f}M predicted")
    
    # Get IDs of sold players to exclude them from remaining squad
    sold_player_ids = {sp.player.player_id for sp in result.players_sold}
    
    # Build remaining squad info (current squad minus sold players, grouped by position)
    rest_squad_by_position = {"GK": [], "DEF": [], "MID": [], "ATT": [], "Other": []}
    rest_squad_players = [p for p in result.current_squad if p.player_id not in sold_player_ids]
    
    for p in rest_squad_players:
        mv = (p.market_value or 0) / 1e6
        pv = (p.predicted_value or 0) / 1e6
        player_str = f"    - {p.name}: €{mv:.1f}M (predicted: €{pv:.1f}M)"
        pos = p.position if p.position in rest_squad_by_position else "Other"
        rest_squad_by_position[pos].append(player_str)
    
    rest_squad_info = []
    for pos in ["GK", "DEF", "MID", "ATT"]:
        if rest_squad_by_position[pos]:
            rest_squad_info.append(f"  {pos} ({len(rest_squad_by_position[pos])}):")
            rest_squad_info.extend(rest_squad_by_position[pos])
    
    # Calculate squad totals
    sold_total_value = sum((sp.player.market_value or 0) for sp in result.players_sold) / 1e6
    sold_total_predicted = sum((sp.player.predicted_value or 0) for sp in result.players_sold) / 1e6
    bought_total_value = sum((p.market_value or 0) for p in result.recommended_signings) / 1e6
    bought_total_predicted = sum((p.predicted_value or 0) for p in result.recommended_signings) / 1e6
    rest_squad_total_value = sum((p.market_value or 0) for p in rest_squad_players) / 1e6
    rest_squad_total_predicted = sum((p.predicted_value or 0) for p in rest_squad_players) / 1e6
    # squad_total_predicted = sum((p.predicted_value or 0) for p in result.current_squad) / 1e6
    
    # Calculate totals
    total_cost = sum((p.market_value or 0) for p in result.recommended_signings) / 1e6
    total_predicted = sum((p.predicted_value or 0) for p in result.recommended_signings) / 1e6
    net_benefit = total_predicted - total_cost
    
    prompt = _build_detailed_prompt(
        club_name=result.club_name,
        season=result.season,
        initial_budget=result.initial_budget,
        sales_revenue=result.sales_revenue,
        total_budget=result.total_budget,
        sold_info=sold_info,
        bought_info=bought_info,
        rest_squad_info=rest_squad_info,
        sold_total_value=sold_total_value,
        sold_total_predicted=sold_total_predicted,
        bought_total_value=bought_total_value,
        bought_total_predicted=bought_total_predicted,
        rest_squad_total_value=rest_squad_total_value,
        rest_squad_total_predicted=rest_squad_total_predicted,
        total_cost=total_cost,
        total_predicted=total_predicted,
        net_benefit=net_benefit,
        remaining_budget=result.total_budget - total_cost,
        language=language,
    )
    
    provider = (provider or os.getenv("LLM_PROVIDER", "openai")).lower()
    
    if provider == "anthropic":
        return _call_anthropic(prompt, api_key=api_key)
    elif provider == "gemini":
        return _call_gemini(prompt, api_key=api_key)
    return _call_openai(prompt, api_key=api_key)


def generate_summary(
    club_name: str,
    season: str,
    players_sold: list,
    players_bought: list,
    initial_valuation: float,
    final_valuation: float,
    net_benefit: float,
    formation: list,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Optional[str]:
    """
    Generate AI summary of the simulation using OpenAI, Anthropic, or Gemini.
    
    Args:
        club_name: Name of the club
        season: Season string
        players_sold: List of sold players
        players_bought: List of bought players
        initial_valuation: Initial squad valuation
        final_valuation: Final squad valuation
        net_benefit: Net financial benefit
        formation: Best formation
        provider: LLM provider ("openai", "anthropic", "gemini"). 
                  Defaults to LLM_PROVIDER env var or "openai".
        api_key: Optional API key override. If not provided, uses env vars.
    
    Returns:
        Summary text, or None if no API key is available.
    """
    provider = (provider or os.getenv("LLM_PROVIDER", "openai")).lower()
    
    sold_names = [p.name for p in players_sold] if players_sold else []
    bought_names = [p.name for p in players_bought] if players_bought else []
    
    prompt = _build_simple_prompt(
        club_name=club_name,
        season=season,
        sold_names=sold_names,
        bought_names=bought_names,
        initial_valuation=initial_valuation,
        final_valuation=final_valuation,
        net_benefit=net_benefit,
        formation=formation,
    )
    
    if provider == "anthropic":
        return _call_anthropic(prompt, api_key=api_key)
    elif provider == "gemini":
        return _call_gemini(prompt, api_key=api_key)
    return _call_openai(prompt, api_key=api_key)


def _build_detailed_prompt(
    club_name: str,
    season: str,
    initial_budget: int,
    sales_revenue: int,
    total_budget: int,
    sold_info: List[str],
    bought_info: List[str],
    rest_squad_info: List[str],
    sold_total_value: float,
    sold_total_predicted: float,
    bought_total_value: float,
    bought_total_predicted: float,
    rest_squad_total_value: float,
    rest_squad_total_predicted: float,
    total_cost: float,
    total_predicted: float,
    net_benefit: float,
    remaining_budget: float,
    language: Optional[str] = None,
) -> str:
    """Build a detailed prompt for the LLM based on full simulation data."""
    sold_text = "\n".join(sold_info) if sold_info else "  None"
    bought_text = "\n".join(bought_info) if bought_info else "  None"
    rest_squad_text = "\n".join(rest_squad_info) if rest_squad_info else "  No squad data available"
    
    return f"""You are a football analyst. Analyze this transfer window simulation for {club_name} in the {season} season.

IMPORTANT: Start your response immediately with the analysis. Be direct and insightful.

=== YOUR TASK ===
Write a strategic analysis (8-12 sentences) that tells a story about this transfer window. Focus on:

1. THE DEPARTURES: What do these sales mean for the club? 
   - Are they losing key players or selling fringe players?
   - Is this a generational change? (e.g., selling a 30-year-old starter to bring in young talent)
   - Compare the sold players' value to the rest of the squad - were these important players?

2. THE ARRIVALS: What do these signings bring?
   - Do they fill the gaps left by the departures?
   - Are they buying potential (low cost, high predicted value) or proven quality?
   - How do they compare to the existing players in their positions?

3. THE BIGGER PICTURE:
   - Is this a rebuilding window or a consolidation window?
   - Financial verdict: Expected Net Benefit is €{net_benefit:+.1f}M - is this good business?

Be specific about player names, positions, and values. Tell a coherent story about what this window means for the club.
{f'IMPORTANT: Write your entire response in Spanish.' if language == 'es' else f'IMPORTANT: Write your entire response in English.' if language == 'en' else 'If the club name is in Spanish, respond in Spanish; otherwise respond in English.'}

=== DATA FOR ANALYSIS ===

BUDGET:
- Initial transfer budget: €{initial_budget}M
- Revenue from player sales: €{sales_revenue}M  
- Total available budget: €{total_budget}M

PLAYERS SOLD (and their destinations):
{sold_text}

PLAYERS BOUGHT (with current cost and predicted value in 1 year):
{bought_text}

FINANCIAL SUMMARY:
- Total spending on new signings: €{total_cost:.1f}M
- Remaining budget: €{remaining_budget:.1f}M
- Total predicted value of signings (1 year): €{total_predicted:.1f}M
- Expected Net Financial Benefit: €{net_benefit:+.1f}M

REMAINING SQUAD (players who stayed - not sold, not bought):
{rest_squad_text}

SQUAD VALUES:
Total value of sold players: €{sold_total_value:.1f}M (predicted in 1 year: €{sold_total_predicted:.1f}M)
Total value of bought players: €{bought_total_value:.1f}M (predicted in 1 year: €{bought_total_predicted:.1f}M)
Total value of remaining players: €{rest_squad_total_value:.1f}M (predicted in 1 year: €{rest_squad_total_predicted:.1f}M)


Note: Previous squad = Remaining players + Players sold ; Final squad = Remaining players + Players bought


Now write your analysis, starting with the overall verdict:"""


def _build_simple_prompt(
    club_name: str,
    season: str,
    sold_names: list,
    bought_names: list,
    initial_valuation: float,
    final_valuation: float,
    net_benefit: float,
    formation: list,
) -> str:
    """Build a simple prompt for the LLM."""
    formation_str = "-".join(map(str, formation))
    return f"""Summarize this transfer simulation for {club_name} in season {season}:

Players sold: {sold_names if sold_names else 'None'}
Players bought: {bought_names if bought_names else 'None'}
Initial squad valuation: €{initial_valuation/1_000_000:.1f}M
Final squad valuation: €{final_valuation/1_000_000:.1f}M
Net benefit (profit/loss): €{net_benefit/1_000_000:.1f}M
Best formation: {formation_str}

Provide a brief strategic assessment (3-5 sentences) covering:
1. Quality of transfers (sales and signings)
2. Financial impact
3. Overall squad improvement
Respond in the same language as the club name if it's Spanish, otherwise English."""


def _call_openai(prompt: str, api_key: Optional[str] = None) -> Optional[str]:
    """Call OpenAI GPT API. Returns None if no API key available."""
    api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
        )
        return response.choices[0].message.content or None
    except Exception as e:
        print(f"  Warning: OpenAI API error: {e}")
        return None


def _call_anthropic(prompt: str, api_key: Optional[str] = None) -> Optional[str]:
    """Call Anthropic Claude API. Returns None if no API key available."""
    api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307"),
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text if response.content else ""
        return text or None
    except Exception as e:
        print(f"  Warning: Anthropic API error: {e}")
        return None


def _call_gemini(prompt: str, api_key: Optional[str] = None) -> Optional[str]:
    """Call Google Gemini API. Returns None if no API key available."""
    api_key = api_key or os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    try:
        from google import genai
        from google.genai import types
        
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=4096),
        )
        return response.text or None
    except Exception as e:
        print(f"  Warning: Gemini API error: {e}")
        return None
