"""
Discover all leagues from Transfermarkt competition pages,
filter by minimum market value, and output configuration
ready to paste into scrapers.

Usage:
    python discover_leagues.py
"""
from __future__ import annotations

import os
import re
import json
import time
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
import tls_requests

# ── Configuration ───────────────────────────────────────────
BASE_URL = "https://www.transfermarkt.com"

COMPETITION_PAGES = {
    "europa":       "/wettbewerbe/europa",
    "amerika":      "/wettbewerbe/amerika",
    "asien":        "/wettbewerbe/asien",
    "afrika":       "/wettbewerbe/afrika",
    "europaJugend": "/wettbewerbe/europaJugend",
}

MAX_PAGES = 10
MIN_VALUE_M   = 100   # €100M for regular leagues
MIN_YOUTH_M   = 10    # €10M  for youth leagues

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Existing league IDs already configured in scrapers ─────────
EXISTING_IDS = {
    "ES1", "ES2", "GB1", "GB2", "L1", "L2", "IT1", "IT2",
    "FR1", "FR2", "NL1", "PO1", "SC1", "BE1", "TR1", "RU1",
    "UKR1", "GR1", "A1", "C1", "MLS1", "BRA1", "AR1N", "MEX1",
}

# League IDs to skip (playoffs, duplicate apertura/clausura, etc.)
SKIP_IDS = {
    "MEXA",  # Liga MX Apertura = same teams as MEX1
    "POMX",  # Liguilla Apertura = Liga MX playoff
    "CRPV",  # Costa Rica Apertura Play-Off
}


# ── Helpers ─────────────────────────────────────────────────
def parse_market_value(text: str) -> float:
    """Parse '€12.43bn', '€955.70m', '€75k' → float in millions."""
    if not text or text.strip() in ("", "-", "\\-"):
        return 0.0
    text = text.strip().replace("€", "").replace(",", ".")
    if text.endswith("bn"):
        return float(text[:-2]) * 1000
    if text.endswith("m"):
        return float(text[:-1])
    if text.endswith("k"):
        return float(text[:-1]) / 1000
    try:
        return float(text)
    except ValueError:
        return 0.0


def slugify(name: str, country: str) -> str:
    """Generate a scraper-friendly key from competition name + country."""
    # Use country_name if the league name is generic (e.g. "Ligue 1", "Premier League")
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")

    # Disambiguate generic names
    generic = {"ligue_1", "premier_league", "premier_liga", "super_league",
               "superliga", "primera_division", "bundesliga"}
    if slug in generic or slug.startswith("primera_division"):
        country_slug = re.sub(r"[^a-z0-9]+", "_", country.lower()).strip("_")
        slug = f"{slug}_{country_slug}"

    return slug


def fetch_page(_session, url: str) -> Optional[str]:
    """Fetch a page with retry logic using tls_requests.get()."""
    for attempt in range(3):
        try:
            resp = tls_requests.get(url, headers=HEADERS)
            if resp.status_code == 200:
                return resp.text
            if resp.status_code == 429:
                print(f"    429 – waiting 15s (attempt {attempt+1}/3)")
                time.sleep(15)
                continue
            print(f"    HTTP {resp.status_code} for {url}")
            return None
        except Exception as e:
            print(f"    Error: {e} (attempt {attempt+1}/3)")
            time.sleep(5)
    return None


def extract_leagues(html: str) -> List[dict]:
    """Extract league data from an HTML competition page.

    The main data table has ``class="items"`` and each league is a
    ``<tr class="odd">`` or ``<tr class="even">`` row with 8-10 cells.
    The league link is inside an ``inline-table``, and the market value
    is in the last ``<td class="rechts hauptlink">``.
    """
    soup = BeautifulSoup(html, "html.parser")
    leagues: List[dict] = []

    # Find the main data table (class="items")
    main_table = soup.find("table", class_="items")
    if not main_table:
        return leagues

    seen_ids: set = set()

    for row in main_table.find_all("tr", class_=re.compile(r"^(odd|even)$")):
        # Find competition link in the row
        link = row.find("a", href=re.compile(r"/startseite/wettbewerb/"))
        if not link:
            continue

        href = link.get("href", "")
        m = re.search(r"/wettbewerb/([A-Za-z0-9]+)$", href)
        if not m:
            continue

        league_id = m.group(1)
        if league_id in seen_ids:
            continue
        seen_ids.add(league_id)

        # Get league name (prefer the text-only link, not the image link)
        name = ""
        for a_tag in row.find_all("a", href=re.compile(r"/wettbewerb/")):
            txt = a_tag.get_text(strip=True)
            if txt:
                name = txt
                break
        if not name:
            continue

        # Country from flag image
        country = ""
        flag_img = row.find("img", class_=re.compile(r"flag"))
        if not flag_img:
            # Try any img with a country title
            for img in row.find_all("img"):
                title = img.get("title", "")
                if title and "logo" not in img.get("class", []):
                    country = title
                    break
        else:
            country = flag_img.get("title", "")

        # Market value: look for <td class="rechts hauptlink">
        value_m = 0.0
        value_cell = row.find("td", class_="rechts")
        if value_cell:
            value_m = parse_market_value(value_cell.get_text(strip=True))
        else:
            # Fallback: last cell
            cells = row.find_all("td")
            if cells:
                value_m = parse_market_value(cells[-1].get_text(strip=True))

        leagues.append({
            "name": name,
            "country": country,
            "league_id": league_id,
            "url_path": href,
            "value_m": value_m,
        })

    return leagues


# ── Main ────────────────────────────────────────────────────
def main():
    all_leagues: Dict[str, dict] = {}  # league_id → data

    for region, base_path in COMPETITION_PAGES.items():
        is_youth = region == "europaJugend"
        min_value = MIN_YOUTH_M if is_youth else MIN_VALUE_M

        print(f"\n{'='*60}")
        print(f"Region: {region}  (min €{min_value}M)")
        print(f"{'='*60}")

        for page in range(1, MAX_PAGES + 1):
            url = f"{BASE_URL}{base_path}"
            if page > 1:
                url += f"?page={page}"

            print(f"  Page {page}: {url}")
            html = fetch_page(None, url)
            if not html:
                print("    → no content, stopping region")
                break

            leagues = extract_leagues(html)
            if not leagues:
                print("    -> no leagues found, stopping region")
                break

            above_threshold = 0
            new = 0
            for lg in leagues:
                lid = lg["league_id"]
                if lid in SKIP_IDS:
                    continue
                if lid not in all_leagues:
                    all_leagues[lid] = {**lg, "region": region, "is_youth": is_youth}
                    new += 1
                if lg["value_m"] >= min_value:
                    above_threshold += 1

            print(f"    -> {len(leagues)} leagues, {new} new, "
                  f"{above_threshold} >= EUR{min_value}M")

            # Early stop: no new leagues means page repeats
            if new == 0:
                print("    -> no new leagues, stopping region")
                break

            # Early stop: if no league on this page meets the threshold, stop
            if above_threshold == 0:
                print("    -> all below threshold, stopping region")
                break

            time.sleep(2)  # Be polite

    # ── Filter ──────────────────────────────────────────────
    filtered: Dict[str, dict] = {}
    for lid, data in all_leagues.items():
        threshold = MIN_YOUTH_M if data["is_youth"] else MIN_VALUE_M
        if data["value_m"] >= threshold:
            filtered[lid] = data

    # ── Sort by value descending ────────────────────────────
    sorted_leagues = sorted(filtered.values(), key=lambda x: x["value_m"], reverse=True)

    # ── Print summary ───────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"QUALIFYING LEAGUES: {len(sorted_leagues)}")
    print(f"  Already configured: {sum(1 for l in sorted_leagues if l['league_id'] in EXISTING_IDS)}")
    print(f"  NEW to add:         {sum(1 for l in sorted_leagues if l['league_id'] not in EXISTING_IDS)}")
    print(f"{'='*60}\n")

    new_leagues = []

    for lg in sorted_leagues:
        lid = lg["league_id"]
        marker = "  OK " if lid in EXISTING_IDS else "  NEW"
        youth  = " [YOUTH]" if lg["is_youth"] else ""
        print(f"{marker} {lg['name']:45s} | {lg['country']:20s} | "
              f"{lid:8s} | EUR{lg['value_m']:>10,.1f}M{youth}")
        if lid not in EXISTING_IDS:
            new_leagues.append(lg)

    # ── Generate config snippets ────────────────────────────
    if new_leagues:
        print(f"\n{'='*60}")
        print("LEAGUE_INFO entries to add:")
        print(f"{'='*60}")

        # Map of known country → tier
        COUNTRY_TIER = {
            "Denmark": 1, "Czech Republic": 1, "Poland": 1, "Norway": 1,
            "Serbia": 1, "Romania": 1, "Sweden": 1, "Croatia": 1,
            "Bulgaria": 1, "Israel": 1, "Cyprus": 1, "Hungary": 1,
            "Azerbaijan": 1, "Slovakia": 1, "Colombia": 1, "Uruguay": 1,
            "Chile": 1, "Ecuador": 1, "Peru": 1, "Paraguay": 1,
            "Saudi Arabia": 1, "Qatar": 1, "United Arab Emirates": 1,
            "Japan": 1, "China": 1, "Iran": 1, "Korea, South": 1,
            "Australia": 1, "Egypt": 1, "South Africa": 1, "Morocco": 1,
            "Italy": 2, "Germany": 2, "Portugal": 2,
        }

        for lg in new_leagues:
            key = slugify(lg["name"], lg["country"])
            country = lg["country"]
            tier = COUNTRY_TIER.get(country, 1)
            if lg["is_youth"]:
                tier = "youth"
            print(f'        "{key}": {{"name": "{lg["name"]}", '
                  f'"country": "{country}", "tier": {tier}, '
                  f'"id": "{lg["league_id"]}", '
                  f'"url": "{lg["url_path"]}"}},')

    # Save results to JSON
    output = {
        "all": sorted_leagues,
        "new": new_leagues,
    }
    output_path = os.path.join("data", "json", "discovered_leagues.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to discovered_leagues.json")


if __name__ == "__main__":
    main()
