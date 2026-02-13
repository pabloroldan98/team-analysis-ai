#!/usr/bin/env python3
# scraping_tasks/scrape_all.py
"""
Task: Run all scrapers for complete data download.
This runs teams, players, and transfers scrapers.

NOTE: Valuations are excluded by default due to time requirements.
Use --include-valuations to include them.

Usage:
    python scraping_tasks/scrape_all.py
    python scraping_tasks/scrape_all.py --leagues laliga premier
    python scraping_tasks/scrape_all.py --include-valuations
"""
import sys
import argparse
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraping.transfermarkt_teams import TransfermarktTeamsScraper
from scraping.transfermarkt_players import TransfermarktPlayersScraper
from scraping.transfermarkt_transfers import TransfermarktTransfersScraper
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
    parser = argparse.ArgumentParser(description="Run all Transfermarkt scrapers")
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
        "--include-valuations",
        action="store_true",
        default=False,
        help="Include valuations scraper (very slow)"
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
    
    print(f"=== Transfermarkt Full Scrape ===")
    print(f"Leagues: {', '.join(args.leagues)}")
    print(f"Season: {args.season or 'current'}")
    print(f"Include valuations: {args.include_valuations}")
    if args.use_downloaded_data:
        print(f"Reuse: downloaded data when available")
    print()
    
    scraper_kwargs = {
        "season": args.season,
        "delay": args.delay,
        "verbose": args.verbose,
        "use_downloaded_data": args.use_downloaded_data,
    }
    
    # 1. Teams
    print("\n" + "="*50)
    print("STEP 1/3: Scraping Teams")
    print("="*50)
    teams_scraper = TransfermarktTeamsScraper(**scraper_kwargs)
    teams_results = teams_scraper.run(leagues=args.leagues)
    total_teams = sum(len(t) for t in teams_results.values())
    print(f"Teams scraped: {total_teams}")
    
    # 2. Players
    print("\n" + "="*50)
    print("STEP 2/3: Scraping Players")
    print("="*50)
    players_scraper = TransfermarktPlayersScraper(**scraper_kwargs)
    players_results = players_scraper.run(leagues=args.leagues)
    total_players = sum(len(p) for ld in players_results.values() for p in ld.values())
    print(f"Players scraped: {total_players}")
    
    # 3. Transfers
    print("\n" + "="*50)
    print("STEP 3/3: Scraping Transfers")
    print("="*50)
    transfers_scraper = TransfermarktTransfersScraper(**scraper_kwargs)
    transfers_results = transfers_scraper.run(leagues=args.leagues)
    total_transfers = sum(len(t) for ld in transfers_results.values() for t in ld.values())
    print(f"Transfers scraped: {total_transfers}")
    
    # Optional: Valuations
    if args.include_valuations:
        print("\n" + "="*50)
        print("BONUS: Scraping Valuations (this may take hours)")
        print("="*50)
        valuations_scraper = TransfermarktValuationsScraper(**scraper_kwargs)
        valuations_scraper.run(leagues=args.leagues)
    
    # Final summary
    print("\n" + "="*50)
    print("=== COMPLETE ===")
    print("="*50)
    print(f"Teams: {total_teams}")
    print(f"Players: {total_players}")
    print(f"Transfers: {total_transfers}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
