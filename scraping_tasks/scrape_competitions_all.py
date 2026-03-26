import sys
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraping.transfermarkt_competitions import TransfermarktCompetitionsScraper
import scraping_tasks.combine_data as combine_data

ALL_LEAGUES = [
    # Europe – Tier 1
    "laliga", "premier", "seriea", "bundesliga", "ligue1", "liga_portugal", 
    "turkish", "eredivisie", "russian", "belgian", "greek", "danish", 
    "ukrainian", "czech", "polish", "swiss", "scottish", "austrian", 
    "norwegian", "serbian", "romanian", "swedish", "croatian", "bulgarian", 
    "israeli", "cypriot", "hungarian", "azerbaijani", "slovak",
    # Europe – Tier 2
    "segunda", "championship", "serieb", "bundesliga2", "ligue2", 
    "liga_portugal2", "turkish2", "dutch2", "belgian2", "russian2",
    # Europe – Tier 3
    "leagueone", "bundesliga3", "seriec1", "seriec2", "seriec3", 
    "primeraref1", "primeraref2",
    # Europe – Tier 4
    "leaguetwo",
    # Americas – Tier 1
    "brazilian", "mls", "argentine", "mexican", "colombian", 
    "uruguayan", "chilean", "ecuadorian", "peruvian", "paraguayan",
    # Americas – Tier 2
    "brazilian2", "argentine2",
    # Asia – Tier 1
    "saudi", "qatari", "emirati", "japanese", "chinese", 
    "iranian", "korean", "australian",
    # Asia – Tier 2
    "japanese2",
    # Africa – Tier 1
    "egyptian", "south_african", "moroccan",
    # Youth
    "primavera1", "u19_bundesliga_a", "u19_bundesliga_h", "liga_revelacao"
]

def main():
    parser = argparse.ArgumentParser(description="Scrape ALL competition standings from Transfermarkt")
    parser.add_argument(
        "--season", 
        type=int, 
        required=True, 
        help="Season start year (e.g. 2024)"
    )
    parser.add_argument(
        "--delay", 
        type=float, 
        default=2.0, 
        help="Base delay between requests in seconds"
    )
    parser.add_argument(
        "--verbose", 
        action="store_true", 
        help="Enable detailed logging"
    )
    parser.add_argument(
        "--use-downloaded-data", 
        action="store_true", 
        help="Use existing JSON data to avoid re-scraping already processed leagues/teams"
    )
    parser.add_argument(
        "--combine", 
        action="store_true", 
        help="Run combine_data.py to generate _all_ file after scraping"
    )
    
    args = parser.parse_args()

    scraper = TransfermarktCompetitionsScraper(
        season=args.season,
        delay=args.delay,
        verbose=args.verbose,
        use_downloaded_data=args.use_downloaded_data
    )

    print(f"============================================================")
    print(f"Starting complete scraping of competitions for season {args.season}...")
    print(f"Total leagues to scrape: {len(ALL_LEAGUES)}")
    print(f"============================================================")

    results = scraper.run(leagues=ALL_LEAGUES)

    total_competitions = sum(len(standings) for standings in results.values())
    print("\n============================================================")
    print("Scraping Completed")
    print(f"Leagues processed: {len(results)}")
    print(f"Total standings extracted: {total_competitions}")
    print("============================================================\n")

    if args.combine:
        print("Combining into _all_ file...")
        season_str = f"{args.season}-{args.season+1}"
        sys.argv = ['combine_data.py', '--entity', 'competitions', '--season', season_str]
        combine_data.main()
        print("Done.")

if __name__ == "__main__":
    main()