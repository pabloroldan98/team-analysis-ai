# scraping/transfermarkt_teams.py
"""
Scraper for team data from Transfermarkt.
Extracts team-level information.
"""
from __future__ import annotations

import re
from typing import List, Optional, Dict

from scraping.base_scraper import BaseScraper
from team import Team


class TransfermarktTeamsScraper(BaseScraper):
    """Scraper for team information from Transfermarkt."""
    
    def scrape_team(self, team_id: str, team_url: str = None, league_key: str = "") -> Optional[Team]:
        """
        Scrape detailed information for a single team.
        
        Args:
            team_id: Transfermarkt team ID
            team_url: Optional team URL (will be constructed if not provided)
            league_key: League identifier for context
        
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
        
        # Get logo URL (try multiple selectors)
        logo_url = ""
        logo_img = soup.select_one("div.data-header__profile-container img.data-header__profile-image")
        if not logo_img:
            logo_img = soup.select_one("div.data-header__profile-container img")
        if not logo_img:
            logo_img = soup.select_one("img.data-header__profile-image")
        if logo_img:
            logo_url = logo_img.get("src", "") or logo_img.get("data-src", "")

        # Get market value
        market_value_el = soup.select_one("a.data-header__market-value-wrapper")
        total_market_value = None
        if market_value_el:
            total_market_value = self.parse_market_value(market_value_el.text)
        
        # Get squad size, average age, foreigners, stadium
        squad_size = None
        average_age = None
        foreign_players_count = None
        national_players_count = None
        stadium_name = ""
        stadium_capacity = None
        
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
            if "squad size" in label_text or "squad" in label_text or "kader" in label_text:
                match = re.search(r"(\d+)", content_text)
                if match:
                    squad_size = int(match.group(1))
            
            elif "ø-age" in label_text or "average age" in label_text or "-age" in label_text:
                match = re.search(r"([\d,.]+)", content_text.replace(",", "."))
                if match:
                    try:
                        average_age = float(match.group(1))
                    except ValueError:
                        pass
            
            elif "foreigner" in label_text or "legionäre" in label_text:
                match = re.search(r"(\d+)", content_text)
                if match:
                    foreign_players_count = int(match.group(1))
            
            elif "national" in label_text and "foreigner" not in label_text:
                match = re.search(r"(\d+)", content_text)
                if match:
                    national_players_count = int(match.group(1))
            
            elif "stadium" in label_text or "estadio" in label_text or "stadion" in label_text:
                # Format: "Etihad Stadium  55.097 Seats" or "Santiago Bernabéu  81.044 Seats"
                # Extract stadium name (text before the number) and capacity
                stadium_link = content_span.select_one("a")
                if stadium_link:
                    stadium_name = stadium_link.get_text(strip=True)
                
                # Extract capacity - look for number followed by "Seats" or similar
                # Handle formats like "55.097" (European) or "55,097" or "55097"
                capacity_match = re.search(r"([\d.,]+)\s*(?:seats|plätze|asientos|posti)", content_text, re.IGNORECASE)
                if capacity_match:
                    capacity_str = capacity_match.group(1).replace(".", "").replace(",", "")
                    try:
                        stadium_capacity = int(capacity_str)
                    except ValueError:
                        pass
        
        # Try to get league info from breadcrumb or context
        league = ""
        league_id = ""
        country = ""
        
        if league_key:
            info = self.LEAGUE_URLS.get(league_key, {})
            if isinstance(info, dict):
                league = info.get("name", league_key)
                league_id = info.get("id", "")
                country = info.get("country", "")
        
        if not league:
            breadcrumb = soup.select("div.breadcrumb a")
            for link in breadcrumb:
                href = link.get("href", "")
                if "/wettbewerb/" in href:
                    league = link.text.strip()
                    match = re.search(r"/wettbewerb/(\w+)", href)
                    if match:
                        league_id = match.group(1)
        
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
            foreign_players_count=foreign_players_count,
            national_players_count=national_players_count,
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
        team_infos = self.get_league_teams(league)
        
        if not team_infos:
            self.log(f"No teams found for league: {league}")
            return []
        
        teams = []
        
        for i, info in enumerate(team_infos):
            self.log(f"  [{i+1}/{len(team_infos)}] {info['team_name']}")
            
            team = self.scrape_team(
                team_id=info["team_id"],
                team_url=info["team_url"],
                league_key=league
            )
            
            if team:
                teams.append(team)
        
        self.log(f"  Found {len(teams)} teams")
        return teams
    
    def run(self, leagues: List[str] = None) -> Dict[str, List[Team]]:
        """
        Run the scraper for specified leagues.
        
        Args:
            leagues: List of league identifiers. Defaults to top 5.
        
        Returns:
            Dict with league_key -> list of Team objects
        """
        if leagues is None:
            leagues = ["laliga", "premier", "bundesliga", "seriea", "ligue1"]
        
        all_teams = {}
        
        for league in leagues:
            self.log(f"\n=== Scraping teams from {league.upper()} ===")
            teams = self.scrape_league_teams(league)
            all_teams[league] = teams
            
            # Save teams for this league
            teams_data = [t.to_dict() for t in teams]
            self.save_json(teams_data, f"teams_{league}_{self.season}")
        
        # Save all teams combined
        all_teams_data = {}
        for league_key, teams in all_teams.items():
            all_teams_data[league_key] = [t.to_dict() for t in teams]
        self.save_json(all_teams_data, f"teams_all_{self.season}")
        
        return all_teams


if __name__ == "__main__":
    scraper = TransfermarktTeamsScraper()
    scraper.run()
