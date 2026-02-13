#!/usr/bin/env python3
# scraping_tasks/scrape_transfers.py
"""
Task: Scrape transfer data from Transfermarkt.

By default (--details), iterates over all players of all teams in the
configured leagues (using the players scraper) and fetches each player's
FULL transfer history via the Transfermarkt API.  This yields every
historical transfer for every squad member, including market_value_at_transfer.

With --no-details, falls back to scraping only the season transfer page
per team (faster, but limited to that season's movements and no
market_value_at_transfer).

Usage:
    python scraping_tasks/scrape_transfers.py
    python scraping_tasks/scrape_transfers.py --no-details
    python scraping_tasks/scrape_transfers.py --leagues laliga premier
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
        "--no-details",
        dest="details",
        action="store_false",
        help="Skip full player transfer history — only scrape current season transfer pages (faster)"
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

    mode_str = "Full player history (all squad players)" if args.details else "Season transfer pages only"

    print(f"=== Transfermarkt Transfers Scraper ===")
    print(f"Leagues: {', '.join(args.leagues)}")
    print(f"Season: {args.season or 'current'}")
    print(f"Mode: {mode_str}")
    if args.use_downloaded_data:
        print(f"Reuse: downloaded data when available")
    print()

    scraper = TransfermarktTransfersScraper(
        season=args.season,
        delay=args.delay,
        verbose=args.verbose,
        use_downloaded_data=args.use_downloaded_data,
    )

    results = scraper.run(leagues=args.leagues, details=args.details)

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
