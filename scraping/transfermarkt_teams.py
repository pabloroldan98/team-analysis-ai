# scraping/transfermarkt_teams.py
"""
Scraper for team data from Transfermarkt.
Only extracts team-level information (no players).
"""
from __future__ import annotations

import re
from typing import List, Optional

from scraping.base_scraper import BaseScraper
from team import Team


class TransfermarktTeamsScraper(BaseScraper):
    """Scraper for team information from Transfermarkt."""
    
    LEAGUE_COUNTRY_MAP = {
        "laliga": "Spain",
        "segunda": "Spain",
        "premier": "England",
        "championship": "England",
        "bundesliga": "Germany",
        "seriea": "Italy",
        "ligue1": "France",
        "eredivisie": "Netherlands",
        "liga_portugal": "Portugal",
    }
    
    def scrape_team(self, team_id: str, team_url: str = None) -> Optional[Team]:
        """
        Scrape detailed information for a single team.
        
        Args:
            team_id: Transfermarkt team ID
            team_url: Optional team URL (will be constructed if not provided)
        
        Returns:
            Team object or None
        """
        if not team_url:
            team_url = f"{self.BASE_URL}/verein/kader/verein/{team_id}/saison_id/{self.season_year}"
        
        # Ensure we're on the kader (squad) page for better data
        if "/kader/" not in team_url:
            team_url = team_url.replace("/startseite/", "/kader/").replace("/spielplan/", "/kader/")
            if "/saison_id/" not in team_url:
                team_url = f"{team_url}/saison_id/{self.season_year}"
        
        self.log(f"Scraping team: {team_id}")
        soup = self.fetch_page(team_url)
        
        if not soup:
            return None
        
        # Get team name from header
        header = soup.select_one("header.data-header h1")
        name = header.text.strip() if header else ""
        
        # Get logo URL
        logo_img = soup.select_one("div.data-header__profile-container img.data-header__profile-image")
        logo_url = logo_img.get("src", "") if logo_img else ""
        
        # Get market value
        market_value_el = soup.select_one("a.data-header__market-value-wrapper")
        total_market_value = None
        if market_value_el:
            total_market_value = self.parse_market_value(market_value_el.text)
        
        # Get squad size, average age, foreigners
        squad_size = None
        average_age = None
        foreigners_count = None
        national_team_players = None
        
        for item in soup.select("li.data-header__label"):
            text = item.text.strip().lower()
            value_span = item.select_one("span.data-header__content")
            if value_span:
                value_text = value_span.text.strip()
                
                if "squad size" in text or "plantilla" in text or "kader" in text:
                    try:
                        squad_size = int(re.search(r"(\d+)", value_text).group(1))
                    except:
                        pass
                elif "average age" in text or "edad media" in text or "altersdurchschnitt" in text:
                    try:
                        average_age = float(value_text.replace(",", "."))
                    except:
                        pass
                elif "foreigner" in text or "extranjero" in text or "legionäre" in text:
                    try:
                        foreigners_count = int(re.search(r"(\d+)", value_text).group(1))
                    except:
                        pass
                elif "national" in text or "nacional" in text:
                    try:
                        national_team_players = int(re.search(r"(\d+)", value_text).group(1))
                    except:
                        pass
        
        # Get stadium info
        stadium_name = ""
        stadium_capacity = None
        stadium_el = soup.select_one("span.mediumpunkt a[href*='stadion']")
        if stadium_el:
            stadium_name = stadium_el.text.strip()
        
        # Try to get league info from breadcrumb
        league = ""
        league_id = ""
        country = ""
        breadcrumb = soup.select("div.breadcrumb a")
        for link in breadcrumb:
            href = link.get("href", "")
            if "/wettbewerb/" in href:
                league = link.text.strip()
                match = re.search(r"/wettbewerb/(\w+)", href)
                if match:
                    league_id = match.group(1)
        
        # Infer country from league
        for lg, ctry in self.LEAGUE_COUNTRY_MAP.items():
            if lg in league.lower().replace(" ", ""):
                country = ctry
                break
        
        return Team(
            team_id=team_id,
            name=name,
            league=league,
            league_id=league_id,
            country=country,
            season=self.season,
            squad_size=squad_size,
            average_age=average_age,
            total_market_value=total_market_value,
            foreigners_count=foreigners_count,
            national_team_players=national_team_players,
            stadium_name=stadium_name,
            stadium_capacity=stadium_capacity,
            logo_url=logo_url,
            profile_url=team_url,
        )
    
    def scrape_league_teams(self, league: str) -> List[Team]:
        """
        Scrape all teams from a league.
        
        Args:
            league: League identifier (e.g., "laliga", "premier")
        
        Returns:
            List of Team objects
        """
        # Get basic team info from league page
        team_infos = self.get_league_teams(league)
        
        if not team_infos:
            self.log(f"No teams found for league: {league}")
            return []
        
        teams = []
        for i, info in enumerate(team_infos):
            self.log(f"  [{i+1}/{len(team_infos)}] {info['team_name']}")
            
            team = self.scrape_team(
                team_id=info["team_id"],
                team_url=info["team_url"]
            )
            
            if team:
                # Override league info from context
                team.league = league
                team.country = self.LEAGUE_COUNTRY_MAP.get(league.lower(), "")
                teams.append(team)
        
        return teams
    
    def run(self, leagues: List[str] = None) -> dict:
        """
        Run the scraper for specified leagues.
        
        Args:
            leagues: List of league identifiers. Defaults to top 5.
        
        Returns:
            Dict with league -> list of teams
        """
        if leagues is None:
            leagues = ["laliga", "premier", "bundesliga", "seriea", "ligue1"]
        
        all_teams = {}
        
        for league in leagues:
            self.log(f"\n=== Scraping {league.upper()} ===")
            teams = self.scrape_league_teams(league)
            all_teams[league] = teams
            
            # Save per league
            teams_data = [t.to_dict() for t in teams]
            self.save_json(teams_data, f"teams_{league}_{self.season}")
        
        # Save combined
        all_teams_data = {}
        for league, teams in all_teams.items():
            all_teams_data[league] = [t.to_dict() for t in teams]
        
        self.save_json(all_teams_data, f"teams_all_{self.season}")
        
        return all_teams


if __name__ == "__main__":
    scraper = TransfermarktTeamsScraper()
    scraper.run()
