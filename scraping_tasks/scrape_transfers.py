#!/usr/bin/env python3
# scraping_tasks/scrape_transfers.py
"""
Task: Scrape transfer data from Transfermarkt.
Downloads transfer information for all teams in configured leagues.

Usage:
    python scraping_tasks/scrape_transfers.py
    python scraping_tasks/scrape_transfers.py --leagues laliga premier
    python scraping_tasks/scrape_transfers.py --season 2024-2025
"""
import sys
import argparse
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraping.transfermarkt_transfers import TransfermarktTransfersScraper


# Default leagues to scrape
DEFAULT_LEAGUES = [
    "laliga",
    "premier",
    "bundesliga",
    "seriea",
    "ligue1",
]


def main():
    parser = argparse.ArgumentParser(description="Scrape transfer data from Transfermarkt")
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
        default=2.0,
        help="Delay between requests in seconds (default: 2.0)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=True,
        help="Enable verbose output"
    )
    
    args = parser.parse_args()
    
    print(f"=== Transfermarkt Transfers Scraper ===")
    print(f"Leagues: {', '.join(args.leagues)}")
    print(f"Season: {args.season or 'current'}")
    print()
    
    scraper = TransfermarktTransfersScraper(
        season=args.season,
        delay=args.delay,
        verbose=args.verbose
    )
    
    results = scraper.run(leagues=args.leagues)
    
    # Summary
    total_transfers = 0
    for league_data in results.values():
        for transfers in league_data.values():
            total_transfers += len(transfers)
    
    print(f"\n=== Complete ===")
    print(f"Total transfers scraped: {total_transfers}")
    for league, teams_data in results.items():
        league_total = sum(len(t) for t in teams_data.values())
        print(f"  {league}: {league_total} transfers from {len(teams_data)} teams")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
