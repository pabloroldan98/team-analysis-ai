import json
from scraping.transfermarkt_players import TransfermarktPlayersScraper

scraper = TransfermarktPlayersScraper()
player = scraper.scrape_player_details('28003') # Messi (not on loan)
print("Name:", player.name)
print("Signed Date:", player.signed_date)
print("Contract End:", player.contract_end_date)
