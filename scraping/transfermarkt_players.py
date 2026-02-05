# scraping/transfermarkt_players.py
"""
Scraper for player data from Transfermarkt.
Extracts player information from teams.
"""
from __future__ import annotations

import re
from typing import List, Optional, Dict

from scraping.base_scraper import BaseScraper
from player import Player


class TransfermarktPlayersScraper(BaseScraper):
    """Scraper for player information from Transfermarkt."""
    
    def scrape_team_players(self, team_id: str, team_name: str = "", team_url: str = None) -> List[Player]:
        """
        Scrape all players from a team's squad page.
        
        Args:
            team_id: Transfermarkt team ID
            team_name: Team name for reference
            team_url: Optional team URL
        
        Returns:
            List of Player objects
        """
        # Build URL to squad page
        if not team_url:
            url = f"{self.BASE_URL}/-/kader/verein/{team_id}/saison_id/{self.season_year}"
        else:
            url = team_url.replace("/startseite/", "/kader/")
            if "/saison_id/" not in url:
                url = f"{url}/saison_id/{self.season_year}"
        
        self.log(f"Scraping players from: {team_name or team_id}")
        soup = self.fetch_page(url)
        
        if not soup:
            return []
        
        # Get team name if not provided
        if not team_name:
            header = soup.select_one("header.data-header h1")
            team_name = header.text.strip() if header else ""
        
        players = []
        
        # Find player table rows
        for row in soup.select("table.items tbody tr.odd, table.items tbody tr.even"):
            player = self._parse_player_row(row, team_id, team_name)
            if player:
                players.append(player)
        
        self.log(f"  Found {len(players)} players")
        return players
    
    def _parse_player_row(self, row, team_id: str, team_name: str) -> Optional[Player]:
        """Parse a player row from the squad table."""
        try:
            # Player link and name
            player_link = row.select_one("td.hauptlink a[href*='/spieler/']")
            if not player_link:
                return None
            
            href = player_link.get("href", "")
            player_id = self.extract_player_id(href)
            name = player_link.text.strip()
            
            if not player_id or not name:
                return None
            
            # Image URL
            img = row.select_one("img.bilderrahmen-fixed")
            img_url = img.get("data-src", "") or img.get("src", "") if img else ""
            
            # Position (from position column)
            position = "N/A"
            pos_td = row.select_one("td.posrela table tr:last-child td")
            if pos_td:
                position = pos_td.text.strip()
            
            # Shirt number
            shirt_number = None
            shirt_td = row.select_one("div.rn_nummer")
            if shirt_td:
                try:
                    shirt_number = int(shirt_td.text.strip())
                except:
                    pass
            
            # Age
            age = None
            for td in row.select("td.zentriert"):
                text = td.text.strip()
                if text.isdigit() and 15 < int(text) < 50:
                    age = int(text)
                    break
            
            # Birth date (often in format "MMM DD, YYYY (age)")
            birth_date = None
            birth_td = row.select("td.zentriert")
            for td in birth_td:
                text = td.text.strip()
                if "(" in text and ")" in text:
                    # Extract date part
                    date_match = re.search(r"([A-Za-z]+ \d+, \d{4})", text)
                    if date_match:
                        birth_date = date_match.group(1)
            
            # Nationality (from flag images)
            nationality = ""
            second_nationality = ""
            flags = row.select("td.zentriert img.flaggenrahmen")
            if len(flags) >= 1:
                nationality = flags[0].get("title", "")
            if len(flags) >= 2:
                second_nationality = flags[1].get("title", "")
            
            # Market value
            market_value = None
            value_td = row.select_one("td.rechts.hauptlink a, td.rechts.hauptlink")
            if value_td:
                market_value = self.parse_market_value(value_td.text)
            
            return Player(
                player_id=player_id,
                name=name,
                team=team_name,
                team_id=team_id,
                position=position,
                age=age,
                birth_date=birth_date,
                nationality=nationality,
                second_nationality=second_nationality,
                shirt_number=shirt_number,
                market_value=market_value,
                img_url=img_url,
                profile_url=f"{self.BASE_URL}{href}",
                season=self.season,
            )
        except Exception as e:
            self.log(f"  Error parsing player row: {e}")
            return None
    
    def scrape_player_details(self, player_id: str, player: Player = None) -> Optional[Player]:
        """
        Scrape detailed information for a single player.
        
        Args:
            player_id: Transfermarkt player ID
            player: Existing player object to update
        
        Returns:
            Updated Player object or new one
        """
        url = f"{self.BASE_URL}/-/profil/spieler/{player_id}"
        
        self.log(f"Scraping player details: {player_id}")
        soup = self.fetch_page(url)
        
        if not soup:
            return player
        
        if player is None:
            player = Player(player_id=player_id, name="")
        
        # Name from header
        header = soup.select_one("h1.data-header__headline-wrapper")
        if header:
            name_text = header.text.strip()
            # Remove shirt number if present
            name_text = re.sub(r"#\d+", "", name_text).strip()
            player.name = name_text
        
        # Profile image
        img = soup.select_one("img.data-header__profile-image")
        if img:
            player.img_url = img.get("src", "")
        
        # Market value from header
        value_el = soup.select_one("a.data-header__market-value-wrapper")
        if value_el:
            player.market_value = self.parse_market_value(value_el.text)
        
        # Parse info table
        for item in soup.select("li.data-header__label, span.info-table__content"):
            label = item.select_one("span.data-header__label, span.info-table__content--regular")
            value = item.select_one("span.data-header__content, span.info-table__content--bold")
            
            if not label or not value:
                continue
            
            label_text = label.text.strip().lower()
            value_text = value.text.strip()
            
            if "date of birth" in label_text or "fecha" in label_text or "geburt" in label_text:
                player.birth_date = value_text
                # Extract age
                age_match = re.search(r"\((\d+)\)", value_text)
                if age_match:
                    player.age = int(age_match.group(1))
            
            elif "height" in label_text or "altura" in label_text or "größe" in label_text:
                height_match = re.search(r"(\d+)", value_text.replace(",", ""))
                if height_match:
                    player.height = int(height_match.group(1))
            
            elif "foot" in label_text or "pie" in label_text or "fuß" in label_text:
                player.preferred_foot = value_text
            
            elif "position" in label_text or "posición" in label_text:
                player.position = value_text
            
            elif "contract" in label_text or "contrato" in label_text or "vertrag" in label_text:
                player.contract_expires = value_text
            
            elif "joined" in label_text or "fichado" in label_text:
                player.joined_date = value_text
        
        # Current club
        club_link = soup.select_one("span.data-header__club a")
        if club_link:
            player.team = club_link.text.strip()
            href = club_link.get("href", "")
            player.team_id = self.extract_team_id(href) or player.team_id
        
        return player
    
    def scrape_league_players(self, league: str, include_details: bool = False) -> Dict[str, List[Player]]:
        """
        Scrape all players from a league.
        
        Args:
            league: League identifier (e.g., "laliga", "premier")
            include_details: Whether to fetch detailed player info
        
        Returns:
            Dict mapping team_id -> list of players
        """
        team_infos = self.get_league_teams(league)
        
        if not team_infos:
            self.log(f"No teams found for league: {league}")
            return {}
        
        all_players = {}
        
        for i, info in enumerate(team_infos):
            self.log(f"  [{i+1}/{len(team_infos)}] {info['team_name']}")
            
            players = self.scrape_team_players(
                team_id=info["team_id"],
                team_name=info["team_name"],
                team_url=info["team_url"]
            )
            
            if include_details:
                for j, player in enumerate(players):
                    self.log(f"    [{j+1}/{len(players)}] Details: {player.name}")
                    self.scrape_player_details(player.player_id, player)
            
            all_players[info["team_id"]] = players
        
        return all_players
    
    def run(self, leagues: List[str] = None, include_details: bool = False) -> dict:
        """
        Run the scraper for specified leagues.
        
        Args:
            leagues: List of league identifiers. Defaults to top 5.
            include_details: Whether to fetch detailed player info
        
        Returns:
            Dict with league -> team_id -> list of players
        """
        if leagues is None:
            leagues = ["laliga", "premier", "bundesliga", "seriea", "ligue1"]
        
        all_data = {}
        
        for league in leagues:
            self.log(f"\n=== Scraping players from {league.upper()} ===")
            players_by_team = self.scrape_league_players(league, include_details)
            all_data[league] = players_by_team
            
            # Flatten for saving
            all_players = []
            for team_id, players in players_by_team.items():
                for p in players:
                    all_players.append(p.to_dict())
            
            self.save_json(all_players, f"players_{league}_{self.season}")
        
        # Save combined
        combined = []
        for league_data in all_data.values():
            for players in league_data.values():
                for p in players:
                    combined.append(p.to_dict())
        
        self.save_json(combined, f"players_all_{self.season}")
        
        return all_data


if __name__ == "__main__":
    scraper = TransfermarktPlayersScraper()
    scraper.run()
