# scraping/transfermarkt_valuations.py
"""
Scraper for player valuation history from Transfermarkt.
"""
from __future__ import annotations

import re
from typing import List, Optional, Dict
from dataclasses import dataclass

from scraping.base_scraper import BaseScraper


@dataclass
class Valuation:
    """Represents a player market valuation at a point in time."""
    valuation_id: str
    player_id: str
    player_name: str
    valuation_amount: float
    valuation_date: str
    club_at_valuation: str
    club_id_at_valuation: str
    age_at_valuation: Optional[int]
    
    def to_dict(self) -> dict:
        return {
            "valuation_id": self.valuation_id,
            "player_id": self.player_id,
            "player_name": self.player_name,
            "valuation_amount": self.valuation_amount,
            "valuation_date": self.valuation_date,
            "club_at_valuation": self.club_at_valuation,
            "club_id_at_valuation": self.club_id_at_valuation,
            "age_at_valuation": self.age_at_valuation,
        }


class TransfermarktValuationsScraper(BaseScraper):
    """Scraper for player valuation history from Transfermarkt."""
    
    def scrape_player_valuations(self, player_id: str, player_name: str = "") -> List[Valuation]:
        """
        Scrape valuation history for a single player.
        
        Args:
            player_id: Transfermarkt player ID
            player_name: Player name for reference
        
        Returns:
            List of Valuation objects
        """
        url = f"{self.BASE_URL}/-/marktwertverlauf/spieler/{player_id}"
        
        self.log(f"Scraping valuations: {player_name or player_id}")
        soup = self.fetch_page(url)
        
        if not soup:
            return []
        
        # Get player name if not provided
        if not player_name:
            header = soup.select_one("h1.data-header__headline-wrapper")
            if header:
                player_name = re.sub(r"#\d+", "", header.text).strip()
        
        valuations = []
        
        # Try to find the valuation table
        for row in soup.select("table.items tbody tr"):
            valuation = self._parse_valuation_row(row, player_id, player_name)
            if valuation:
                valuations.append(valuation)
        
        # Also try to parse from the graph data (highcharts)
        script_data = soup.select_one("script:contains('series')")
        if script_data and not valuations:
            text = script_data.string or ""
            # This would need more complex parsing of the JavaScript
            # For now, rely on the table
        
        self.log(f"  Found {len(valuations)} valuations")
        return valuations
    
    def _parse_valuation_row(self, row, player_id: str, player_name: str) -> Optional[Valuation]:
        """Parse a valuation row from the market value table."""
        try:
            cells = row.select("td")
            if len(cells) < 4:
                return None
            
            # Date (first column)
            valuation_date = cells[0].text.strip()
            
            # Age
            age_at_valuation = None
            if len(cells) > 1:
                age_text = cells[1].text.strip()
                try:
                    age_at_valuation = int(age_text)
                except:
                    pass
            
            # Club
            club_at_valuation = ""
            club_id_at_valuation = ""
            club_link = row.select_one("td a[href*='/verein/']")
            if club_link:
                club_at_valuation = club_link.text.strip() or club_link.get("title", "")
                club_id_at_valuation = self.extract_team_id(club_link.get("href", "")) or ""
            
            # Market value (last column usually)
            valuation_amount = None
            for cell in reversed(cells):
                text = cell.text.strip()
                if "€" in text or "m" in text.lower() or "k" in text.lower():
                    valuation_amount = self.parse_market_value(text)
                    if valuation_amount:
                        break
            
            if valuation_amount is None:
                return None
            
            # Generate unique ID
            valuation_id = self.generate_id(player_id, valuation_date, str(valuation_amount))
            
            return Valuation(
                valuation_id=valuation_id,
                player_id=player_id,
                player_name=player_name,
                valuation_amount=valuation_amount,
                valuation_date=valuation_date,
                club_at_valuation=club_at_valuation,
                club_id_at_valuation=club_id_at_valuation,
                age_at_valuation=age_at_valuation,
            )
        except Exception as e:
            self.log(f"  Error parsing valuation row: {e}")
            return None
    
    def scrape_team_player_valuations(self, team_id: str, player_ids: List[str] = None) -> Dict[str, List[Valuation]]:
        """
        Scrape valuations for all players in a team.
        
        Args:
            team_id: Transfermarkt team ID
            player_ids: Optional list of player IDs (will fetch from team if not provided)
        
        Returns:
            Dict mapping player_id -> list of valuations
        """
        # If no player IDs provided, we need to fetch them first
        if player_ids is None:
            from scraping.transfermarkt_players import TransfermarktPlayersScraper
            players_scraper = TransfermarktPlayersScraper(season=self.season, delay=self.delay, verbose=False)
            players = players_scraper.scrape_team_players(team_id)
            player_ids = [p.player_id for p in players]
        
        all_valuations = {}
        
        for i, pid in enumerate(player_ids):
            self.log(f"  [{i+1}/{len(player_ids)}] Player {pid}")
            valuations = self.scrape_player_valuations(pid)
            all_valuations[pid] = valuations
        
        return all_valuations
    
    def scrape_league_valuations(self, league: str, max_players_per_team: int = None) -> Dict[str, Dict[str, List[Valuation]]]:
        """
        Scrape valuations for all players in a league.
        
        Args:
            league: League identifier
            max_players_per_team: Limit players per team (for testing)
        
        Returns:
            Dict mapping team_id -> player_id -> list of valuations
        """
        # First get teams and players
        from scraping.transfermarkt_players import TransfermarktPlayersScraper
        players_scraper = TransfermarktPlayersScraper(season=self.season, delay=self.delay, verbose=False)
        players_by_team = players_scraper.scrape_league_players(league)
        
        all_valuations = {}
        
        for team_id, players in players_by_team.items():
            self.log(f"\nTeam: {team_id}")
            
            player_ids = [p.player_id for p in players]
            if max_players_per_team:
                player_ids = player_ids[:max_players_per_team]
            
            team_valuations = {}
            for i, pid in enumerate(player_ids):
                self.log(f"  [{i+1}/{len(player_ids)}] Player {pid}")
                valuations = self.scrape_player_valuations(pid)
                team_valuations[pid] = valuations
            
            all_valuations[team_id] = team_valuations
        
        return all_valuations
    
    def run(self, leagues: List[str] = None) -> dict:
        """
        Run the scraper for specified leagues.
        
        Args:
            leagues: List of league identifiers. Defaults to top 5.
        
        Returns:
            Dict with all valuation data
        """
        if leagues is None:
            leagues = ["laliga", "premier", "bundesliga", "seriea", "ligue1"]
        
        all_data = {}
        
        for league in leagues:
            self.log(f"\n=== Scraping valuations from {league.upper()} ===")
            valuations_data = self.scrape_league_valuations(league)
            all_data[league] = valuations_data
            
            # Flatten for saving
            all_valuations = []
            for team_data in valuations_data.values():
                for player_valuations in team_data.values():
                    for v in player_valuations:
                        all_valuations.append(v.to_dict())
            
            self.save_json(all_valuations, f"valuations_{league}_{self.season}")
        
        # Save combined
        combined = []
        for league_data in all_data.values():
            for team_data in league_data.values():
                for player_valuations in team_data.values():
                    for v in player_valuations:
                        combined.append(v.to_dict())
        
        self.save_json(combined, f"valuations_all_{self.season}")
        
        return all_data


if __name__ == "__main__":
    scraper = TransfermarktValuationsScraper()
    scraper.run()
