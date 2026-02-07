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
DATA_DIR = ROOT_DIR / "data"

# Rotating header pool
HEADER_POOL = [
    # Chrome / Windows (older)
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )
    },
    # Chrome / Windows (newer)
    {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
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
    # Safari / macOS
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.1 Safari/605.1.15"
        )
    },
]


def pick_headers() -> dict:
    """Pick a random header from the pool."""
    return random.choice(HEADER_POOL).copy()


class BaseScraper:
    """Base class for Transfermarkt scrapers."""
    
    BASE_URL = "https://www.transfermarkt.com"
    
    # League URL mappings
    LEAGUE_URLS = {
        "laliga": "/laliga/startseite/wettbewerb/ES1",
        "premier": "/premier-league/startseite/wettbewerb/GB1",
        "seriea": "/serie-a/startseite/wettbewerb/IT1",
        "bundesliga": "/bundesliga/startseite/wettbewerb/L1",
        "ligue1": "/ligue-1/startseite/wettbewerb/FR1",
        "segunda": "/laliga2/startseite/wettbewerb/ES2",
        "championship": "/championship/startseite/wettbewerb/GB2",
        "eredivisie": "/eredivisie/startseite/wettbewerb/NL1",
        "liga_portugal": "/liga-nos/startseite/wettbewerb/PO1",
        "champions": "/uefa-champions-league/startseite/pokalwettbewerb/CL",
        "europa_league": "/europa-league/startseite/pokalwettbewerb/EL",
        "conference": "/europa-conference-league/startseite/pokalwettbewerb/UCOL",
    }
    
    def __init__(
        self,
        season: str = None,
        delay: float = 0.25,
        max_retries: int = 5,
        retry_pause: float = 60.0,
        verbose: bool = True,
    ):
        """
        Initialize the scraper.
        
        Args:
            season: Season to scrape (e.g., "2024-2025"). Defaults to current.
            delay: Delay between requests in seconds.
            max_retries: Maximum retry attempts for failed requests.
            retry_pause: Pause between retries in seconds.
            verbose: Print progress information.
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
        return self.LEAGUE_URLS.get(league_lower, f"/{league_lower}/startseite/wettbewerb")
    
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
        from scraping.utils.helpers import read_dict_from_json
        return read_dict_from_json(file_name)
    
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
            return float(value_str) * multiplier
        except ValueError:
            return None
