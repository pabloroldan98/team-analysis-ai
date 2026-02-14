# scraping/base_scraper.py
"""
Base scraper class with common functionality for Transfermarkt scraping.
"""
from __future__ import annotations

import json
import os
import re
import time
import random
import hashlib
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Any

import requests
from bs4 import BeautifulSoup

try:
    import tls_requests
    USE_TLS = True
except ImportError:
    USE_TLS = False

from unidecode import unidecode


ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data" / "json"

# Rotating header pool
HEADER_POOL = [
    # Chrome / Windows 10 (older)
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )
    },
    # Chrome / Windows 10 (newer)
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    },
    # Chrome / Windows 11
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    },
    # Chrome / macOS
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    },
    # Chrome / macOS Sonoma
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0.0.0 Safari/537.36"
        )
    },
    # Chrome / Linux
    {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    },
    # Firefox / Windows
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) "
            "Gecko/20100101 Firefox/121.0"
        )
    },
    # Firefox / macOS
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.3; rv:122.0) "
            "Gecko/20100101 Firefox/122.0"
        )
    },
    # Safari / macOS Ventura
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.1 Safari/605.1.15"
        )
    },
    # Safari / macOS Sonoma
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.3 Safari/605.1.15"
        )
    },
    # Edge / Windows
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
        )
    },
    # Opera / Windows
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0"
        )
    },
]


def pick_headers() -> dict:
    """Pick a random header from the pool."""
    return random.choice(HEADER_POOL).copy()


class BaseScraper:
    """Base class for Transfermarkt scrapers."""
    
    BASE_URL = "https://www.transfermarkt.com"
    
    # ─── Single source of truth: metadata + URL for every league ───
    # Each entry: name, country, tier, id (Transfermarkt), url (path)
    LEAGUE_INFO = {
        # ── Europe – Tier 1 ──────────────────────────────────────
        "laliga":         {"name": "LaLiga",                 "country": "Spain",         "tier": 1, "id": "ES1",  "url": "/laliga/startseite/wettbewerb/ES1"},
        "premier":        {"name": "Premier League",         "country": "England",       "tier": 1, "id": "GB1",  "url": "/premier-league/startseite/wettbewerb/GB1"},
        "seriea":         {"name": "Serie A",                "country": "Italy",         "tier": 1, "id": "IT1",  "url": "/serie-a/startseite/wettbewerb/IT1"},
        "bundesliga":     {"name": "Bundesliga",             "country": "Germany",       "tier": 1, "id": "L1",   "url": "/bundesliga/startseite/wettbewerb/L1"},
        "ligue1":         {"name": "Ligue 1",                "country": "France",        "tier": 1, "id": "FR1",  "url": "/ligue-1/startseite/wettbewerb/FR1"},
        "liga_portugal":  {"name": "Liga Portugal",          "country": "Portugal",      "tier": 1, "id": "PO1",  "url": "/liga-portugal/startseite/wettbewerb/PO1"},
        "turkish":        {"name": "Süper Lig",              "country": "Turkey",        "tier": 1, "id": "TR1",  "url": "/super-lig/startseite/wettbewerb/TR1"},
        "eredivisie":     {"name": "Eredivisie",             "country": "Netherlands",   "tier": 1, "id": "NL1",  "url": "/eredivisie/startseite/wettbewerb/NL1"},
        "russian":        {"name": "Russian Premier League", "country": "Russia",        "tier": 1, "id": "RU1",  "url": "/premier-liga/startseite/wettbewerb/RU1"},
        "belgian":        {"name": "Jupiler Pro League",     "country": "Belgium",       "tier": 1, "id": "BE1",  "url": "/jupiler-pro-league/startseite/wettbewerb/BE1"},
        "greek":          {"name": "Super League Greece",    "country": "Greece",        "tier": 1, "id": "GR1",  "url": "/super-league-1/startseite/wettbewerb/GR1"},
        "danish":         {"name": "Superliga",              "country": "Denmark",       "tier": 1, "id": "DK1",  "url": "/superliga/startseite/wettbewerb/DK1"},
        "ukrainian":      {"name": "Ukrainian Premier League","country": "Ukraine",      "tier": 1, "id": "UKR1", "url": "/premier-liga/startseite/wettbewerb/UKR1"},
        "czech":          {"name": "Chance Liga",            "country": "Czech Republic","tier": 1, "id": "TS1",  "url": "/chance-liga/startseite/wettbewerb/TS1"},
        "polish":         {"name": "Ekstraklasa",            "country": "Poland",        "tier": 1, "id": "PL1",  "url": "/pko-bp-ekstraklasa/startseite/wettbewerb/PL1"},
        "swiss":          {"name": "Swiss Super League",     "country": "Switzerland",   "tier": 1, "id": "C1",   "url": "/super-league/startseite/wettbewerb/C1"},
        "scottish":       {"name": "Scottish Premiership",   "country": "Scotland",      "tier": 1, "id": "SC1",  "url": "/scottish-premiership/startseite/wettbewerb/SC1"},
        "austrian":       {"name": "Austrian Bundesliga",    "country": "Austria",       "tier": 1, "id": "A1",   "url": "/bundesliga/startseite/wettbewerb/A1"},
        "norwegian":      {"name": "Eliteserien",            "country": "Norway",        "tier": 1, "id": "NO1",  "url": "/eliteserien/startseite/wettbewerb/NO1"},
        "serbian":        {"name": "Super liga Srbije",      "country": "Serbia",        "tier": 1, "id": "SER1", "url": "/super-liga-srbije/startseite/wettbewerb/SER1"},
        "romanian":       {"name": "SuperLiga",              "country": "Romania",       "tier": 1, "id": "RO1",  "url": "/superliga/startseite/wettbewerb/RO1"},
        "swedish":        {"name": "Allsvenskan",            "country": "Sweden",        "tier": 1, "id": "SE1",  "url": "/allsvenskan/startseite/wettbewerb/SE1"},
        "croatian":       {"name": "SuperSport HNL",         "country": "Croatia",       "tier": 1, "id": "KR1",  "url": "/supersport-hnl/startseite/wettbewerb/KR1"},
        "bulgarian":      {"name": "efbet Liga",             "country": "Bulgaria",      "tier": 1, "id": "BU1",  "url": "/efbet-liga/startseite/wettbewerb/BU1"},
        "israeli":        {"name": "Ligat ha'Al",            "country": "Israel",        "tier": 1, "id": "ISR1", "url": "/ligat-haal/startseite/wettbewerb/ISR1"},
        "cypriot":        {"name": "Cyprus League",          "country": "Cyprus",        "tier": 1, "id": "ZYP1", "url": "/cyprus-league/startseite/wettbewerb/ZYP1"},
        "hungarian":      {"name": "NB I.",                  "country": "Hungary",       "tier": 1, "id": "UNG1", "url": "/nemzeti-bajnoksag/startseite/wettbewerb/UNG1"},
        "azerbaijani":    {"name": "Premyer Liqa",           "country": "Azerbaijan",    "tier": 1, "id": "AZ1",  "url": "/premyer-liqa/startseite/wettbewerb/AZ1"},
        "slovak":         {"name": "Niké Liga",              "country": "Slovakia",      "tier": 1, "id": "SLO1", "url": "/nike-liga/startseite/wettbewerb/SLO1"},
        # ── Europe – Tier 2 ──────────────────────────────────────
        "segunda":        {"name": "LaLiga 2",               "country": "Spain",         "tier": 2, "id": "ES2",  "url": "/laliga2/startseite/wettbewerb/ES2"},
        "championship":   {"name": "Championship",           "country": "England",       "tier": 2, "id": "GB2",  "url": "/championship/startseite/wettbewerb/GB2"},
        "serieb":         {"name": "Serie B",                "country": "Italy",         "tier": 2, "id": "IT2",  "url": "/serie-b/startseite/wettbewerb/IT2"},
        "bundesliga2":    {"name": "2. Bundesliga",          "country": "Germany",       "tier": 2, "id": "L2",   "url": "/2-bundesliga/startseite/wettbewerb/L2"},
        "ligue2":         {"name": "Ligue 2",                "country": "France",        "tier": 2, "id": "FR2",  "url": "/ligue-2/startseite/wettbewerb/FR2"},
        "liga_portugal2": {"name": "Liga Portugal 2",        "country": "Portugal",      "tier": 2, "id": "PO2",  "url": "/liga-portugal-2/startseite/wettbewerb/PO2"},
        "turkish2":       {"name": "1. Lig",                 "country": "Turkey",        "tier": 2, "id": "TR2",  "url": "/1-lig/startseite/wettbewerb/TR2"},
        "dutch2":         {"name": "Keuken Kampioen Divisie","country": "Netherlands",   "tier": 2, "id": "NL2",  "url": "/keuken-kampioen-divisie/startseite/wettbewerb/NL2"},
        "belgian2":       {"name": "Challenger Pro League",  "country": "Belgium",       "tier": 2, "id": "BE2",  "url": "/challenger-pro-league/startseite/wettbewerb/BE2"},
        "russian2":       {"name": "1. Division",            "country": "Russia",        "tier": 2, "id": "RU2",  "url": "/1-division/startseite/wettbewerb/RU2"},
        # ── Europe – Tier 3 ──────────────────────────────────────
        "leagueone":      {"name": "League One",             "country": "England",       "tier": 3, "id": "GB3",  "url": "/league-one/startseite/wettbewerb/GB3"},
        "bundesliga3":    {"name": "3. Liga",                "country": "Germany",       "tier": 3, "id": "L3",   "url": "/3-liga/startseite/wettbewerb/L3"},
        "seriec1":        {"name": "Serie C Girone A",       "country": "Italy",         "tier": 3, "id": "IT3A", "url": "/serie-c-girone-a/startseite/wettbewerb/IT3A"},
        "seriec2":        {"name": "Serie C Girone B",       "country": "Italy",         "tier": 3, "id": "IT3B", "url": "/serie-c-girone-b/startseite/wettbewerb/IT3B"},
        "seriec3":        {"name": "Serie C Girone C",       "country": "Italy",         "tier": 3, "id": "IT3C", "url": "/serie-c-girone-c/startseite/wettbewerb/IT3C"},
        "primeraref1":    {"name": "Primera Federación I",   "country": "Spain",         "tier": 3, "id": "E3G1", "url": "/primera-federacion-grupo-i/startseite/wettbewerb/E3G1"},
        "primeraref2":    {"name": "Primera Federación II",  "country": "Spain",         "tier": 3, "id": "E3G2", "url": "/primera-federacion-grupo-ii/startseite/wettbewerb/E3G2"},
        # ── Europe – Tier 4 ──────────────────────────────────────
        "leaguetwo":      {"name": "League Two",             "country": "England",       "tier": 4, "id": "GB4",  "url": "/league-two/startseite/wettbewerb/GB4"},
        # ── Americas – Tier 1 ────────────────────────────────────
        "brazilian":      {"name": "Brasileirão",            "country": "Brazil",        "tier": 1, "id": "BRA1", "url": "/campeonato-brasileiro-serie-a/startseite/wettbewerb/BRA1"},
        "mls":            {"name": "MLS",                    "country": "USA",           "tier": 1, "id": "MLS1", "url": "/major-league-soccer/startseite/wettbewerb/MLS1"},
        "argentine":      {"name": "Liga Profesional",       "country": "Argentina",     "tier": 1, "id": "ARG1", "url": "/torneo-apertura/startseite/wettbewerb/ARG1"},
        "mexican":        {"name": "Liga MX",                "country": "Mexico",        "tier": 1, "id": "MEX1", "url": "/liga-mx-clausura/startseite/wettbewerb/MEX1"},
        "colombian":      {"name": "Liga DIMAYOR",           "country": "Colombia",      "tier": 1, "id": "COLP", "url": "/liga-dimayor-apertura/startseite/wettbewerb/COLP"},
        "uruguayan":      {"name": "Liga AUF",               "country": "Uruguay",       "tier": 1, "id": "URU1", "url": "/liga-auf-apertura/startseite/wettbewerb/URU1"},
        "chilean":        {"name": "Liga Primera",           "country": "Chile",         "tier": 1, "id": "CLPD", "url": "/liga-de-primera/startseite/wettbewerb/CLPD"},
        "ecuadorian":     {"name": "LigaPro Serie A",        "country": "Ecuador",       "tier": 1, "id": "EC1N", "url": "/ligapro-serie-a/startseite/wettbewerb/EC1N"},
        "peruvian":       {"name": "Liga 1",                 "country": "Peru",          "tier": 1, "id": "TDeA", "url": "/liga-1-apertura/startseite/wettbewerb/TDeA"},
        "paraguayan":     {"name": "Primera División",       "country": "Paraguay",      "tier": 1, "id": "PR1A", "url": "/primera-division-apertura/startseite/wettbewerb/PR1A"},
        # ── Americas – Tier 2 ────────────────────────────────────
        "brazilian2":     {"name": "Série B",                "country": "Brazil",        "tier": 2, "id": "BRA2", "url": "/campeonato-brasileiro-serie-b/startseite/wettbewerb/BRA2"},
        "argentine2":     {"name": "Primera Nacional",       "country": "Argentina",     "tier": 2, "id": "ARG2", "url": "/primera-nacional/startseite/wettbewerb/ARG2"},
        # ── Asia – Tier 1 ────────────────────────────────────────
        "saudi":          {"name": "Saudi Pro League",       "country": "Saudi Arabia",  "tier": 1, "id": "SA1",  "url": "/saudi-pro-league/startseite/wettbewerb/SA1"},
        "qatari":         {"name": "Stars League",           "country": "Qatar",         "tier": 1, "id": "QSL",  "url": "/qatar-stars-league/startseite/wettbewerb/QSL"},
        "emirati":        {"name": "UAE Pro League",         "country": "UAE",           "tier": 1, "id": "UAE1", "url": "/uae-pro-league/startseite/wettbewerb/UAE1"},
        "japanese":       {"name": "J1 League",              "country": "Japan",         "tier": 1, "id": "JAP1", "url": "/j1-league/startseite/wettbewerb/JAP1"},
        "chinese":        {"name": "Chinese Super League",   "country": "China",         "tier": 1, "id": "CSL",  "url": "/chinese-super-league/startseite/wettbewerb/CSL"},
        "iranian":        {"name": "Persian Gulf Pro League","country": "Iran",          "tier": 1, "id": "IRN1", "url": "/persian-gulf-pro-league/startseite/wettbewerb/IRN1"},
        "korean":         {"name": "K League 1",             "country": "South Korea",   "tier": 1, "id": "RSK1", "url": "/k-league-1/startseite/wettbewerb/RSK1"},
        "australian":     {"name": "A-League Men",           "country": "Australia",     "tier": 1, "id": "AUS1", "url": "/a-league-men/startseite/wettbewerb/AUS1"},
        # ── Asia – Tier 2 ────────────────────────────────────────
        "japanese2":      {"name": "J2 League",              "country": "Japan",         "tier": 2, "id": "JAP2", "url": "/j2-league/startseite/wettbewerb/JAP2"},
        # ── Africa – Tier 1 ──────────────────────────────────────
        "egyptian":       {"name": "Egyptian Premier League","country": "Egypt",         "tier": 1, "id": "EGY1", "url": "/egyptian-premier-league/startseite/wettbewerb/EGY1"},
        "south_african":  {"name": "Betway Premiership",     "country": "South Africa",  "tier": 1, "id": "SFA1", "url": "/betway-premiership/startseite/wettbewerb/SFA1"},
        "moroccan":       {"name": "Botola Pro Inwi",        "country": "Morocco",       "tier": 1, "id": "MAR1", "url": "/botola-pro-inwi/startseite/wettbewerb/MAR1"},
        # ── Youth ────────────────────────────────────────────────
        "primavera1":         {"name": "Primavera 1",              "country": "Italy",    "tier": "youth", "id": "IJ1",  "url": "/primavera-1/startseite/wettbewerb/IJ1"},
        "u19_bundesliga_a":   {"name": "U19 DFB-Nachwuchsliga A", "country": "Germany",  "tier": "youth", "id": "19LA", "url": "/u19-dfb-nachwuchsliga-hauptrunde-liga-a/startseite/wettbewerb/19LA"},
        "u19_bundesliga_h":   {"name": "U19 DFB-Nachwuchsliga H", "country": "Germany",  "tier": "youth", "id": "19D8", "url": "/u19-dfb-nachwuchsliga-vorrunde-gruppe-h/startseite/wettbewerb/19D8"},
        "liga_revelacao":     {"name": "Liga Revelação U23",       "country": "Portugal", "tier": "youth", "id": "PT23", "url": "/liga-revelacao-u23/startseite/wettbewerb/PT23"},
        # ── European Cups ────────────────────────────────────────
        "champions":      {"name": "UEFA Champions League",       "country": "Europe", "tier": "cup", "id": "CL",   "url": "/uefa-champions-league/startseite/pokalwettbewerb/CL"},
        "europa_league":  {"name": "UEFA Europa League",          "country": "Europe", "tier": "cup", "id": "EL",   "url": "/europa-league/startseite/pokalwettbewerb/EL"},
        "conference":     {"name": "UEFA Conference League",      "country": "Europe", "tier": "cup", "id": "UCOL", "url": "/europa-conference-league/startseite/pokalwettbewerb/UCOL"},
    }
    
    
    def __init__(
        self,
        season: str = None,
        delay: float = 0.25,
        max_retries: int = 5,
        retry_pause: float = 60.0,
        verbose: bool = True,
        use_downloaded_data: bool = False,
    ):
        """
        Initialize the scraper.
        
        Args:
            season: Season to scrape (e.g., "2024-2025"). Defaults to current.
            delay: Delay between requests in seconds.
            max_retries: Maximum retry attempts for failed requests.
            retry_pause: Pause between retries in seconds.
            verbose: Print progress information.
            use_downloaded_data: If True, skip leagues whose per-league JSON
                already exists and reuse the downloaded data instead.
        """
        if season:
            self.season = season
            self.season_year = self._get_season_year(season)
        else:
            year = datetime.now().year
            if datetime.now().month < 7:
                year -= 1
            self.season = f"{year}-{year+1}"
            self.season_year = year
        
        self.delay = delay
        self.max_retries = max_retries
        self.retry_pause = retry_pause
        self.verbose = verbose
        self.use_downloaded_data = use_downloaded_data
        
        # Ensure data directory exists
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    def _get_season_year(self, season: str) -> int:
        """Extract starting year from season string."""
        match = re.search(r"(\d{4})", str(season))
        if match:
            return int(match.group(1))
        return datetime.now().year
    
    def log(self, message: str):
        """Print message if verbose mode is on."""
        if self.verbose:
            print(message)
    
    def fetch_page(
        self,
        url: str,
        tries: int = None,
        pause: float = None,
    ) -> Optional[BeautifulSoup]:
        """
        Fetch a URL and return BeautifulSoup object.
        
        Args:
            url: URL to fetch
            tries: Number of retry attempts
            pause: Pause between retries
        
        Returns:
            BeautifulSoup object or None if failed
        """
        tries = tries or self.max_retries
        pause = pause or self.retry_pause
        
        for attempt in range(1, tries + 1):
            try:
                time.sleep(self.delay)
                headers = pick_headers()
                
                if USE_TLS:
                    response = tls_requests.get(url, headers=headers)
                else:
                    response = requests.get(url, headers=headers)
                
                if response.status_code == 200:
                    return BeautifulSoup(response.content, "html.parser")
                else:
                    self.log(f"  Attempt {attempt}/{tries}: HTTP {response.status_code}")
                    
            except Exception as e:
                self.log(f"  Attempt {attempt}/{tries}: Error {e!r}")
            
            if attempt < tries:
                time.sleep(pause)
        
        return None
    
    def generate_id(self, *parts: str) -> str:
        """Generate a unique ID from parts."""
        combined = "_".join(str(p) for p in parts if p)
        return hashlib.md5(combined.encode()).hexdigest()[:12]
    
    def extract_team_id(self, url: str) -> Optional[str]:
        """Extract team ID from URL."""
        match = re.search(r"/verein/(\d+)", url)
        return match.group(1) if match else None
    
    def extract_player_id(self, url: str) -> Optional[str]:
        """Extract player ID from URL."""
        match = re.search(r"/spieler/(\d+)", url)
        return match.group(1) if match else None
    
    def get_league_url(self, league: str) -> str:
        """Get the URL path for a league."""
        league_lower = league.lower().strip().replace(" ", "_")
        entry = self.LEAGUE_INFO.get(league_lower)
        if entry:
            return entry["url"]
        return f"/{league_lower}/startseite/wettbewerb"
    
    def search_team(self, team_name: str) -> Optional[Dict[str, str]]:
        """
        Search for a team by name.
        
        Args:
            team_name: Team name to search
        
        Returns:
            Dict with team_name, team_url, team_id or None
        """
        search_url = f"{self.BASE_URL}/schnellsuche/ergebnis/schnellsuche?query={team_name.replace(' ', '+')}"
        
        self.log(f"Searching for team: {team_name}")
        soup = self.fetch_page(search_url)
        
        if not soup:
            return None
        
        # Find team results
        for box in soup.select("div.box"):
            header = box.select_one("h2")
            if header and "club" in header.text.lower():
                link = box.select_one("table.items td.hauptlink a")
                if link:
                    href = link.get("href", "")
                    name = link.text.strip()
                    team_id = self.extract_team_id(href)
                    
                    return {
                        "team_name": name,
                        "team_url": f"{self.BASE_URL}{href}",
                        "team_id": team_id,
                    }
        
        # Fallback: first link with verein
        link = soup.select_one("a[href*='/verein/']")
        if link:
            href = link.get("href", "")
            name = link.get("title") or link.text.strip()
            team_id = self.extract_team_id(href)
            if team_id:
                return {
                    "team_name": name,
                    "team_url": f"{self.BASE_URL}{href}",
                    "team_id": team_id,
                }
        
        return None
    
    def get_league_teams(self, league: str) -> List[Dict[str, str]]:
        """
        Get all teams from a league.
        
        Args:
            league: League name (e.g., "laliga", "premier")
        
        Returns:
            List of dicts with team_name, team_url, team_id
        """
        league_path = self.get_league_url(league)
        url = f"{self.BASE_URL}{league_path}/saison_id/{self.season_year}"
        
        self.log(f"Fetching teams from {league}...")
        soup = self.fetch_page(url)
        
        if not soup:
            self.log(f"Failed to fetch league page")
            return []
        
        teams = []
        seen_ids = set()
        
        # Try multiple selectors
        for selector in ["table.items tbody tr td.hauptlink a", "div.responsive-table table tbody tr td a[title]"]:
            for a in soup.select(selector):
                href = a.get("href", "")
                title = a.get("title", "") or a.text.strip()
                
                if "verein" in href and title:
                    team_id = self.extract_team_id(href)
                    if team_id and team_id not in seen_ids:
                        seen_ids.add(team_id)
                        teams.append({
                            "team_name": title,
                            "team_url": f"{self.BASE_URL}{href}",
                            "team_id": team_id,
                        })
        
        self.log(f"Found {len(teams)} teams")
        return teams
    
    def get_transferred_player_ids(self, team_id: str, team_name: str = "") -> List[tuple]:
        """
        Scrape the season transfer page for a team and return the
        (player_id, player_name) pairs found in arrivals & departures.

        This is a lightweight helper used by the players, valuations and
        transfers scrapers to discover players that are not in the current
        squad (Phase 2).
        """
        season_year = str(self.season_year)
        url = f"{self.BASE_URL}/-/transfers/verein/{team_id}/saison_id/{season_year}"

        self.log(f"  Scanning transfer page: {team_name or team_id} ({self.season})")
        soup = self.fetch_page(url)

        if not soup:
            return []

        players: List[tuple] = []
        seen: set = set()

        for box in soup.select("div.box"):
            header = box.select_one("h2")
            if not header:
                continue
            ht = header.text.strip().lower()
            if not any(kw in ht for kw in ("arrival", "departure", "llegada", "salida", "zugänge", "abgänge")):
                continue

            table = box.select_one("table.items")
            if not table:
                continue
            tbody = table.select_one("tbody")
            if not tbody:
                continue

            for row in tbody.select("tr.odd, tr.even"):
                link = row.select_one("a[href*='/profil/spieler/'], a[href*='/spieler/']")
                if not link:
                    continue
                pid = self.extract_player_id(link.get("href", ""))
                pname = link.get("title", "") or link.text.strip()
                if pid and pid not in seen:
                    seen.add(pid)
                    players.append((pid, pname))

        self.log(f"    Found {len(players)} players on transfer page")
        return players

    def save_json(
        self,
        data: Any,
        file_name: str,
        validate: bool = True,
        create_backup: bool = True,
        min_items: int = 5,
        id_field: str = "team_id",
        data_type: str = "teams"
    ) -> Path:
        """
        Save data to JSON file with optional validation and backup.
        
        Args:
            data: Data to save
            file_name: Filename without extension
            validate: If True, validate data before saving
            create_backup: If True, create _OLD backup of previous file
            min_items: Minimum items for validation
            id_field: Field for unique ID when merging
            data_type: Type of data for validation
        
        Returns:
            Path to saved file
        """
        from scraping.utils.helpers import overwrite_dict_data, write_dict_to_json, DATA_DIR
        
        file_path = DATA_DIR / f"{file_name}.json"
        
        if create_backup:
            # Use overwrite with backup and optional validation
            success = overwrite_dict_data(
                data=data,
                file_name=file_name,
                ignore_valid_file=not validate,
                ignore_old_data=False,
                min_items=min_items,
                id_field=id_field,
                data_type=data_type
            )
            if success:
                self.log(f"Saved (with backup): {file_path}")
            else:
                self.log(f"Warning: Save failed or skipped for {file_name}")
        else:
            # Simple save without backup
            write_dict_to_json(data, file_name)
            self.log(f"Saved: {file_path}")
        
        return file_path
    
    def load_json(self, file_name: str) -> Optional[Any]:
        """
        Load data from JSON file.
        
        Args:
            file_name: Filename without extension
        
        Returns:
            Data or None if file doesn't exist
        """
        from scraping.utils.helpers import load_json
        return load_json(file_name)
    
    @staticmethod
    def normalize_string(s: str) -> str:
        """Normalize string for comparison."""
        if not s:
            return ""
        return unidecode(str(s)).lower().replace(" ", "").replace("-", "")
    
    @staticmethod
    def parse_market_value(value_str: str) -> Optional[float]:
        """Parse market value string to float (in euros)."""
        if not value_str:
            return None
        
        # Clean the string - remove all non-numeric except decimal separators and multiplier letters
        value_str = value_str.strip().lower()
        
        # Remove currency symbols and other unicode chars (keep only alphanumeric, dots, commas)
        value_str = re.sub(r"[^\d.,a-z]", "", value_str)
        
        # Normalize decimal separator
        value_str = value_str.replace(",", ".")
        
        multiplier = 1
        if "bn" in value_str:
            multiplier = 1_000_000_000
            value_str = value_str.replace("bn", "")
        elif "b" in value_str:
            multiplier = 1_000_000_000
            value_str = value_str.replace("b", "")
        elif "mill" in value_str:
            multiplier = 1_000_000
            value_str = value_str.replace("mill", "")
        elif "m" in value_str:
            multiplier = 1_000_000
            value_str = value_str.replace("m", "")
        elif "k" in value_str:
            multiplier = 1_000
            value_str = value_str.replace("k", "")
        elif "th" in value_str:
            multiplier = 1_000
            value_str = value_str.replace("th", "")
        
        # Remove any remaining non-numeric chars except dot
        value_str = re.sub(r"[^\d.]", "", value_str)
        
        try:
            return round(float(value_str) * multiplier, 0)
        except ValueError:
            return None
