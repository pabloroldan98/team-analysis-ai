#!/usr/bin/env python3
# scraping_tasks/scrape_valuations.py
"""
Task: Scrape player valuation history from Transfermarkt.
Downloads valuation history for all players in configured leagues.

By default (--details), fetches the FULL valuation history for each player
from their individual market value page (e.g., /kylian-mbappe/marktwertverlauf/spieler/342229).

Use --no-details for faster scraping of only current market values
(from player profiles, no historical data).

NOTE: With --details, this task is slow due to visiting each player's page.

Usage:
    python scraping_tasks/scrape_valuations.py                     # Full history (default)
    python scraping_tasks/scrape_valuations.py --no-details        # Current values only, fast
    python scraping_tasks/scrape_valuations.py --leagues laliga
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
    
    # Details argument: default True, --no-details sets to False
    parser.add_argument(
        "--no-details",
        dest="details",
        action="store_false",
        help="Skip full valuation history (faster, only current market values)"
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
    
    mode_str = "Full valuation history" if args.details else "Current values only (fast)"
    
    print(f"=== Transfermarkt Valuations Scraper ===")
    print(f"Leagues: {', '.join(args.leagues)}")
    print(f"Season: {args.season or 'current'}")
    print(f"Mode: {mode_str}")
    if args.details:
        print(f"WARNING: This task may take a very long time with --details!")
    print()
    
    scraper = TransfermarktValuationsScraper(
        season=args.season,
        delay=args.delay,
        verbose=args.verbose
    )
    
    results = scraper.run(leagues=args.leagues, details=args.details)
    
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
