#!/usr/bin/env python3
# scraping_tasks/scrape_valuations.py
"""
Task: Scrape player valuation history from Transfermarkt.
Downloads valuation history for all players in configured leagues.

NOTE: This task is very slow due to the number of individual player pages.
Consider running with fewer leagues or limiting players.

Usage:
    python scraping_tasks/scrape_valuations.py
    python scraping_tasks/scrape_valuations.py --leagues laliga
    python scraping_tasks/scrape_valuations.py --season 2024-2025
"""
import sys
import argparse
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraping.transfermarkt_valuations import TransfermarktValuationsScraper


# Default leagues to scrape (fewer by default due to time)
DEFAULT_LEAGUES = [
    "laliga",
]


def main():
    parser = argparse.ArgumentParser(description="Scrape valuation data from Transfermarkt")
    parser.add_argument(
        "--leagues",
        nargs="+",
        default=DEFAULT_LEAGUES,
        help="Leagues to scrape (default: laliga only due to volume)"
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
    
    print(f"=== Transfermarkt Valuations Scraper ===")
    print(f"Leagues: {', '.join(args.leagues)}")
    print(f"Season: {args.season or 'current'}")
    print(f"WARNING: This task may take a very long time!")
    print()
    
    scraper = TransfermarktValuationsScraper(
        season=args.season,
        delay=args.delay,
        verbose=args.verbose
    )
    
    results = scraper.run(leagues=args.leagues)
    
    # Summary
    total_valuations = 0
    for league_data in results.values():
        for team_data in league_data.values():
            for player_valuations in team_data.values():
                total_valuations += len(player_valuations)
    
    print(f"\n=== Complete ===")
    print(f"Total valuations scraped: {total_valuations}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
