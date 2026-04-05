#!/usr/bin/env python3
# scraping_tasks/scrape_competitions.py
"""
Task: Scrape competition standings data from Transfermarkt.

Usage:
    python scraping_tasks/scrape_competitions.py
    python scraping_tasks/scrape_competitions.py --leagues laliga premier
    python scraping_tasks/scrape_competitions.py --season 2024-2025
"""
import sys
import argparse
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraping.transfermarkt_competitions import TransfermarktCompetitionsScraper

# Default leagues to scrape
DEFAULT_LEAGUES = [
    "laliga",
    "premier",
    "bundesliga",
    "seriea",
    "ligue1",
]


def main():
    parser = argparse.ArgumentParser(description="Scrape competition standings from Transfermarkt")
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
        help="Skip competitions whose JSON already exists and reuse downloaded data"
    )
    
    parser.add_argument(
        "--skip-scraped",
        action="store_true",
        default=False,
        help="Skip scraping for leagues that already have a saved JSON file"
    )
    
    args = parser.parse_args()
    
    if 'all' in args.leagues:
        from scraping.base_scraper import BaseScraper
        args.leagues = list(BaseScraper.LEAGUE_INFO.keys())
    
    print(f"=== Transfermarkt Competitions Scraper ===")
    print(f"Leagues: {', '.join(args.leagues)}")
    print(f"Season: {args.season or 'current'}")
    if args.use_downloaded_data:
        print(f"Mode: reuse downloaded data when available")
    print()
    
    scraper = TransfermarktCompetitionsScraper(
        season=args.season,
        delay=args.delay,
        verbose=args.verbose,
        use_downloaded_data=args.use_downloaded_data,
        skip_scraped=args.skip_scraped,
    )
    
    results = scraper.run(leagues=args.leagues)
    
    # Summary
    print(f"\n=== Complete ===")
    total_competitions = sum(len(standings) for standings in results.values())
    print(f"Total standings extracted: {total_competitions}")
    print(f"Leagues processed: {len(results)}")
    for league_key, standings in results.items():
        print(f"  {league_key}: {len(standings)} teams")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
