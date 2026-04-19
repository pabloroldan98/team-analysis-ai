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
    from entities.player import Player


def _build_prompt_from_result(
    result: "TransferResult",
    language: Optional[str] = None,
) -> str:
    """Build the LLM prompt from a TransferResult (without calling any LLM)."""
    sold_info = []
    for sp in result.players_sold:
        p = sp.player
        mv = (p.market_value or 0) / 1e6
        if sp.was_sold:
            sold_info.append(f"  - {p.name} ({p.position}): €{mv:.1f}M -> {sp.destination_team}")
        else:
            sold_info.append(f"  - {p.name} ({p.position}): €{mv:.1f}M (no buyer found)")

    bought_info = []
    for p in result.recommended_signings:
        mv = (p.market_value or 0) / 1e6
        pv = (p.predicted_value or 0) / 1e6
        bought_info.append(f"  - {p.name} ({p.position}, from {p.team}): €{mv:.1f}M -> €{pv:.1f}M predicted")

    sold_player_ids = {sp.player.player_id for sp in result.players_sold}
    rest_squad_by_position: dict = {"GK": [], "DEF": [], "MID": [], "ATT": [], "Other": []}
    rest_squad_players = [p for p in result.current_squad if p.player_id not in sold_player_ids]

    for p in rest_squad_players:
        mv = (p.market_value or 0) / 1e6
        pv = (p.predicted_value or 0) / 1e6
        player_str = f"    - {p.name}: €{mv:.1f}M (predicted: €{pv:.1f}M)"
        pos = p.position if p.position in rest_squad_by_position else "Other"
        rest_squad_by_position[pos].append(player_str)

    rest_squad_info: list = []
    for pos in ["GK", "DEF", "MID", "ATT"]:
        if rest_squad_by_position[pos]:
            rest_squad_info.append(f"  {pos} ({len(rest_squad_by_position[pos])}):")
            rest_squad_info.extend(rest_squad_by_position[pos])

    sold_total_value = sum((sp.player.market_value or 0) for sp in result.players_sold) / 1e6
    sold_total_predicted = sum((sp.player.predicted_value or 0) for sp in result.players_sold) / 1e6
    bought_total_value = sum((p.market_value or 0) for p in result.recommended_signings) / 1e6
    bought_total_predicted = sum((p.predicted_value or 0) for p in result.recommended_signings) / 1e6
    rest_squad_total_value = sum((p.market_value or 0) for p in rest_squad_players) / 1e6
    rest_squad_total_predicted = sum((p.predicted_value or 0) for p in rest_squad_players) / 1e6
    total_cost = bought_total_value
    total_predicted = bought_total_predicted
    net_benefit = total_predicted - total_cost

    return _build_detailed_prompt(
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


def generate_summary_from_result(
    result: "TransferResult",
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    language: Optional[str] = None,
) -> Optional[str]:
    """Generate AI summary from a TransferResult object."""
    prompt = _build_prompt_from_result(result, language=language)
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
    Generate AI summary of the simulation using ChatGPT, Claude, or Gemini.
    
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
    
    return f"""You are an elite football transfer analyst. Produce a structured report for {club_name}'s {season} transfer window simulation.

{f'IMPORTANT: Write your ENTIRE response in Spanish.' if language == 'es' else f'IMPORTANT: Write your ENTIRE response in English.' if language == 'en' else 'If the club name is in Spanish, respond in Spanish; otherwise respond in English.'}

=== DATA ===

BUDGET:
- Initial: €{initial_budget}M | Sales revenue: €{sales_revenue}M | Total: €{total_budget}M

PLAYERS SOLD:
{sold_text}

PLAYERS BOUGHT (cost → predicted value in 1 year):
{bought_text}

REMAINING SQUAD (players who stayed: not sold, not bought):
{rest_squad_text}

FINANCIALS:
- Spending: €{total_cost:.1f}M | Remaining: €{remaining_budget:.1f}M
- Predicted value of signings (1yr): €{total_predicted:.1f}M | Net Benefit: €{net_benefit:+.1f}M
- Sold total: €{sold_total_value:.1f}M (pred €{sold_total_predicted:.1f}M)
- Bought total: €{bought_total_value:.1f}M (pred €{bought_total_predicted:.1f}M)
- Staying total: €{rest_squad_total_value:.1f}M (pred €{rest_squad_total_predicted:.1f}M)

Note: Previous squad = Remaining squad + Players sold ; Final squad = Remaining squad + Players bought

=== YOUR TASK ===

Write a structured report with these sections. Use markdown formatting (##, bold, bullet points).

## 1. Overall Verdict (2-3 sentences)
A headline-style verdict on the window. Is it a rebuilding, consolidation, or marquee window?

## 2. Sale-by-Sale Reasoning
For EACH sold player, write 1-2 sentences explaining:
- **Why sell now**: Was the player past peak? Declining value? Needed the budget? Squad depth made them expendable?
- **Financial logic**: Compare market value vs predicted value. If predicted < market → good timing. If no buyer → explain the difficulty.

## 3. Signing-by-Signing Reasoning
For EACH signed player, write 2-3 sentences explaining:
- **Why this player**: What does the model see? Growth potential (compare cost vs predicted)? Position need?
- **xGrowth**: Calculate and show (predicted_value / market_value - 1) as a percentage.
- **Fair price assessment**: Is the market_value a fair price? Overpay or bargain?

## 4. Financial Summary
- Total investment vs expected return
- ROI percentage
- Risk assessment (concentration risk, age profile)

Be specific with names, numbers, and percentages. No filler."""


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


def _call_openai(prompt: str, api_key: Optional[str] = None, *, raise_on_error: bool = False) -> Optional[str]:
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
        if raise_on_error:
            raise
        print(f"  Warning: OpenAI API error: {e}")
        return None


def _call_anthropic(prompt: str, api_key: Optional[str] = None, *, raise_on_error: bool = False) -> Optional[str]:
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
        if raise_on_error:
            raise
        print(f"  Warning: Anthropic API error: {e}")
        return None


def _call_gemini(prompt: str, api_key: Optional[str] = None, *, raise_on_error: bool = False) -> Optional[str]:
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
        if raise_on_error:
            raise
        print(f"  Warning: Gemini API error: {e}")
        return None
