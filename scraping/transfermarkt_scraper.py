# scraping/transfermarkt_scraper.py
"""
Transfermarkt Scraper for team-analysis-ai

Extracts football data from Transfermarkt including:
- Team information
- Player details
- Transfer history
- Market valuations
"""
from __future__ import annotations

import re
import time
import random
import hashlib
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple, Callable

import requests
from bs4 import BeautifulSoup
import tls_requests

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

from .base_scraper import BaseScraper
from .models import Player, Team, Transfer, Valuation
from .utils.helpers import (
    parse_market_value,
    parse_age,
    parse_height,
    normalize_team_name,
    get_season_year,
    format_season,
    write_dict_data,
    read_dict_data,
    write_list_to_csv,
)


class TransfermarktScraper:
    """
    Scraper for extracting football data from Transfermarkt.
    
    Supports scraping:
    - Single team by name
    - Entire league
    - Player details, transfers, and valuations
    """
    
    BASE_URL = "https://www.transfermarkt.com"
    
    # Reuse LEAGUE_INFO from BaseScraper (single source of truth)
    LEAGUE_INFO = BaseScraper.LEAGUE_INFO
    
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
        self.season = season or format_season(datetime.now().year)
        self.season_year = get_season_year(self.season)
        self.delay = delay
        self.max_retries = max_retries
        self.retry_pause = retry_pause
        self.verbose = verbose
        
        # Cache
        self._team_cache: Dict[str, Team] = {}
        self._player_cache: Dict[str, Player] = {}
    
    def _log(self, message: str):
        """Print message if verbose mode is on."""
        if self.verbose:
            print(message)
    
    def _fetch_page(
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
                
                response = tls_requests.get(url, headers=headers)
                
                if response.status_code == 200:
                    return BeautifulSoup(response.content, "html.parser")
                else:
                    self._log(f"  Attempt {attempt}/{tries}: HTTP {response.status_code} for {url}")
                    
            except Exception as e:
                self._log(f"  Attempt {attempt}/{tries}: Error {e!r}")
            
            if attempt < tries:
                time.sleep(pause)
        
        return None
    
    def _generate_id(self, *parts: str) -> str:
        """Generate a unique ID from parts."""
        combined = "_".join(str(p) for p in parts if p)
        return hashlib.md5(combined.encode()).hexdigest()[:12]
    
    def _get_league_url(self, league: str) -> str:
        """Get the URL path for a league."""
        league_lower = league.lower().strip().replace(" ", "_")
        entry = self.LEAGUE_INFO.get(league_lower)
        if entry:
            return entry["url"]
        return f"/{league_lower}/startseite/wettbewerb"
    
    def _extract_team_id(self, url: str) -> Optional[str]:
        """Extract team ID from URL."""
        match = re.search(r"/verein/(\d+)", url)
        return match.group(1) if match else None
    
    def _extract_player_id(self, url: str) -> Optional[str]:
        """Extract player ID from URL."""
        match = re.search(r"/spieler/(\d+)", url)
        return match.group(1) if match else None
    
    # =========================================================================
    # LEAGUE SCRAPING
    # =========================================================================
    
    def get_league_teams(self, league: str) -> List[Dict[str, str]]:
        """
        Get all teams from a league.
        
        Args:
            league: League name (e.g., "laliga", "premier league")
        
        Returns:
            List of dicts with team_name, team_url, team_id
        """
        league_path = self._get_league_url(league)
        url = f"{self.BASE_URL}{league_path}/saison_id/{self.season_year}"
        
        self._log(f"Fetching teams from {league}...")
        soup = self._fetch_page(url)
        
        if not soup:
            self._log(f"Failed to fetch league page: {url}")
            return []
        
        teams = []
        
        # Try multiple table selectors
        selectors = [
            "#yw1 table tbody tr td a[title]",
            "table.items tbody tr td.hauptlink a",
            "div.responsive-table table tbody tr td a[title]",
        ]
        
        for selector in selectors:
            links = soup.select(selector)
            for a in links:
                href = a.get("href", "")
                title = a.get("title", "") or a.text.strip()
                
                if "verein" in href and title:
                    team_id = self._extract_team_id(href)
                    if team_id and not any(t["team_id"] == team_id for t in teams):
                        teams.append({
                            "team_name": normalize_team_name(title),
                            "team_url": f"{self.BASE_URL}{href}",
                            "team_id": team_id,
                        })
        
        self._log(f"Found {len(teams)} teams in {league}")
        return teams
    
    # =========================================================================
    # TEAM SCRAPING
    # =========================================================================
    
    def search_team(self, team_name: str) -> Optional[Dict[str, str]]:
        """
        Search for a team by name.
        
        Args:
            team_name: Team name to search
        
        Returns:
            Dict with team info or None
        """
        search_url = f"{self.BASE_URL}/schnellsuche/ergebnis/schnellsuche?query={team_name.replace(' ', '+')}&x=0&y=0"
        
        self._log(f"Searching for team: {team_name}")
        soup = self._fetch_page(search_url)
        
        if not soup:
            return None
        
        # Find team results
        team_box = soup.select_one("div.box:has(h2:-soup-contains('Clubs'))")
        if not team_box:
            team_box = soup.select_one("div.box")
        
        if team_box:
            link = team_box.select_one("table.items td.hauptlink a")
            if link:
                href = link.get("href", "")
                name = link.text.strip()
                team_id = self._extract_team_id(href)
                
                return {
                    "team_name": normalize_team_name(name),
                    "team_url": f"{self.BASE_URL}{href}",
                    "team_id": team_id,
                }
        
        return None
    
    def scrape_team(
        self,
        team_name: str = None,
        team_url: str = None,
        team_id: str = None,
    ) -> Optional[Team]:
        """
        Scrape team details.
        
        Args:
            team_name: Team name to search (if URL not provided)
            team_url: Direct URL to team page
            team_id: Team ID
        
        Returns:
            Team object or None
        """
        # Resolve team URL
        if not team_url:
            if team_name:
                result = self.search_team(team_name)
                if result:
                    team_url = result["team_url"]
                    team_id = result["team_id"]
                    team_name = result["team_name"]
            if not team_url:
                self._log(f"Could not find team: {team_name}")
                return None
        
        # Ensure URL has season
        if "saison_id" not in team_url:
            team_url = f"{team_url.rstrip('/')}/saison_id/{self.season_year}"
        
        self._log(f"Scraping team: {team_name or team_url}")
        soup = self._fetch_page(team_url)
        
        if not soup:
            return None
        
        # Extract team ID if not provided
        if not team_id:
            team_id = self._extract_team_id(team_url)
        
        # Team name from header
        if not team_name:
            header = soup.select_one("h1.data-header__headline-wrapper")
            team_name = header.text.strip() if header else "Unknown"
        
        team = Team(
            team_id=team_id or self._generate_id(team_name),
            name=normalize_team_name(team_name),
            season=self.season,
            profile_url=team_url,
        )
        
        # Extract squad info box
        info_table = soup.select_one("div.data-header__info-box")
        if info_table:
            for item in info_table.select("li, span.data-header__content"):
                text = item.text.strip()
                label_el = item.select_one("span.data-header__label")
                label = label_el.text.strip().lower() if label_el else ""
                
                if "squad size" in label or "kader" in label or "plantilla" in label:
                    match = re.search(r"(\d+)", text)
                    if match:
                        team.squad_size = int(match.group(1))
                
                elif "average age" in label or "alter" in label or "edad" in label:
                    match = re.search(r"(\d+[.,]?\d*)", text)
                    if match:
                        team.average_age = float(match.group(1).replace(",", "."))
                
                elif "foreigners" in label or "ausländer" in label or "extranjeros" in label:
                    match = re.search(r"(\d+)", text)
                    if match:
                        team.foreigners_count = int(match.group(1))
                    pct_match = re.search(r"(\d+[.,]?\d*)\s*%", text)
                    if pct_match:
                        team.foreigners_percentage = float(pct_match.group(1).replace(",", "."))
                
                elif "national team" in label or "nationalspieler" in label or "selección" in label:
                    match = re.search(r"(\d+)", text)
                    if match:
                        team.national_team_players = int(match.group(1))
                
                elif "stadium" in label or "stadion" in label or "estadio" in label:
                    stadium_link = item.select_one("a")
                    if stadium_link:
                        team.stadium_name = stadium_link.text.strip()
                
        # Market value
        value_el = soup.select_one("a.data-header__market-value-wrapper")
        if value_el:
            team.total_market_value = parse_market_value(value_el.text)
        
        # League
        league_el = soup.select_one("span.data-header__club a")
        if league_el:
            team.league = league_el.text.strip()
            league_href = league_el.get("href", "")
            match = re.search(r"wettbewerb/(\w+)", league_href)
            if match:
                team.league_id = match.group(1)
        
        # Country
        flag_el = soup.select_one("span.data-header__club img.flaggenrahmen")
        if flag_el:
            team.country = flag_el.get("title", "")
        
        # Logo
        logo_el = soup.select_one("img.data-header__profile-image")
        if logo_el:
            team.logo_url = logo_el.get("src", "")
        
        # Cache
        self._team_cache[team.team_id] = team
        
        return team
    
    # =========================================================================
    # PLAYER SCRAPING
    # =========================================================================
    
    def get_team_players(
        self,
        team: Team = None,
        team_url: str = None,
    ) -> List[Player]:
        """
        Get all players from a team.
        
        Args:
            team: Team object
            team_url: Direct URL to team page
        
        Returns:
            List of Player objects
        """
        if team:
            team_url = team.profile_url
        
        if not team_url:
            self._log("No team URL provided")
            return []
        
        # Ensure we're on the squad page
        if "/kader/" not in team_url and "/startseite/" in team_url:
            team_url = team_url.replace("/startseite/", "/kader/")
        elif "/kader/" not in team_url:
            # Extract team slug and ID
            match = re.search(r"/([^/]+)/(?:startseite|kader)/verein/(\d+)", team_url)
            if match:
                slug, tid = match.groups()
                team_url = f"{self.BASE_URL}/{slug}/kader/verein/{tid}/saison_id/{self.season_year}/plus/1"
        
        # Add plus/1 for detailed view
        if "/plus/" not in team_url:
            team_url = f"{team_url.rstrip('/')}/plus/1"
        
        self._log(f"Fetching players from: {team_url}")
        soup = self._fetch_page(team_url)
        
        if not soup:
            return []
        
        players = []
        
        # Find player rows
        rows = soup.select("table.items tbody tr.odd, table.items tbody tr.even")
        
        for row in rows:
            try:
                player = self._parse_player_row(row, team)
                if player:
                    players.append(player)
                    self._player_cache[player.player_id] = player
            except Exception as e:
                self._log(f"  Error parsing player row: {e}")
                continue
        
        self._log(f"Found {len(players)} players")
        
        # Update team with player IDs
        if team:
            team.player_ids = [p.player_id for p in players]
        
        return players
    
    def _parse_player_row(self, row, team: Team = None) -> Optional[Player]:
        """Parse a player row from the squad table."""
        # Player link and name
        name_cell = row.select_one("td.hauptlink a")
        if not name_cell:
            return None
        
        player_url = name_cell.get("href", "")
        player_name = name_cell.text.strip()
        player_id = self._extract_player_id(player_url)
        
        if not player_id:
            return None
        
        player = Player(
            player_id=player_id,
            name=player_name,
            current_club=team.name if team else "",
            current_club_id=team.team_id if team else None,
            profile_url=f"{self.BASE_URL}{player_url}",
            season=self.season,
        )
        
        # Image
        img_el = row.select_one("img.bilderrahmen-fixed")
        if img_el:
            player.img_url = img_el.get("data-src") or img_el.get("src")
        
        # Position
        pos_cells = row.select("td.posrela table tr")
        if len(pos_cells) >= 2:
            pos_text = pos_cells[1].text.strip()
            player.position = self._normalize_position(pos_text)
            player.detailed_position = pos_text
        else:
            pos_cell = row.select_one("td:nth-of-type(2)")
            if pos_cell:
                player.position = self._normalize_position(pos_cell.text.strip())
        
        # Parse all cells
        cells = row.select("td")
        for i, cell in enumerate(cells):
            text = cell.text.strip()
            
            # Shirt number
            if cell.select_one("div.rn_nummer"):
                try:
                    player.shirt_number = int(text)
                except ValueError:
                    pass
            
            # Age / Birth date
            if "(" in text and ")" in text:
                age_match = re.search(r"\((\d+)\)", text)
                if age_match:
                    player.age = int(age_match.group(1))
                date_match = re.search(r"(\w{3}\s+\d{1,2},\s+\d{4})", text)
                if date_match:
                    try:
                        player.birth_date = datetime.strptime(date_match.group(1), "%b %d, %Y").date()
                    except ValueError:
                        pass
            
            # Nationality (flag image)
            flags = cell.select("img.flaggenrahmen")
            if flags and not player.nationality:
                player.nationality = flags[0].get("title", "")
                if len(flags) > 1:
                    player.second_nationality = flags[1].get("title", "")
            
            # Market value
            if "€" in text or "m" in text.lower() or "k" in text.lower():
                value = parse_market_value(text)
                if value and value > 0:
                    player.current_market_value = value
        
        # Foot and height from additional columns
        for cell in cells:
            cell_text = cell.text.strip().lower()
            if cell_text in ["right", "left", "both", "derecho", "izquierdo", "ambos", "rechts", "links", "beidfüßig"]:
                player.preferred_foot = cell_text.capitalize()
            elif re.match(r"^\d{1,2}[,.]?\d{0,2}\s*m?$", cell_text) or "cm" in cell_text:
                player.height = parse_height(cell_text)
        
        return player
    
    def _normalize_position(self, pos: str) -> str:
        """Normalize position to standard format."""
        pos = pos.strip().lower()
        
        # Goalkeeper
        if any(x in pos for x in ["keeper", "portero", "torwart", "gk"]):
            return "GK"
        
        # Defender
        if any(x in pos for x in ["back", "defens", "centre-back", "cb", "lb", "rb", "defensa"]):
            return "DEF"
        
        # Midfielder
        if any(x in pos for x in ["midfield", "medio", "mittelfeld", "cm", "dm", "am"]):
            return "MID"
        
        # Forward
        if any(x in pos for x in ["forward", "striker", "wing", "delantero", "stürmer", "cf", "lw", "rw", "ss"]):
            return "ATT"
        
        return pos.upper()[:3] if pos else "N/A"
    
    def scrape_player_details(self, player: Player) -> Player:
        """
        Scrape detailed player information from their profile page.
        
        Args:
            player: Player object with profile_url
        
        Returns:
            Updated Player object
        """
        if not player.profile_url:
            return player
        
        self._log(f"  Scraping details for: {player.name}")
        soup = self._fetch_page(player.profile_url)
        
        if not soup:
            return player
        
        # Info table
        info_table = soup.select_one("div.info-table")
        if info_table:
            for row in info_table.select("span.info-table__content"):
                label_el = row.find_previous_sibling("span", class_="info-table__content--regular")
                if not label_el:
                    continue
                
                label = label_el.text.strip().lower()
                value = row.text.strip()
                
                if "date of birth" in label or "nacimiento" in label or "geburtsdatum" in label:
                    try:
                        # Try multiple date formats
                        for fmt in ["%b %d, %Y", "%d.%m.%Y", "%d/%m/%Y"]:
                            try:
                                player.birth_date = datetime.strptime(value.split("(")[0].strip(), fmt).date()
                                break
                            except ValueError:
                                continue
                    except Exception:
                        pass
                    
                    age_match = re.search(r"\((\d+)\)", value)
                    if age_match:
                        player.age = int(age_match.group(1))
                
                elif "height" in label or "altura" in label or "größe" in label:
                    player.height = parse_height(value)
                
                elif "citizenship" in label or "nacionalidad" in label or "staatsbürgerschaft" in label:
                    if not player.nationality:
                        player.nationality = value
                
                elif "foot" in label or "pie" in label or "fuß" in label:
                    player.preferred_foot = value
                
                elif "position" in label or "posición" in label:
                    if not player.detailed_position:
                        player.detailed_position = value
                        player.position = self._normalize_position(value)
                
                elif "contract" in label or "contrato" in label or "vertrag" in label:
                    try:
                        for fmt in ["%b %d, %Y", "%d.%m.%Y", "%d/%m/%Y"]:
                            try:
                                player.contract_expires_date = datetime.strptime(value, fmt).date()
                                break
                            except ValueError:
                                continue
                    except Exception:
                        pass
                
                elif "joined" in label or "llegada" in label or "im team seit" in label:
                    try:
                        for fmt in ["%b %d, %Y", "%d.%m.%Y", "%d/%m/%Y"]:
                            try:
                                player.joined_date = datetime.strptime(value, fmt).date()
                                break
                            except ValueError:
                                continue
                    except Exception:
                        pass
        
        # Highest market value
        mv_box = soup.select_one("div.data-header__market-value-wrapper")
        if mv_box:
            highest_el = mv_box.select_one("span.data-header__market-value-max")
            if highest_el:
                player.highest_market_value = parse_market_value(highest_el.text)
        
        return player
    
    # =========================================================================
    # TRANSFER SCRAPING
    # =========================================================================
    
    def get_player_transfers(self, player: Player) -> List[Transfer]:
        """
        Get transfer history for a player.
        
        Args:
            player: Player object
        
        Returns:
            List of Transfer objects
        """
        if not player.profile_url:
            return []
        
        # Navigate to transfers page
        transfers_url = player.profile_url.replace("/profil/", "/transfers/")
        
        self._log(f"  Fetching transfers for: {player.name}")
        soup = self._fetch_page(transfers_url)
        
        if not soup:
            return []
        
        transfers = []
        
        # Find transfer rows
        rows = soup.select("div.grid-view table.items tbody tr")
        
        for row in rows:
            try:
                transfer = self._parse_transfer_row(row, player)
                if transfer:
                    transfers.append(transfer)
            except Exception as e:
                self._log(f"    Error parsing transfer: {e}")
                continue
        
        self._log(f"    Found {len(transfers)} transfers")
        return transfers
    
    def _parse_transfer_row(self, row, player: Player) -> Optional[Transfer]:
        """Parse a transfer row."""
        cells = row.select("td")
        if len(cells) < 5:
            return None
        
        # Season
        season_cell = cells[0]
        season_text = season_cell.text.strip()
        
        # Date
        date_cell = cells[1] if len(cells) > 1 else None
        transfer_date = None
        if date_cell:
            date_text = date_cell.text.strip()
            for fmt in ["%b %d, %Y", "%d.%m.%Y", "%d/%m/%Y"]:
                try:
                    transfer_date = datetime.strptime(date_text, fmt).date()
                    break
                except ValueError:
                    continue
        
        # From club
        from_cell = row.select_one("td.rechts + td.hauptlink a")
        from_club_name = from_cell.text.strip() if from_cell else ""
        from_club_id = self._extract_team_id(from_cell.get("href", "")) if from_cell else None
        
        # To club
        to_cell = row.select("td.hauptlink a")
        to_club_name = ""
        to_club_id = None
        if len(to_cell) >= 2:
            to_club_name = to_cell[-1].text.strip()
            to_club_id = self._extract_team_id(to_cell[-1].get("href", ""))
        
        # Fee
        fee_cell = row.select_one("td.rechts:last-of-type")
        fee_text = fee_cell.text.strip() if fee_cell else ""
        
        price = None
        price_str = fee_text
        is_loan = False
        transfer_type = "purchase"
        
        fee_lower = fee_text.lower()
        if "loan" in fee_lower or "préstamo" in fee_lower or "leihgabe" in fee_lower:
            is_loan = True
            transfer_type = "loan"
        elif "free" in fee_lower or "libre" in fee_lower or "ablösefrei" in fee_lower:
            transfer_type = "free"
            price = 0
            price_str = "Free transfer"
        elif "?" not in fee_text and "-" not in fee_text:
            price = parse_market_value(fee_text)
        
        if price is None and fee_text in ["?", "-", ""]:
            price_str = "Unknown"
        
        if not from_club_name and not to_club_name:
            return None
        
        transfer_id = self._generate_id(player.player_id, from_club_name, to_club_name, season_text)
        
        return Transfer(
            transfer_id=transfer_id,
            player_id=player.player_id,
            player_name=player.name,
            from_club_name=normalize_team_name(from_club_name),
            from_club_id=from_club_id,
            to_club_name=normalize_team_name(to_club_name),
            to_club_id=to_club_id,
            price=price,
            price_str=price_str,
            transfer_date=transfer_date,
            season=season_text,
            transfer_type=transfer_type,
            is_loan=is_loan,
        )
    
    def get_team_transfers(
        self,
        team: Team,
        window: str = "all",
    ) -> Tuple[List[Transfer], List[Transfer]]:
        """
        Get transfers for a team (arrivals and departures).
        
        Args:
            team: Team object
            window: "summer", "winter", or "all"
        
        Returns:
            Tuple of (arrivals, departures)
        """
        if not team.profile_url:
            return [], []
        
        # Navigate to transfers page
        base_url = team.profile_url.split("/startseite/")[0] if "/startseite/" in team.profile_url else team.profile_url.rsplit("/", 1)[0]
        transfers_url = f"{base_url}/transfers/verein/{team.team_id}/saison_id/{self.season_year}"
        
        self._log(f"Fetching team transfers: {team.name}")
        soup = self._fetch_page(transfers_url)
        
        if not soup:
            return [], []
        
        arrivals = []
        departures = []
        
        # Find transfer boxes
        boxes = soup.select("div.box")
        
        for box in boxes:
            header = box.select_one("h2")
            if not header:
                continue
            
            header_text = header.text.lower()
            is_arrival = "arrival" in header_text or "llegada" in header_text or "zugänge" in header_text
            is_departure = "departure" in header_text or "salida" in header_text or "abgänge" in header_text
            
            if not is_arrival and not is_departure:
                continue
            
            rows = box.select("table.items tbody tr")
            for row in rows:
                try:
                    # Player link
                    player_link = row.select_one("td.hauptlink a")
                    if not player_link:
                        continue
                    
                    player_name = player_link.text.strip()
                    player_id = self._extract_player_id(player_link.get("href", ""))
                    
                    # Other club
                    club_links = row.select("td.zentriert a img.tiny_wappen")
                    other_club = ""
                    other_club_id = None
                    if club_links:
                        club_link = club_links[0].find_parent("a")
                        if club_link:
                            other_club = club_link.get("title", "")
                            other_club_id = self._extract_team_id(club_link.get("href", ""))
                    
                    # Fee
                    fee_cell = row.select_one("td.rechts:last-of-type")
                    fee_text = fee_cell.text.strip() if fee_cell else ""
                    
                    price = None
                    price_str = fee_text
                    is_loan = False
                    transfer_type = "purchase"
                    
                    fee_lower = fee_text.lower()
                    if "loan" in fee_lower or "préstamo" in fee_lower or "leihgabe" in fee_lower:
                        is_loan = True
                        transfer_type = "loan"
                    elif "free" in fee_lower or "libre" in fee_lower or "ablösefrei" in fee_lower:
                        transfer_type = "free"
                        price = 0
                        price_str = "Free transfer"
                    elif "end of loan" in fee_lower or "fin de cesión" in fee_lower:
                        transfer_type = "loan_return"
                        is_loan = True
                    elif "?" not in fee_text and "-" not in fee_text:
                        price = parse_market_value(fee_text)
                    
                    if price is None and fee_text in ["?", "-", ""]:
                        price_str = "Unknown"
                    
                    from_club_name = normalize_team_name(other_club) if is_arrival else team.name
                    to_club_name = team.name if is_arrival else normalize_team_name(other_club)
                    from_id = other_club_id if is_arrival else team.team_id
                    to_id = team.team_id if is_arrival else other_club_id
                    
                    transfer = Transfer(
                        transfer_id=self._generate_id(player_id, from_club_name, to_club_name, self.season),
                        player_id=player_id or self._generate_id(player_name),
                        player_name=player_name,
                        from_club_name=from_club_name,
                        from_club_id=from_id,
                        to_club_name=to_club_name,
                        to_club_id=to_id,
                        price=price,
                        price_str=price_str,
                        season=self.season,
                        transfer_type=transfer_type,
                        is_loan=is_loan,
                    )
                    
                    if is_arrival:
                        arrivals.append(transfer)
                    else:
                        departures.append(transfer)
                        
                except Exception as e:
                    self._log(f"  Error parsing team transfer: {e}")
                    continue
        
        self._log(f"  Found {len(arrivals)} arrivals, {len(departures)} departures")
        return arrivals, departures
    
    # =========================================================================
    # VALUATION SCRAPING
    # =========================================================================
    
    def get_player_valuations(self, player: Player) -> List[Valuation]:
        """
        Get market value history for a player.
        
        Args:
            player: Player object
        
        Returns:
            List of Valuation objects
        """
        if not player.profile_url:
            return []
        
        # Navigate to market value page
        mv_url = player.profile_url.replace("/profil/", "/marktwertverlauf/")
        
        self._log(f"  Fetching valuations for: {player.name}")
        soup = self._fetch_page(mv_url)
        
        if not soup:
            return []
        
        valuations = []
        
        # Look for the chart data in JavaScript
        scripts = soup.select("script")
        for script in scripts:
            if script.string and "series" in script.string and "data" in script.string:
                # Extract data points
                data_match = re.findall(r"\{[^}]*'y':\s*(\d+)[^}]*'datum_mw':\s*'([^']+)'[^}]*\}", script.string)
                
                for value_str, date_str in data_match:
                    try:
                        # Parse date (format varies)
                        val_date = None
                        for fmt in ["%b %d, %Y", "%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"]:
                            try:
                                val_date = datetime.strptime(date_str.strip(), fmt).date()
                                break
                            except ValueError:
                                continue
                        
                        if not val_date:
                            continue
                        
                        value = float(value_str)
                        
                        valuation = Valuation(
                            valuation_id=self._generate_id(player.player_id, date_str),
                            player_id=player.player_id,
                            player_name=player.name,
                            valuation_amount=value,
                            valuation_date=val_date,
                            club_at_valuation=player.current_club,
                        )
                        valuations.append(valuation)
                        
                    except Exception as e:
                        continue
        
        # If no chart data, try table
        if not valuations:
            rows = soup.select("div.responsive-table table tbody tr")
            for row in rows:
                try:
                    cells = row.select("td")
                    if len(cells) < 3:
                        continue
                    
                    date_cell = cells[0]
                    value_cell = cells[1]
                    club_cell = cells[2] if len(cells) > 2 else None
                    
                    date_text = date_cell.text.strip()
                    val_date = None
                    for fmt in ["%b %d, %Y", "%d.%m.%Y", "%d/%m/%Y"]:
                        try:
                            val_date = datetime.strptime(date_text, fmt).date()
                            break
                        except ValueError:
                            continue
                    
                    if not val_date:
                        continue
                    
                    value = parse_market_value(value_cell.text.strip())
                    if not value:
                        continue
                    
                    club = club_cell.text.strip() if club_cell else player.current_club
                    
                    valuation = Valuation(
                        valuation_id=self._generate_id(player.player_id, date_text),
                        player_id=player.player_id,
                        player_name=player.name,
                        valuation_amount=value,
                        valuation_date=val_date,
                        club_at_valuation=normalize_team_name(club),
                    )
                    valuations.append(valuation)
                    
                except Exception as e:
                    continue
        
        self._log(f"    Found {len(valuations)} valuations")
        return valuations
    
    # =========================================================================
    # MAIN SCRAPING METHODS
    # =========================================================================
    
    def scrape_team_full(
        self,
        team_name: str,
        include_player_details: bool = True,
        include_transfers: bool = True,
        include_valuations: bool = True,
        progress_cb: Callable[[int, int], None] = None,
    ) -> Dict[str, Any]:
        """
        Scrape all data for a team.
        
        Args:
            team_name: Team name to scrape
            include_player_details: Scrape detailed player info
            include_transfers: Scrape transfer history
            include_valuations: Scrape market value history
            progress_cb: Progress callback (current, total)
        
        Returns:
            Dictionary with team, players, transfers, valuations
        """
        result = {
            "team": None,
            "players": [],
            "transfers": [],
            "valuations": [],
            "arrivals": [],
            "departures": [],
        }
        
        # Scrape team
        team = self.scrape_team(team_name=team_name)
        if not team:
            self._log(f"Could not find team: {team_name}")
            return result
        
        result["team"] = team
        
        # Scrape players
        players = self.get_team_players(team)
        result["players"] = players
        
        total_steps = len(players)
        if include_player_details:
            total_steps += len(players)
        if include_transfers:
            total_steps += len(players) + 1  # +1 for team transfers
        if include_valuations:
            total_steps += len(players)
        
        current_step = 0
        
        # Detailed player info
        if include_player_details:
            for player in players:
                self.scrape_player_details(player)
                current_step += 1
                if progress_cb:
                    progress_cb(current_step, total_steps)
        
        # Player transfers and valuations
        all_transfers = []
        all_valuations = []
        
        if include_transfers or include_valuations:
            for player in players:
                if include_transfers:
                    transfers = self.get_player_transfers(player)
                    all_transfers.extend(transfers)
                    current_step += 1
                    if progress_cb:
                        progress_cb(current_step, total_steps)
                
                if include_valuations:
                    valuations = self.get_player_valuations(player)
                    all_valuations.extend(valuations)
                    current_step += 1
                    if progress_cb:
                        progress_cb(current_step, total_steps)
        
        result["transfers"] = all_transfers
        result["valuations"] = all_valuations
        
        # Team transfers (arrivals/departures)
        if include_transfers:
            arrivals, departures = self.get_team_transfers(team)
            result["arrivals"] = arrivals
            result["departures"] = departures
            current_step += 1
            if progress_cb:
                progress_cb(current_step, total_steps)
        
        return result
    
    def scrape_league_full(
        self,
        league: str,
        include_player_details: bool = False,
        include_transfers: bool = True,
        include_valuations: bool = False,
        progress_cb: Callable[[int, int, str], None] = None,
    ) -> Dict[str, Any]:
        """
        Scrape all teams in a league.
        
        Args:
            league: League name
            include_player_details: Scrape detailed player info
            include_transfers: Scrape transfer history
            include_valuations: Scrape market value history
            progress_cb: Progress callback (current, total, team_name)
        
        Returns:
            Dictionary with teams, all_players, all_transfers, all_valuations
        """
        result = {
            "league": league,
            "season": self.season,
            "teams": [],
            "all_players": [],
            "all_transfers": [],
            "all_valuations": [],
        }
        
        # Get league teams
        team_list = self.get_league_teams(league)
        
        if not team_list:
            self._log(f"No teams found for league: {league}")
            return result
        
        total_teams = len(team_list)
        
        for i, team_info in enumerate(team_list):
            team_name = team_info["team_name"]
            self._log(f"\n[{i+1}/{total_teams}] Processing: {team_name}")
            
            if progress_cb:
                progress_cb(i + 1, total_teams, team_name)
            
            team_data = self.scrape_team_full(
                team_name=team_name,
                include_player_details=include_player_details,
                include_transfers=include_transfers,
                include_valuations=include_valuations,
            )
            
            if team_data["team"]:
                result["teams"].append(team_data["team"])
                result["all_players"].extend(team_data["players"])
                result["all_transfers"].extend(team_data["transfers"])
                result["all_transfers"].extend(team_data["arrivals"])
                result["all_transfers"].extend(team_data["departures"])
                result["all_valuations"].extend(team_data["valuations"])
        
        return result
    
    # =========================================================================
    # SAVE METHODS
    # =========================================================================
    
    def save_results(
        self,
        data: Dict[str, Any],
        prefix: str = "transfermarkt",
    ) -> None:
        """
        Save scraping results to files.
        
        Args:
            data: Scraped data dictionary
            prefix: Filename prefix
        """
        timestamp = datetime.now().strftime("%Y%m%d")
        
        # Save team(s)
        if "team" in data and data["team"]:
            team = data["team"]
            file_name = f"{prefix}_{team.name.lower().replace(' ', '_')}_{self.season_year}"
            write_dict_data({"team": team.to_dict()}, file_name)
        
        if "teams" in data and data["teams"]:
            teams_data = [t.to_dict() for t in data["teams"]]
            file_name = f"{prefix}_{data.get('league', 'league')}_{self.season_year}_teams"
            write_dict_data({"teams": teams_data}, file_name)
            write_list_to_csv(teams_data, file_name)
        
        # Save players
        if "players" in data and data["players"]:
            players_data = [p.to_dict() for p in data["players"]]
            team_name = data["team"].name if data.get("team") else "team"
            file_name = f"{prefix}_{team_name.lower().replace(' ', '_')}_{self.season_year}_players"
            write_dict_data({"players": players_data}, file_name)
            write_list_to_csv(players_data, file_name)
        
        if "all_players" in data and data["all_players"]:
            players_data = [p.to_dict() for p in data["all_players"]]
            file_name = f"{prefix}_{data.get('league', 'league')}_{self.season_year}_players"
            write_dict_data({"players": players_data}, file_name)
            write_list_to_csv(players_data, file_name)
        
        # Save transfers
        all_transfers = data.get("transfers", []) + data.get("arrivals", []) + data.get("departures", []) + data.get("all_transfers", [])
        if all_transfers:
            # Deduplicate
            seen = set()
            unique_transfers = []
            for t in all_transfers:
                if t.transfer_id not in seen:
                    seen.add(t.transfer_id)
                    unique_transfers.append(t)
            
            transfers_data = [t.to_dict() for t in unique_transfers]
            if data.get("team"):
                file_name = f"{prefix}_{data['team'].name.lower().replace(' ', '_')}_{self.season_year}_transfers"
            else:
                file_name = f"{prefix}_{data.get('league', 'league')}_{self.season_year}_transfers"
            write_dict_data({"transfers": transfers_data}, file_name)
            write_list_to_csv(transfers_data, file_name)
        
        # Save valuations
        all_valuations = data.get("valuations", []) + data.get("all_valuations", [])
        if all_valuations:
            valuations_data = [v.to_dict() for v in all_valuations]
            if data.get("team"):
                file_name = f"{prefix}_{data['team'].name.lower().replace(' ', '_')}_{self.season_year}_valuations"
            else:
                file_name = f"{prefix}_{data.get('league', 'league')}_{self.season_year}_valuations"
            write_dict_data({"valuations": valuations_data}, file_name)
            write_list_to_csv(valuations_data, file_name)
        
        self._log(f"\nResults saved with prefix: {prefix}")


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def main():
    """Command-line entry point for scraper."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Transfermarkt Football Data Scraper")
    parser.add_argument("--team", "-t", type=str, help="Team name to scrape")
    parser.add_argument("--league", "-l", type=str, help="League to scrape (e.g., 'laliga', 'premier')")
    parser.add_argument("--season", "-s", type=str, help="Season (e.g., '2024-2025')")
    parser.add_argument("--no-details", action="store_true", help="Skip detailed player scraping")
    parser.add_argument("--no-transfers", action="store_true", help="Skip transfer history")
    parser.add_argument("--no-valuations", action="store_true", help="Skip valuation history")
    parser.add_argument("--delay", "-d", type=float, default=0.0, help="Delay between requests")
    parser.add_argument("--quiet", "-q", action="store_true", help="Quiet mode")
    
    args = parser.parse_args()
    
    scraper = TransfermarktScraper(
        season=args.season,
        delay=args.delay,
        verbose=not args.quiet,
    )
    
    if args.team:
        data = scraper.scrape_team_full(
            team_name=args.team,
            include_player_details=not args.no_details,
            include_transfers=not args.no_transfers,
            include_valuations=not args.no_valuations,
        )
        scraper.save_results(data)
        
    elif args.league:
        data = scraper.scrape_league_full(
            league=args.league,
            include_player_details=not args.no_details,
            include_transfers=not args.no_transfers,
            include_valuations=not args.no_valuations,
        )
        scraper.save_results(data)
        
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
