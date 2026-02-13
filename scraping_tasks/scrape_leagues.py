#!/usr/bin/env python3
# scraping_tasks/scrape_leagues.py
"""
Task: Scrape league data from Transfermarkt.
Downloads league information (without detailed team scraping).

Usage:
    python scraping_tasks/scrape_leagues.py
    python scraping_tasks/scrape_leagues.py --leagues laliga premier
    python scraping_tasks/scrape_leagues.py --season 2024-2025
"""
import sys
import argparse
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraping.transfermarkt_leagues import TransfermarktLeaguesScraper


# Default leagues to scrape
DEFAULT_LEAGUES = [
    "laliga",
    "premier",
    "bundesliga",
    "seriea",
    "ligue1",
]


def main():
    parser = argparse.ArgumentParser(description="Scrape league data from Transfermarkt")
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
    
    print(f"=== Transfermarkt Leagues Scraper ===")
    print(f"Leagues: {', '.join(args.leagues)}")
    print(f"Season: {args.season or 'current'}")
    if args.use_downloaded_data:
        print(f"Mode: reuse downloaded data when available")
    print()
    
    scraper = TransfermarktLeaguesScraper(
        season=args.season,
        delay=args.delay,
        verbose=args.verbose,
        use_downloaded_data=args.use_downloaded_data,
    )
    
    results = scraper.run(leagues=args.leagues)
    
    # Summary
    print(f"\n=== Complete ===")
    print(f"Total leagues scraped: {len(results)}")
    for league_key, league in results.items():
        value_str = f"€{league.total_market_value/1_000_000_000:.2f}B" if league.total_market_value else "N/A"
        print(f"  {league.name}: {league.num_teams} teams, {value_str}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
