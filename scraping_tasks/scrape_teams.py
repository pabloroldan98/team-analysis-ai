#!/usr/bin/env python3
# scraping_tasks/scrape_teams.py
"""
Task: Scrape team data from Transfermarkt.
Downloads team information for configured leagues.

Usage:
    python scraping_tasks/scrape_teams.py
    python scraping_tasks/scrape_teams.py --leagues laliga premier
    python scraping_tasks/scrape_teams.py --season 2024-2025
"""
import sys
import argparse
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraping.transfermarkt_teams import TransfermarktTeamsScraper


# Default leagues to scrape
DEFAULT_LEAGUES = [
    "laliga",
    "premier",
    "bundesliga",
    "seriea",
    "ligue1",
]


def main():
    parser = argparse.ArgumentParser(description="Scrape team data from Transfermarkt")
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
    parser.add_argument(
        "--use-downloaded-data",
        action="store_true",
        default=False,
        help="Skip leagues whose JSON already exists and reuse downloaded data"
    )
    
    args = parser.parse_args()
    
    print(f"=== Transfermarkt Teams Scraper ===")
    print(f"Leagues: {', '.join(args.leagues)}")
    print(f"Season: {args.season or 'current'}")
    if args.use_downloaded_data:
        print(f"Mode: reuse downloaded data when available")
    print()
    
    scraper = TransfermarktTeamsScraper(
        season=args.season,
        delay=args.delay,
        verbose=args.verbose,
        use_downloaded_data=args.use_downloaded_data,
    )
    
    results = scraper.run(leagues=args.leagues)
    
    # Summary
    total_teams = sum(len(teams) for teams in results.values())
    print(f"\n=== Complete ===")
    print(f"Total teams scraped: {total_teams}")
    for league_key, teams in results.items():
        total_value = sum(t.total_market_value or 0 for t in teams)
        value_str = f"€{total_value/1_000_000_000:.2f}B" if total_value else "N/A"
        print(f"  {league_key}: {len(teams)} teams, {value_str}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
