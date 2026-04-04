import json
from scraping.transfermarkt_competitions import TransfermarktCompetitionsScraper

scraper = TransfermarktCompetitionsScraper(season="2025-2026")
results = scraper.scrape_competition("argentine")

print(f"Total teams extracted: {len(results)}")
for r in results:
    if r.position == 1:
        print(r.to_dict())
