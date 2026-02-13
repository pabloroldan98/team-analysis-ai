#!/usr/bin/env python3
# scraping_tasks/scrape_valuations.py
"""
Task: Scrape player valuation history from Transfermarkt.
Downloads valuation history for all players in configured leagues.

By default, fetches the FULL valuation history for each player via API.
Use --no-details for faster scraping of only current market values.

Usage:
    python scraping_tasks/scrape_valuations.py
    python scraping_tasks/scrape_valuations.py --no-details
    python scraping_tasks/scrape_valuations.py --leagues laliga
"""
import sys
import argparse
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraping.transfermarkt_valuations import TransfermarktValuationsScraper


# Default leagues to scrape
DEFAULT_LEAGUES = [
    "laliga",
    "premier",
    "bundesliga",
    "seriea",
    "ligue1",
]


def main():
    parser = argparse.ArgumentParser(description="Scrape valuation data from Transfermarkt")
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
    parser.add_argument(
        "--use-downloaded-data",
        action="store_true",
        default=False,
        help="Skip leagues whose JSON already exists and reuse downloaded data"
    )
    
    args = parser.parse_args()
    
    mode_str = "Full valuation history" if args.details else "Current values only"
    
    print(f"=== Transfermarkt Valuations Scraper ===")
    print(f"Leagues: {', '.join(args.leagues)}")
    print(f"Season: {args.season or 'current'}")
    print(f"Mode: {mode_str}")
    if args.use_downloaded_data:
        print(f"Reuse: downloaded data when available")
    print()
    
    scraper = TransfermarktValuationsScraper(
        season=args.season,
        delay=args.delay,
        verbose=args.verbose,
        use_downloaded_data=args.use_downloaded_data,
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
    for league, teams_data in results.items():
        league_total = sum(
            len(pv) for td in teams_data.values() for pv in td.values()
        )
        print(f"  {league}: {league_total} valuations from {len(teams_data)} teams")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
