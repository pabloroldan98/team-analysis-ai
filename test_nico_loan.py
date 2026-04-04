import json
from bs4 import BeautifulSoup
from scraping.transfermarkt_players import TransfermarktPlayersScraper

scraper = TransfermarktPlayersScraper(season="2025-2026")
soup = scraper.fetch_page("https://www.transfermarkt.com/nico-gonzalez/profil/spieler/486031")
info_table = soup.select_one("div.info-table")
if info_table:
    labels = info_table.select("span.info-table__content--regular")
    for label_el in labels:
        if "on loan from" in label_el.get_text(strip=True).lower() or "prestado de" in label_el.get_text(strip=True).lower():
            value_el = label_el.find_next_sibling("span", class_="info-table__content--bold")
            if value_el:
                print("Text:", value_el.get_text(strip=True))
                print("HTML:", value_el.decode_contents())
                
                a_tag = value_el.find("a")
                if a_tag:
                    print("Link:", a_tag.get("href"))
