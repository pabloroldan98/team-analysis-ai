import os
import sys
import argparse
import glob
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraping.base_scraper import BaseScraper
from scraping.transfermarkt_leagues import TransfermarktLeaguesScraper
from scraping.transfermarkt_teams import TransfermarktTeamsScraper
from scraping.transfermarkt_players import TransfermarktPlayersScraper
from scraping.transfermarkt_transfers import TransfermarktTransfersScraper
from scraping.transfermarkt_competitions import TransfermarktCompetitionsScraper
from scraping.transfermarkt_valuations import TransfermarktValuationsScraper
from scraping.transfermarkt_injuries import TransfermarktInjuriesScraper

from common.data_paths import dataset_dir_for_entity


def cleanup_temp_jsons(entity: str, season: str):
    """Deletes temporary JSON files for a specific entity and season EXCEPT *_all_* and discovered_leagues.json"""
    print(f"\nCleaning up individual {entity} JSON files for season {season} to save space...")
    try:
        count = 0
        entity_dir = dataset_dir_for_entity(entity)
        for path in glob.glob(str(entity_dir / f"{entity}_*{season}*.json")):
            filename = os.path.basename(path)
            # Skip _all_ files and discovered_leagues
            if "_all_" in filename or "discovered_leagues" in filename:
                continue
            try:
                os.remove(path)
                count += 1
            except OSError:
                pass
        print(f"Cleanup complete. Deleted {count} temporary JSON files.")
    except Exception as e:
        print(f"Error during cleanup: {e}")

def main():
    parser = argparse.ArgumentParser(description="Run full sequential scrape in a single process")
    parser.add_argument(
        "--season",
        type=str,
        required=True,
        help="Season to scrape (e.g. 2024-2025)"
    )
    parser.add_argument(
        "--exclude-valuations",
        action="store_true",
        help="Skip the valuations scraper"
    )
    parser.add_argument(
        "--exclude-injuries",
        action="store_true",
        help="Skip the injuries scraper"
    )
    parser.add_argument(
        "--use-players-from-file",
        action="store_true",
        help="Load players_by_league from players_all files instead of scraping players"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Delay between requests in seconds"
    )

    args = parser.parse_args()

    print(f"=== STARTING FULL SCRAPE FOR SEASON {args.season} ===")

    leagues = list(BaseScraper.LEAGUE_INFO.keys())

    scraper_kwargs = {
        "season": args.season,
        "delay": args.delay,
        "verbose": True,
        "use_downloaded_data": True,
    }

    # 1. Competitions
    print("\n" + "="*50)
    print("STEP 1: Scraping Competitions")
    print("="*50)
    competitions_scraper = TransfermarktCompetitionsScraper(**scraper_kwargs)
    competitions_scraper.run(leagues=leagues)
    cleanup_temp_jsons("competitions", args.season)

    # 2. Leagues
    print("\n" + "="*50)
    print("STEP 2: Scraping Leagues")
    print("="*50)
    leagues_scraper = TransfermarktLeaguesScraper(**scraper_kwargs)
    leagues_scraper.run(leagues=leagues)
    cleanup_temp_jsons("leagues", args.season)

    # 3. Teams
    print("\n" + "="*50)
    print("STEP 3: Scraping Teams")
    print("="*50)
    teams_scraper = TransfermarktTeamsScraper(**scraper_kwargs)
    teams_scraper.run(leagues=leagues)
    cleanup_temp_jsons("teams", args.season)

    # 4. Players
    print("\n" + "="*50)
    print("STEP 4: Scraping Players (Caching IDs for Transfers & Valuations)")
    print("="*50)
    
    players_by_league = None
    if args.use_players_from_file:
        from scraping.utils.helpers import load_players_by_league_from_files
        print("Loading players from existing files (--use-players-from-file)...")
        players_by_league = load_players_by_league_from_files(args.season)
        if players_by_league is None:
            print("Failed to load players from files. Falling back to scraping.")
            
    players_scraper = TransfermarktPlayersScraper(**scraper_kwargs)
    if players_by_league is None:
        players_by_league = players_scraper.run(leagues=leagues)
    else:
        players_by_league = players_scraper.run(leagues=leagues, players_by_league=players_by_league)
        
    cleanup_temp_jsons("players", args.season)

    # 5. Transfers (Reuses players_by_league)
    print("\n" + "="*50)
    print("STEP 5: Scraping Transfers")
    print("="*50)
    transfers_scraper = TransfermarktTransfersScraper(**scraper_kwargs)
    transfers_scraper.run(leagues=leagues, players_by_league=players_by_league)
    cleanup_temp_jsons("transfers", args.season)

    # 6. Valuations (Reuses players_by_league)
    if not args.exclude_valuations:
        print("\n" + "="*50)
        print("STEP 6: Scraping Valuations")
        print("="*50)
        valuations_scraper = TransfermarktValuationsScraper(**scraper_kwargs)
        valuations_scraper.run(leagues=leagues, players_by_league=players_by_league)
        cleanup_temp_jsons("valuations", args.season)
    else:
        print("\nSkipping valuations scraper as requested.")

    # 7. Injuries (Reuses players_by_league)
    if not args.exclude_injuries:
        print("\n" + "="*50)
        print("STEP 7: Scraping Injuries")
        print("="*50)
        injuries_scraper = TransfermarktInjuriesScraper(**scraper_kwargs)
        injuries_scraper.run(leagues=leagues, players_by_league=players_by_league)
        cleanup_temp_jsons("injuries", args.season)
    else:
        print("\nSkipping injuries scraper as requested.")

    print("\n" + "="*50)
    print(f"=== COMPLETE SCRAPING FINISHED FOR {args.season} ===")
    print("="*50)

if __name__ == "__main__":
    main()
