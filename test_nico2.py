import json
from scraping.transfermarkt_players import TransfermarktPlayersScraper

scraper = TransfermarktPlayersScraper()
players = scraper.scrape_team_players('13')  # Atletico Madrid
for p in players:
    if "Nico" in p.name:
        print("Name:", p.name)
        print("Signed Date:", p.signed_date)
        print("Contract End:", p.contract_end_date)
