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
    
    LEAGUE_INFO = {
        "laliga": {"name": "LaLiga", "country": "Spain", "tier": 1, "id": "ES1"},
        "segunda": {"name": "LaLiga 2", "country": "Spain", "tier": 2, "id": "ES2"},
        "premier": {"name": "Premier League", "country": "England", "tier": 1, "id": "GB1"},
        "championship": {"name": "Championship", "country": "England", "tier": 2, "id": "GB2"},
        "bundesliga": {"name": "Bundesliga", "country": "Germany", "tier": 1, "id": "L1"},
        "bundesliga2": {"name": "2. Bundesliga", "country": "Germany", "tier": 2, "id": "L2"},
        "seriea": {"name": "Serie A", "country": "Italy", "tier": 1, "id": "IT1"},
        "serieb": {"name": "Serie B", "country": "Italy", "tier": 2, "id": "IT2"},
        "ligue1": {"name": "Ligue 1", "country": "France", "tier": 1, "id": "FR1"},
        "ligue2": {"name": "Ligue 2", "country": "France", "tier": 2, "id": "FR2"},
        "eredivisie": {"name": "Eredivisie", "country": "Netherlands", "tier": 1, "id": "NL1"},
        "liga_portugal": {"name": "Liga Portugal", "country": "Portugal", "tier": 1, "id": "PO1"},
        "scottish": {"name": "Scottish Premiership", "country": "Scotland", "tier": 1, "id": "SC1"},
        "belgian": {"name": "Jupiler Pro League", "country": "Belgium", "tier": 1, "id": "BE1"},
        "turkish": {"name": "Süper Lig", "country": "Turkey", "tier": 1, "id": "TR1"},
        "russian": {"name": "Russian Premier League", "country": "Russia", "tier": 1, "id": "RU1"},
        "ukrainian": {"name": "Ukrainian Premier League", "country": "Ukraine", "tier": 1, "id": "UKR1"},
        "greek": {"name": "Super League Greece", "country": "Greece", "tier": 1, "id": "GR1"},
        "austrian": {"name": "Austrian Bundesliga", "country": "Austria", "tier": 1, "id": "A1"},
        "swiss": {"name": "Swiss Super League", "country": "Switzerland", "tier": 1, "id": "C1"},
        "mls": {"name": "MLS", "country": "USA", "tier": 1, "id": "MLS1"},
        "brazilian": {"name": "Brasileirão", "country": "Brazil", "tier": 1, "id": "BRA1"},
        "argentine": {"name": "Liga Profesional", "country": "Argentina", "tier": 1, "id": "AR1N"},
        "mexican": {"name": "Liga MX", "country": "Mexico", "tier": 1, "id": "MEX1"},
    }
    
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
        value_el = soup.select_one("a.data-header__market-value-wrapper")
        if value_el:
            total_market_value = self.parse_market_value(value_el.text)
        
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
        if team_infos:
            team_ids = [t["team_id"] for t in team_infos]
            if not num_teams:
                num_teams = len(team_ids)
        
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
            teams=team_ids,
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
        
        for league_key in leagues:
            self.log(f"\n=== Scraping {league_key.upper()} ===")
            league = self.scrape_league(league_key)
            
            if league:
                all_leagues[league_key] = league
                
                # Save individual league
                self.save_json(league.to_dict(), f"league_{league_key}_{self.season}")
        
        # Save all leagues combined
        all_leagues_data = {k: v.to_dict() for k, v in all_leagues.items()}
        self.save_json(all_leagues_data, f"leagues_all_{self.season}")
        
        return all_leagues
    
    @classmethod
    def get_available_leagues(cls) -> List[str]:
        """Get list of available league keys."""
        return list(cls.LEAGUE_INFO.keys())


if __name__ == "__main__":
    scraper = TransfermarktLeaguesScraper()
    scraper.run()
