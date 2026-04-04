#!/usr/bin/env python3
# scraping_tasks/scrape_injuries.py
"""
Task: Scrape player injury history from Transfermarkt.

For every player of every team in the configured leagues, fetches the
FULL injury history from the detailed injury page (with pagination).

Usage:
    python scraping_tasks/scrape_injuries.py
    python scraping_tasks/scrape_injuries.py --leagues laliga premier
    python scraping_tasks/scrape_injuries.py --use-past-players-ids --season 2024-2025
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scraping.transfermarkt_injuries import TransfermarktInjuriesScraper


DEFAULT_LEAGUES = [
    "laliga",
    "premier",
    "bundesliga",
    "seriea",
    "ligue1",
]


def main():
    parser = argparse.ArgumentParser(description="Scrape player injury history from Transfermarkt")
    parser.add_argument(
        "--leagues",
        nargs="+",
        default=DEFAULT_LEAGUES,
        help="Leagues to scrape (default: top 5 European leagues)",
    )
    parser.add_argument(
        "--season",
        type=str,
        default=None,
        help="Season to scrape (e.g., 2024-2025). Defaults to current season.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Delay between requests in seconds (default: 0.0)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=True,
        help="Enable verbose output",
    )
    parser.add_argument(
        "--use-downloaded-data",
        action="store_true",
        default=False,
        help="Skip players whose injury data already exists and reuse downloaded data",
    )
    parser.add_argument(
        "--use-past-players-ids",
        action="store_true",
        help="Load players_by_league from players_all files instead of scraping players",
    )

    args = parser.parse_args()

    if "all" in args.leagues:
        from scraping.base_scraper import BaseScraper
        args.leagues = list(BaseScraper.LEAGUE_INFO.keys())

    print("=== Transfermarkt Injuries Scraper ===")
    print(f"Leagues: {', '.join(args.leagues)}")
    print(f"Season: {args.season or 'current'}")
    if args.use_downloaded_data:
        print("Reuse: downloaded data when available")
    print()

    scraper = TransfermarktInjuriesScraper(
        season=args.season,
        delay=args.delay,
        verbose=args.verbose,
        use_downloaded_data=args.use_downloaded_data,
    )

    players_by_league = None
    if args.use_past_players_ids:
        from scraping.utils.helpers import load_players_by_league_from_files
        print("Loading players from existing files (--use-past-players-ids)...")
        players_by_league = load_players_by_league_from_files(args.season)
        if players_by_league is None:
            print("Failed to load players from files. Falling back to scraping.")

    results = scraper.run(leagues=args.leagues, players_by_league=players_by_league)

    # Summary
    total_injuries = 0
    for league_data in results.values():
        for injuries in league_data.values():
            total_injuries += len(injuries)

    print(f"\n=== Complete ===")
    print(f"Total injuries scraped: {total_injuries}")
    for league, teams_data in results.items():
        league_total = sum(len(t) for t in teams_data.values())
        print(f"  {league}: {league_total} injuries from {len(teams_data)} teams")

    return 0


if __name__ == "__main__":
    sys.exit(main())
