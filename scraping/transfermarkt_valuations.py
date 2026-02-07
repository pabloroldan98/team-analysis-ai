# scraping/transfermarkt_valuations.py
"""
Scraper for player valuation history from Transfermarkt.

By default (--details), fetches the FULL valuation history for each player
via Transfermarkt API.

With --no-details, only gets the current market value from player profiles
(much faster but no historical data).
"""
from __future__ import annotations

import re
from typing import List, Optional, Dict, Set

from scraping.base_scraper import BaseScraper
from valuation import Valuation


class TransfermarktValuationsScraper(BaseScraper):
    """Scraper for player valuation history from Transfermarkt."""
    
    # Transfermarkt API base URL
    TM_API_URL = "https://tmapi-alpha.transfermarkt.technology"
    
    # Cache for club names to avoid repeated API calls
    _club_name_cache: Dict[str, str] = {}
    
    def _fetch_club_names_batch(self, club_ids: Set[str]) -> Dict[str, str]:
        """
        Fetch multiple club names in a single API call.
        API: https://tmapi-alpha.transfermarkt.technology/clubs?ids[]=X&ids[]=Y...
        
        Args:
            club_ids: Set of club IDs to fetch
        
        Returns:
            Dict mapping club_id -> club_name
        """
        if not club_ids:
            return {}
        
        # Filter out already cached IDs
        ids_to_fetch = [cid for cid in club_ids if cid and cid not in self._club_name_cache]
        
        if not ids_to_fetch:
            return {cid: self._club_name_cache.get(cid, "") for cid in club_ids}
        
        # Build URL with query params
        params = "&".join([f"ids[]={cid}" for cid in ids_to_fetch])
        api_url = f"{self.TM_API_URL}/clubs?{params}"
        
        self.log(f"  Fetching {len(ids_to_fetch)} club names via API...")
        
        try:
            import requests
            response = requests.get(api_url, timeout=60)
            
            if response.status_code != 200:
                self.log(f"    API error: {response.status_code}")
                return {cid: self._club_name_cache.get(cid, "") for cid in club_ids}
            
            data = response.json()
            
            if data.get("success"):
                clubs_data = data.get("data", [])
                for club in clubs_data:
                    club_id = str(club.get("id", ""))
                    club_name = club.get("name", "")
                    if club_id:
                        self._club_name_cache[club_id] = club_name
            
            self.log(f"    Found {len(self._club_name_cache)} club names")
            
        except Exception as e:
            self.log(f"    Error fetching club names: {e}")
        
        return {cid: self._club_name_cache.get(cid, "") for cid in club_ids}
    
    def _fill_club_names(self, valuations: List[Valuation]) -> None:
        """
        Fill club_name_at_valuation for all valuations by fetching club names from API.
        
        Args:
            valuations: List of Valuation objects to update (modified in place)
        """
        # Collect unique club IDs that need names
        club_ids = set()
        for v in valuations:
            if v.club_id_at_valuation and not v.club_name_at_valuation:
                club_ids.add(v.club_id_at_valuation)
        
        if not club_ids:
            return
        
        self.log(f"\nFetching names for {len(club_ids)} clubs...")
        
        # Fetch all club names in one call
        club_names = self._fetch_club_names_batch(club_ids)
        
        # Fill club names in valuations
        for v in valuations:
            if v.club_id_at_valuation and v.club_id_at_valuation in club_names:
                v.club_name_at_valuation = club_names[v.club_id_at_valuation]
    
    def scrape_player_valuations(self, player_id: str, player_name: str = "") -> List[Valuation]:
        """
        Get FULL valuation history for a player using Transfermarkt API.
        API: https://tmapi-alpha.transfermarkt.technology/player/{player_id}/market-value-history
        
        Args:
            player_id: Transfermarkt player ID
            player_name: Player name for reference
        
        Returns:
            List of Valuation objects (all historical valuations)
        """
        api_url = f"{self.TM_API_URL}/player/{player_id}/market-value-history"
        
        self.log(f"  Fetching valuations via API: {player_name or player_id}")
        
        try:
            import requests
            response = requests.get(api_url, timeout=30)
            
            if response.status_code != 200:
                self.log(f"    API error: {response.status_code}")
                return []
            
            data = response.json()
            
            if not data.get("success"):
                self.log(f"    API returned error: {data.get('message')}")
                return []
            
            # Parse the history data
            history = data.get("data", {}).get("history", [])
            
            valuations = []
            for item in history:
                valuation = self._parse_api_valuation(item, player_id, player_name)
                if valuation:
                    valuations.append(valuation)
            
            self.log(f"    Found {len(valuations)} valuations")
            return valuations
            
        except Exception as e:
            self.log(f"    Error fetching from API: {e}")
            return []
    
    def _parse_api_valuation(self, item: dict, player_id: str, player_name: str) -> Optional[Valuation]:
        """
        Parse a valuation from the Transfermarkt API response.
        
        API structure:
        {
            "playerId": "948275",
            "clubId": "6767",
            "age": 17,
            "marketValue": {
                "value": 200000,
                "currency": "EUR",
                "compact": {"prefix": "€", "content": "200.00", "suffix": "K"},
                "determined": "2022-03-21"
            }
        }
        """
        try:
            market_value_data = item.get("marketValue", {})
            
            # Value
            valuation_amount = market_value_data.get("value")
            if valuation_amount is None:
                return None
            
            # Date - from marketValue.determined (format: "2022-03-21")
            date_str = market_value_data.get("determined", "")
            valuation_date = ""
            if date_str:
                date_match = re.match(r'(\d{4})-(\d{2})-(\d{2})', date_str)
                if date_match:
                    valuation_date = f"{date_match.group(3)}/{date_match.group(2)}/{date_match.group(1)}"
                else:
                    valuation_date = date_str
            
            # Club ID (club name will be filled later)
            club_id_at_valuation = str(item.get("clubId", ""))
            
            # Age
            age_at_valuation = item.get("age")
            
            # Generate unique ID
            valuation_id = self.generate_id(player_id, valuation_date, str(valuation_amount))
            
            return Valuation(
                valuation_id=valuation_id,
                player_id=player_id,
                player_name=player_name,
                valuation_amount=valuation_amount,
                valuation_date=valuation_date,
                club_name_at_valuation="",  # Will be filled later by _fill_club_names
                club_id_at_valuation=club_id_at_valuation,
                age_at_valuation=age_at_valuation,
            )
            
        except Exception as e:
            self.log(f"    Error parsing API valuation: {e}")
            return None
    
    def scrape_team_valuations(self, team_id: str, details: bool = True, 
                               player_ids: List = None) -> Dict[str, List[Valuation]]:
        """
        Scrape valuations for all players in a team.
        
        Args:
            team_id: Transfermarkt team ID
            details: If True, get full valuation history per player. 
                     If False, only current market value.
            player_ids: Optional list of player IDs or tuples (will fetch from team if not provided)
        
        Returns:
            Dict mapping player_id -> list of valuations
        """
        # If no player IDs provided, fetch them from team
        if player_ids is None:
            from scraping.transfermarkt_players import TransfermarktPlayersScraper
            players_scraper = TransfermarktPlayersScraper(season=self.season, delay=self.delay, verbose=False)
            players = players_scraper.scrape_team_players(team_id)
            player_ids = [(p.player_id, p.name, p.market_value, p.team) for p in players]
        else:
            # Convert simple IDs to tuples with placeholder info if needed
            player_ids = [
                (pid, "", None, "") if not isinstance(pid, tuple) else pid 
                for pid in player_ids
            ]
        
        all_valuations = {}
        
        for i, player_info in enumerate(player_ids):
            if isinstance(player_info, tuple):
                pid, pname, current_value, club = player_info
            else:
                pid = player_info
                pname = ""
                current_value = None
                club = ""
            
            self.log(f"  [{i+1}/{len(player_ids)}] Player {pname or pid}")
            
            if details:
                # Get full history via API
                valuations = self.scrape_player_valuations(pid, pname)
            else:
                # Only current value (create single Valuation from player data)
                if current_value:
                    valuation_id = self.generate_id(pid, self.season, str(current_value))
                    valuations = [Valuation(
                        valuation_id=valuation_id,
                        player_id=pid,
                        player_name=pname,
                        valuation_amount=current_value,
                        valuation_date=self.season,
                        club_name_at_valuation=club,
                    )]
                else:
                    valuations = []
            
            all_valuations[pid] = valuations
        
        return all_valuations
    
    def scrape_league_valuations(self, league: str, details: bool = True) -> Dict[str, Dict[str, List[Valuation]]]:
        """
        Scrape valuations for all players in a league.
        
        Args:
            league: League identifier
            details: If True, get full valuation history per player (slower).
                     If False, only current market values (faster).
        
        Returns:
            Dict mapping team_id -> player_id -> list of valuations
        """
        # First get teams and players
        from scraping.transfermarkt_players import TransfermarktPlayersScraper
        players_scraper = TransfermarktPlayersScraper(season=self.season, delay=self.delay, verbose=False)
        players_by_team = players_scraper.scrape_league_players(league)
        
        all_valuations = {}
        
        for team_id, players in players_by_team.items():
            team_name = players[0].team if players else team_id
            self.log(f"\nTeam: {team_name}")
            
            # Prepare player info with current values
            player_info = [(p.player_id, p.name, p.market_value, p.team) for p in players]
            
            team_valuations = self.scrape_team_valuations(
                team_id=team_id,
                details=details,
                player_ids=player_info
            )
            
            all_valuations[team_id] = team_valuations
        
        return all_valuations
    
    def run(self, leagues: List[str] = None, details: bool = True) -> dict:
        """
        Run the scraper for specified leagues.
        
        Args:
            leagues: List of league identifiers. Defaults to top 5.
            details: If True, get full valuation history (slower).
        
        Returns:
            Dict with all valuation data
        """
        if leagues is None:
            leagues = ["laliga", "premier", "bundesliga", "seriea", "ligue1"]
        
        all_data = {}
        
        for league in leagues:
            self.log(f"\n=== Scraping valuations from {league.upper()} ===")
            valuations_data = self.scrape_league_valuations(league, details=details)
            all_data[league] = valuations_data
            
            # Collect all valuations for this league
            all_valuations = []
            for team_data in valuations_data.values():
                for player_valuations in team_data.values():
                    all_valuations.extend(player_valuations)
            
            # Fill club names from API (single batch call)
            if details:
                self._fill_club_names(all_valuations)
            
            # Save to JSON
            valuations_dicts = [v.to_dict() for v in all_valuations]
            self.save_json(valuations_dicts, f"valuations_{league}_{self.season}")
        
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
