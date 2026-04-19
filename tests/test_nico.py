import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraping.transfermarkt_players import TransfermarktPlayersScraper

scraper = TransfermarktPlayersScraper()
player = scraper.scrape_player_details('486031')
print("Signed Date:", player.signed_date)
print("Contract End:", player.contract_end_date)
