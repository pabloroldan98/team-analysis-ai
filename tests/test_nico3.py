import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scraping.transfermarkt_players import TransfermarktPlayersScraper

scraper = TransfermarktPlayersScraper()
soup = scraper.fetch_page("https://www.transfermarkt.com/nico-gonzalez/profil/spieler/486031")
info_table = soup.select_one("div.info-table")
if info_table:
    labels = info_table.select("span.info-table__content--regular")
    for label_el in labels:
        value_el = label_el.find_next_sibling("span", class_="info-table__content--bold")
        if value_el:
            print(f"LABEL: {label_el.get_text(strip=True)} | VALUE: {value_el.get_text(strip=True)}")
