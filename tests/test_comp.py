import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraping.transfermarkt_competitions import TransfermarktCompetitionsScraper

scraper = TransfermarktCompetitionsScraper(season="2025-2026")
results = scraper.scrape_competition("argentine")

print(f"Total teams extracted: {len(results)}")
for r in results:
    if r.position == 1:
        print(r.to_dict())
