#!/usr/bin/env python3
# scraping_tasks/scrape_players.py
"""
Task: Scrape player data from Transfermarkt.
Downloads player information for all teams in configured leagues.

Usage:
    python scraping_tasks/scrape_players.py
    python scraping_tasks/scrape_players.py --leagues laliga premier
    python scraping_tasks/scrape_players.py --season 2024-2025
    python scraping_tasks/scrape_players.py --no-details  # Skip detailed player info (faster)
"""
import sys
import argparse
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraping.transfermarkt_players import TransfermarktPlayersScraper


# Default leagues to scrape
DEFAULT_LEAGUES = [
    "laliga",
    "premier",
    "bundesliga",
    "seriea",
    "ligue1",
]


def main():
    parser = argparse.ArgumentParser(description="Scrape player data from Transfermarkt")
    parser.add_argument(
        "--leagues",
        nargs="+",
        default=DEFAULT_LEAGUES,
        help="Leagues to scrape (default: top 5 European leagues)"
    )
    parser.add_argument(
        "--season",
        type=str,
        default=None,
        help="Season to scrape (e.g., 2024-2025). Defaults to current season."
    )
    parser.add_argument(
        "--no-details",
        action="store_false",
        dest="details",
        help="Skip detailed player information (faster)"
    )
    parser.set_defaults(details=True)
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Delay between requests in seconds (default: 0.0)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=True,
        help="Enable verbose output"
    )
    
    args = parser.parse_args()
    
    print(f"=== Transfermarkt Players Scraper ===")
    print(f"Leagues: {', '.join(args.leagues)}")
    print(f"Season: {args.season or 'current'}")
    print(f"Include details: {args.details}")
    print()
    
    scraper = TransfermarktPlayersScraper(
        season=args.season,
        delay=args.delay,
        verbose=args.verbose
    )
    
    results = scraper.run(leagues=args.leagues, include_details=args.details)
    
    # Summary
    total_players = 0
    for league_data in results.values():
        for players in league_data.values():
            total_players += len(players)
    
    print(f"\n=== Complete ===")
    print(f"Total players scraped: {total_players}")
    for league, teams_data in results.items():
        league_total = sum(len(p) for p in teams_data.values())
        print(f"  {league}: {league_total} players from {len(teams_data)} teams")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
