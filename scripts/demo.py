#!/usr/bin/env python3
"""
Interactive console demo of Team Transfers Simulator.

Showcases all major features:
  1. Squad loading (from precomputed cache)
  2. Player search
  3. Sell recommendations
  4. Transfer simulation (multiple objectives)
  5. Analytics: xGrowth ranking, similar players, fair price
  6. AI summary prompt preview

Usage:
    python scripts/demo.py
    python scripts/demo.py --club "FC Barcelona" --season 2024-2025
    python scripts/demo.py --club "Athletic Club" --season today --speed local
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# ── Formatting helpers ────────────────────────────────────────────────────

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def header(text: str) -> None:
    width = 70
    print(f"\n{CYAN}{'═' * width}")
    print(f"  {BOLD}{text}{RESET}{CYAN}")
    print(f"{'═' * width}{RESET}\n")


def subheader(text: str) -> None:
    print(f"\n{YELLOW}── {text} {'─' * (60 - len(text))}{RESET}\n")


def money(value: float | None) -> str:
    if value is None:
        return "—"
    m = (value or 0) / 1_000_000
    if m >= 1:
        return f"€{m:,.1f}M"
    return f"€{value or 0:,.0f}"


def pct(value: float | None, signed: bool = True) -> str:
    if value is None:
        return "—"
    s = f"{value * 100:+.1f}%" if signed else f"{value * 100:.1f}%"
    if value >= 0:
        return f"{GREEN}{s}{RESET}"
    return f"{RED}{s}{RESET}"


def table_row(*cols: str, widths: list[int] | None = None) -> str:
    if widths is None:
        widths = [22] * len(cols)
    parts = []
    for col, w in zip(cols, widths):
        clean = col
        for esc in [CYAN, GREEN, YELLOW, RED, BOLD, DIM, RESET]:
            clean = clean.replace(esc, "")
        pad = max(0, w - len(clean))
        parts.append(col + " " * pad)
    return "  ".join(parts)


# ── Main demo ─────────────────────────────────────────────────────────────

def run_demo(
    club_name: str = "Athletic Club",
    season: str = "today",
    speed: str = "local",
    objective: str = "smv",
    budget: int = 50,
):
    from simulator.transfer_simulator import TransferSimulator

    header(f"DEMO: {club_name} — Season {season}")

    # ── 1. Load squad ─────────────────────────────────────────────────
    subheader("1 / 6  Loading squad")
    t0 = time.time()
    sim = TransferSimulator(
        club_name=club_name,
        season=season,
        transfer_budget=budget,
    )
    sim.preload_data(verbose=False)
    elapsed = time.time() - t0
    print(f"  Squad loaded in {elapsed:.1f}s  ({len(sim.club_players)} players, "
          f"{len(sim.all_players)} total in database)")
    print(f"  Budget: €{budget}M")

    widths = [25, 6, 5, 14, 14, 10]
    print(f"\n  {BOLD}{table_row('Player', 'Pos', 'Age', 'Market Value', 'Predicted', 'xGrowth', widths=widths)}{RESET}")
    print(f"  {'─' * 80}")
    for p in sorted(sim.club_players, key=lambda x: x.market_value or 0, reverse=True)[:15]:
        mv = p.market_value or 0
        pv = p.predicted_value
        xg = pct((pv / mv) - 1) if pv and mv > 0 else "—"
        print(f"  {table_row(p.name or '?', p.position or '?', str(p.age or '?'), money(mv), money(pv), xg, widths=widths)}")
    if len(sim.club_players) > 15:
        print(f"  {DIM}... and {len(sim.club_players) - 15} more{RESET}")

    # ── 2. Player search ──────────────────────────────────────────────
    subheader("2 / 6  Player search  (MID, 18-21 years, €1M-€30M)")
    search_results = []
    for p in sim.all_players:
        if (p.position or "") != "MID":
            continue
        age = p.age or 0
        if not (18 <= age <= 21):
            continue
        mv = (p.market_value or 0) / 1e6
        if not (1 <= mv <= 30):
            continue
        search_results.append(p)
    search_results.sort(key=lambda x: x.market_value or 0, reverse=True)
    print(f"  Found {BOLD}{len(search_results)}{RESET} players matching filters\n")

    widths_s = [25, 20, 5, 14, 14, 10]
    print(f"  {BOLD}{table_row('Player', 'Team', 'Age', 'Market Value', 'Predicted', 'xGrowth', widths=widths_s)}{RESET}")
    print(f"  {'─' * 95}")
    for p in search_results[:10]:
        mv = p.market_value or 0
        pv = p.predicted_value
        xg = pct((pv / mv) - 1) if pv and mv > 0 else "—"
        print(f"  {table_row(p.name or '?', (p.team or '?')[:20], str(p.age or '?'), money(mv), money(pv), xg, widths=widths_s)}")

    # ── 3. Sell recommendations ───────────────────────────────────────
    subheader("3 / 6  Sell recommendations  (players past peak)")
    sell_candidates = []
    for p in sim.club_players:
        mv = p.market_value or 0
        pv = p.predicted_value or 0
        if mv > 0 and pv < mv:
            delta = mv - pv
            sell_candidates.append((p, delta, delta / mv))
    sell_candidates.sort(key=lambda x: x[1], reverse=True)

    if sell_candidates:
        widths_sell = [25, 6, 5, 14, 14, 12]
        print(f"  {BOLD}{table_row('Player', 'Pos', 'Age', 'Market Value', 'Predicted', 'Decline', widths=widths_sell)}{RESET}")
        print(f"  {'─' * 85}")
        for p, delta, dpct in sell_candidates[:8]:
            print(f"  {table_row(p.name or '?', p.position or '?', str(p.age or '?'), money(p.market_value), money(p.predicted_value), f'{RED}-{delta/1e6:.1f}M ({dpct:.0%}){RESET}', widths=widths_sell)}")
    else:
        print(f"  {GREEN}No players with predicted decline — squad is in great shape!{RESET}")

    # ── 4. Run simulation ─────────────────────────────────────────────
    subheader(f"4 / 6  Transfer simulation  (objective={objective}, speed={speed})")
    players_to_sell = [p.player_id for p, _, _ in sell_candidates[:3]] if sell_candidates else None

    t0 = time.time()
    result = sim.run(
        verbose=False,
        generate_summary=False,
        players_to_sell=players_to_sell,
        objective=objective,
        sim_speed=speed,
    )
    elapsed = time.time() - t0
    print(f"  Simulation completed in {elapsed:.1f}s\n")

    print(f"  {BOLD}Sales:{RESET}")
    for sp in result.players_sold:
        p = sp.player
        status = f"{GREEN}SOLD to {sp.destination_team}{RESET}" if sp.was_sold else f"{RED}NO BUYER{RESET}"
        print(f"    {p.name} ({p.position}) — {money(p.market_value)} → {status}")

    total_cost = sum((p.market_value or 0) for p in result.recommended_signings)
    total_predicted = sum((p.predicted_value or 0) for p in result.recommended_signings)
    roi = ((total_predicted - total_cost) / total_cost * 100) if total_cost > 0 else 0

    print(f"\n  {BOLD}Signings ({len(result.recommended_signings)} players):{RESET}")
    widths_buy = [25, 20, 6, 5, 14, 14, 10]
    print(f"  {BOLD}{table_row('Player', 'From', 'Pos', 'Age', 'Cost', 'Predicted 1yr', 'xGrowth', widths=widths_buy)}{RESET}")
    print(f"  {'─' * 100}")
    for p in result.recommended_signings:
        mv = p.market_value or 0
        pv = p.predicted_value or 0
        xg = pct((pv / mv) - 1) if mv > 0 else "—"
        print(f"  {table_row(p.name or '?', (p.team or '?')[:20], p.position or '?', str(p.age or '?'), money(mv), money(pv), xg, widths=widths_buy)}")

    print(f"\n  {BOLD}Financial summary:{RESET}")
    print(f"    Initial budget:      €{result.initial_budget}M")
    print(f"    Sales revenue:       €{result.sales_revenue}M")
    print(f"    Total budget:        €{result.total_budget}M")
    print(f"    Total spend:         {money(total_cost)}")
    print(f"    Predicted value:     {money(total_predicted)}")
    print(f"    Expected ROI:        {GREEN if roi > 0 else RED}{roi:+.1f}%{RESET}")
    print(f"    Formation:           {'-'.join(map(str, result.recommended_formation))}")

    # ── 5. Analytics ──────────────────────────────────────────────────
    subheader("5 / 6  Analytics: Top xGrowth players in the market")
    club_ids = {p.player_id for p in sim.club_players}
    pool = [
        p for p in sim.all_players
        if p.predicted_value is not None
        and (p.market_value or 0) > 0
        and not p.on_loan
        and p.player_id not in club_ids
    ]
    pool.sort(key=lambda p: (p.predicted_value / (p.market_value or 1)) - 1, reverse=True)

    widths_xg = [25, 20, 6, 5, 14, 14, 10]
    print(f"  {BOLD}{table_row('Player', 'Team', 'Pos', 'Age', 'Market Value', 'Predicted', 'xGrowth', widths=widths_xg)}{RESET}")
    print(f"  {'─' * 100}")
    for p in pool[:12]:
        mv = p.market_value or 0
        pv = p.predicted_value or 0
        xg = pct((pv / mv) - 1) if mv > 0 else "—"
        print(f"  {table_row(p.name or '?', (p.team or '?')[:20], p.position or '?', str(p.age or '?'), money(mv), money(pv), xg, widths=widths_xg)}")

    subheader("  Similar players for each signing")
    for s in result.recommended_signings[:3]:
        mv_s = s.market_value or 1
        xg_s = ((s.predicted_value or mv_s) / mv_s) - 1
        print(f"  {BOLD}{s.name}{RESET} ({s.position}, {money(s.market_value)}, xGrowth: {pct(xg_s)})")

        candidates = [
            p for p in pool
            if p.player_id != s.player_id
            and (p.position or "") == (s.position or "")
        ]
        scored = []
        for c in candidates:
            mv_c = c.market_value or 1
            val_sim = 1 - min(abs(mv_s - mv_c) / max(mv_s, mv_c), 1)
            age_sim = 1 - min(abs((s.age or 25) - (c.age or 25)) / 10, 1)
            xg_c = ((c.predicted_value or mv_c) / mv_c) - 1
            xg_sim = 1 - min(abs(xg_s - xg_c) / max(abs(xg_s) + 0.01, abs(xg_c) + 0.01), 1)
            score = 0.35 * val_sim + 0.25 * age_sim + 0.40 * xg_sim
            scored.append((c, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        for c, sc in scored[:3]:
            mv_c = c.market_value or 1
            xg_c = pct(((c.predicted_value or mv_c) / mv_c) - 1)
            print(f"    ↳ {c.name} ({c.team}, {money(c.market_value)}, xGrowth: {xg_c}) — similarity: {sc:.0%}")
        print()

    # ── 6. AI Summary preview ─────────────────────────────────────────
    subheader("6 / 6  AI Summary  (prompt preview — needs API key to generate)")
    print(f"  The system generates a structured report using ChatGPT/Claude/Gemini")
    print(f"  with detailed sale-by-sale and signing-by-signing reasoning.\n")
    print(f"  {DIM}To generate a real summary, set OPENAI_API_KEY and run:{RESET}")
    print(f"  {DIM}  result.generate_llm_summary(provider='openai'){RESET}")
    print()

    # ── Final ─────────────────────────────────────────────────────────
    header("DEMO COMPLETE")
    print(f"  {BOLD}Web demo:{RESET} python -m uvicorn api.main:app --reload")
    print(f"  Then open {CYAN}http://localhost:8000{RESET}\n")


def main():
    parser = argparse.ArgumentParser(description="Interactive demo of Team Transfers Simulator")
    parser.add_argument("--club", default="Athletic Club", help="Club name (default: Athletic Club)")
    parser.add_argument("--season", default="today", help="Season (default: today)")
    parser.add_argument("--speed", default="local", choices=["local", "fast", "standard"], help="Sim speed")
    parser.add_argument("--objective", default="smv", choices=["smv", "net_benefit", "roi", "value_growth", "growth_pct"])
    parser.add_argument("--budget", type=int, default=50, help="Transfer budget in millions")
    args = parser.parse_args()
    run_demo(
        club_name=args.club,
        season=args.season,
        speed=args.speed,
        objective=args.objective,
        budget=args.budget,
    )


if __name__ == "__main__":
    main()
