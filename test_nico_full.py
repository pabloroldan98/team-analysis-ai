import json
from scraping.transfermarkt_players import TransfermarktPlayersScraper

scraper = TransfermarktPlayersScraper(season="2025-2026")
players = scraper.scrape_team_players("13", "Atlético de Madrid")

nico = None
for p in players:
    if p.player_id == "486031":
        nico = p
        break

if nico:
    nico = scraper.scrape_player_details("486031", nico)
    print(json.dumps(nico.to_dict(), indent=2, ensure_ascii=False))
else:
    print("Nico not found in team squad.")