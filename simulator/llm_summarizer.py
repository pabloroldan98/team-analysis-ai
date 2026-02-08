"""LLM integration for season summary."""
from __future__ import annotations

import os
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def generate_summary(
    club_name: str,
    season: str,
    players_sold: list,
    players_bought: list,
    initial_valuation: float,
    final_valuation: float,
    net_benefit: float,
    formation: list,
) -> str:
    """
    Generate AI summary of the simulation using OpenAI or Anthropic.
    
    Returns summary text. Falls back to a template if no API keys are set.
    """
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    
    sold_names = [p.name for p in players_sold] if players_sold else []
    bought_names = [p.name for p in players_bought] if players_bought else []
    
    prompt = _build_prompt(
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
        return _call_anthropic(prompt)
    return _call_openai(prompt)


def _build_prompt(
    club_name: str,
    season: str,
    sold_names: list,
    bought_names: list,
    initial_valuation: float,
    final_valuation: float,
    net_benefit: float,
    formation: list,
) -> str:
    """Build the prompt for the LLM."""
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


def _call_openai(prompt: str) -> str:
    """Call OpenAI GPT API."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _fallback_summary(prompt)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
        )
        return response.choices[0].message.content or _fallback_summary(prompt)
    except Exception as e:
        return _fallback_summary(prompt) + f"\n\n(API error: {e})"


def _call_anthropic(prompt: str) -> str:
    """Call Anthropic Claude API."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return _fallback_summary(prompt)

    try:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307"),
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text if response.content else ""
        return text or _fallback_summary(prompt)
    except Exception as e:
        return _fallback_summary(prompt) + f"\n\n(API error: {e})"


def _fallback_summary(prompt: str) -> str:
    """Return a basic summary when no API is available."""
    return """**Summary (template - set OPENAI_API_KEY or ANTHROPIC_API_KEY for AI-generated summary):**

The transfer simulation has been completed. Review the players sold and bought above to assess the strategy. Set LLM_PROVIDER=openai or anthropic and the corresponding API key in .env to enable AI-generated summaries."""
