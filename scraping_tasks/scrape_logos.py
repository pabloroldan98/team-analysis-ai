#!/usr/bin/env python3
# scraping_tasks/scrape_logos.py
"""
Task: Scrape and download team logos from Transfermarkt.
Downloads logo images for all teams in configured leagues.

Usage:
    python scraping_tasks/scrape_logos.py
    python scraping_tasks/scrape_logos.py --leagues laliga premier
    python scraping_tasks/scrape_logos.py --season 2024-2025
"""
import sys
import argparse
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraping.transfermarkt_logos import TransfermarktLogosScraper


# Default leagues to scrape
DEFAULT_LEAGUES = [
    "laliga",
    "premier",
    "bundesliga",
    "seriea",
    "ligue1",
]


def main():
    parser = argparse.ArgumentParser(description="Scrape team logos from Transfermarkt")
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
    
    print(f"=== Transfermarkt Logos Scraper ===")
    print(f"Leagues: {', '.join(args.leagues)}")
    print(f"Season: {args.season or 'current'}")
    print()
    
    scraper = TransfermarktLogosScraper(
        season=args.season,
        delay=args.delay,
        verbose=args.verbose
    )
    
    results = scraper.run(leagues=args.leagues)
    
    # Summary
    total = sum(len(r) for r in results.values())
    downloaded = sum(1 for league_data in results.values() for r in league_data if r.get("local_path"))
    
    print(f"\n=== Complete ===")
    print(f"Total logos: {total}")
    print(f"Successfully downloaded: {downloaded}")
    for league, data in results.items():
        downloaded_count = sum(1 for r in data if r.get("local_path"))
        print(f"  {league}: {downloaded_count}/{len(data)} logos")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
