# scraping/transfermarkt_leagues.py
"""
Scraper for league data from Transfermarkt.
Only extracts league-level information.
"""
from __future__ import annotations

import re
from typing import List, Optional, Dict

from scraping.base_scraper import BaseScraper
from league import League


class TransfermarktLeaguesScraper(BaseScraper):
    """Scraper for league information from Transfermarkt."""
    
    # Transfermarkt API base URL (fallback for market values)
    TM_API_URL = "https://tmapi-alpha.transfermarkt.technology"
    
    # LEAGUE_INFO is inherited from BaseScraper
    
    def _fetch_league_market_value(self, league_id: str) -> Optional[float]:
        """Fetch total market value for a league via the TM API.
        
        API: ``/competition/{league_id}`` → ``data.totalMarketValue.value``
        
        Returns the value in EUR or None on failure.
        """
        if not league_id:
            return None
        
        import time as _time
        import requests
        
        api_url = f"{self.TM_API_URL}/competition/{league_id}"
        
        for attempt in range(1, self.max_retries + 1):
            try:
                _time.sleep(self.delay)
                resp = requests.get(api_url, timeout=60)
                
                if resp.status_code == 200:
                    data = resp.json()
                    tmv = (data.get("data") or {}).get("totalMarketValue") or {}
                    value = tmv.get("value")
                    if value is not None:
                        self.log(f"  API fallback: total_market_value = {value}")
                        return float(value)
                    return None
                
                if resp.status_code in (429, 500, 502, 503, 504):
                    self.log(f"    API attempt {attempt}/{self.max_retries}: HTTP {resp.status_code}")
                else:
                    self.log(f"    API HTTP {resp.status_code} for {league_id}")
                    return None
                
            except Exception as e:
                self.log(f"    API attempt {attempt}/{self.max_retries}: {e!r}")
            
            if attempt < self.max_retries:
                _time.sleep(self.retry_pause)
        
        return None
    
    def scrape_league(self, league_key: str) -> Optional[League]:
        """
        Scrape information for a single league.
        
        Args:
            league_key: League identifier (e.g., "laliga", "premier")
        
        Returns:
            League object or None
        """
        league_url = self.get_league_url(league_key)
        if not league_url:
            self.log(f"Unknown league: {league_key}")
            return None
        
        url = f"{self.BASE_URL}{league_url}/saison_id/{self.season_year}"
        self.log(f"Scraping league: {league_key}")
        soup = self.fetch_page(url)
        
        if not soup:
            return None
        
        info = self.LEAGUE_INFO.get(league_key, {})
        
        # Get league name from header
        header = soup.select_one("header.data-header h1")
        name = header.text.strip() if header else info.get("name", league_key)
        
        # Get total market value from the big header value
        total_market_value = None
        # Try multiple selectors – TM sometimes uses <a>, sometimes <div>
        value_el = (
            soup.select_one("a.data-header__market-value-wrapper")
            or soup.select_one("div.data-header__market-value-wrapper")
            or soup.select_one(".data-header__market-value-wrapper")
        )
        if value_el:
            # Grab the full visible text, then strip away known labels
            raw = value_el.get_text(separator=" ", strip=True)
            for noise in ("Total Market Value", "Gesamtmarktwert",
                          "Last update", "Letzte Aktualisierung"):
                raw = raw.replace(noise, "")
            raw = re.sub(r"\b[A-Z][a-z]{2}\s+\d{1,2},?\s*\d{4}\b", "", raw)
            raw = raw.strip()
            if raw:
                total_market_value = self.parse_market_value(raw)
        
        # Fallback: use the TM API if HTML scraping didn't get the value
        if total_market_value is None:
            league_id = info.get("id", "")
            api_value = self._fetch_league_market_value(league_id)
            if api_value is not None:
                total_market_value = api_value
        
        # Get stats from header labels
        num_teams = 0
        num_players = 0
        average_age = None
        average_market_value = None
        most_valuable_player = ""
        
        # Find all data-header__label items
        for item in soup.select("li.data-header__label"):
            # Get the label text (before the span)
            label_text = ""
            for child in item.children:
                if hasattr(child, 'name') and child.name == 'span':
                    break
                if isinstance(child, str):
                    label_text += child
            label_text = label_text.strip().lower()
            
            # Get the content from span
            content_span = item.select_one("span.data-header__content")
            if not content_span:
                continue
            
            content_text = content_span.get_text(strip=True)
            
            # Parse based on label
            if "number of" in label_text or "teams" in label_text or "clubs" in label_text:
                match = re.search(r"(\d+)", content_text)
                if match:
                    num_teams = int(match.group(1))
            
            elif "players" in label_text and "valuable" not in label_text:
                match = re.search(r"(\d+)", content_text)
                if match:
                    num_players = int(match.group(1))
            
            elif "ø-age" in label_text or "average age" in label_text or "-age" in label_text:
                # Try to extract age like "27.3" or "27,3"
                match = re.search(r"([\d,.]+)", content_text.replace(",", "."))
                if match:
                    try:
                        average_age = float(match.group(1))
                    except ValueError:
                        pass
            
            elif "ø-market value" in label_text or "market value" in label_text and "total" not in label_text:
                average_market_value = self.parse_market_value(content_text)
            
            elif "most valuable" in label_text:
                # Extract player name (everything before the value)
                # Format: "Lamine Yamal €200.00m"
                # Get the anchor text if exists
                player_link = content_span.select_one("a")
                if player_link:
                    most_valuable_player = player_link.get_text(strip=True)
                else:
                    # Try to extract name before € symbol
                    match = re.match(r"([^€]+)", content_text)
                    if match:
                        most_valuable_player = match.group(1).strip()
        
        # Get logo (try multiple attributes)
        logo_url = ""
        logo_img = soup.select_one("div.data-header__profile-container img")
        if logo_img:
            logo_url = logo_img.get("src", "") or logo_img.get("data-src", "")
        
        # Extract league_id from URL
        league_id = info.get("id", "")
        match = re.search(r"/wettbewerb/(\w+)", league_url)
        if match:
            league_id = match.group(1)
        
        # Get team IDs from the page
        team_ids = []
        team_infos = self.get_league_teams(league_key)
        if team_infos and not num_teams:
            num_teams = len(team_infos)
        
        return League(
            league_id=league_id,
            name=name,
            country=info.get("country", ""),
            season=self.season,
            tier=info.get("tier", 1),
            total_market_value=total_market_value,
            num_teams=num_teams,
            num_players=num_players,
            average_age=average_age,
            average_market_value=average_market_value,
            most_valuable_player=most_valuable_player,
            logo_url=logo_url,
            profile_url=url,
        )
    
    def run(self, leagues: List[str] = None) -> Dict[str, League]:
        """
        Run the scraper for specified leagues.
        
        Args:
            leagues: List of league identifiers. Defaults to top 5.
        
        Returns:
            Dict with league_key -> League object
        """
        if leagues is None:
            leagues = ["laliga", "premier", "bundesliga", "seriea", "ligue1"]
        
        all_leagues = {}
        loaded_data: list = []  # dicts loaded from existing files
        loaded_by_id: dict = {}

        # Load existing data for incremental scraping
        skip_league_ids: set = set()
        if self.use_downloaded_data:
            existing_all = self.load_json(f"leagues_all_{self.season}")
            if existing_all:
                skip_league_ids = {lg["league_id"] for lg in existing_all if "league_id" in lg}
                loaded_by_id = {lg["league_id"]: lg for lg in existing_all if "league_id" in lg}
                loaded_data = existing_all
                self.log(f"\nIncremental mode: {len(skip_league_ids)} leagues already scraped")
        
        for league_key in leagues:
            # Skip if already present in existing data
            league_id = self.LEAGUE_INFO.get(league_key, {}).get("id", "")
            if league_id and league_id in skip_league_ids:
                self.log(f"\n=== {league_key.upper()}: already scraped, skipping ===")
                existing = loaded_by_id.get(league_id)
                self.save_json(
                    [existing] if existing else [],
                    f"leagues_{league_key}_{self.season}",
                    validate=False,
                    id_field="league_id",
                    data_type="leagues",
                )
                continue
            
            self.log(f"\n=== Scraping {league_key.upper()} ===")
            league = self.scrape_league(league_key)
            
            if league:
                all_leagues[league_key] = league
                # Save per-league file as list with one dict
                self.save_json(
                    [league.to_dict()],
                    f"leagues_{league_key}_{self.season}",
                    min_items=1,
                    id_field="league_id",
                    data_type="leagues"
                )
        
        # Save combined _all_ file (new + existing)
        all_leagues_data = [v.to_dict() for v in all_leagues.values()]
        all_leagues_data.extend(loaded_data)
        self.save_json(
            all_leagues_data,
            f"leagues_all_{self.season}",
            min_items=1,
            id_field="league_id",
            data_type="leagues"
        )
        
        return all_leagues
    
    @classmethod
    def get_available_leagues(cls) -> List[str]:
        """Get list of available league keys."""
        return list(cls.LEAGUE_INFO.keys())


if __name__ == "__main__":
    scraper = TransfermarktLeaguesScraper()
    scraper.run()
