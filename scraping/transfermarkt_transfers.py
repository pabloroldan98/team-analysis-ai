# scraping/transfermarkt_transfers.py
"""
Scraper for transfer data from Transfermarkt.
"""
from __future__ import annotations

import re
from typing import List, Optional, Dict
from dataclasses import dataclass

from scraping.base_scraper import BaseScraper


@dataclass
class Transfer:
    """Represents a player transfer."""
    transfer_id: str
    player_id: str
    player_name: str
    from_club: str
    from_club_id: str
    to_club: str
    to_club_id: str
    transfer_fee: Optional[float]
    transfer_fee_str: str
    transfer_date: str
    transfer_type: str  # "in" or "out"
    is_loan: bool
    season: str
    
    def to_dict(self) -> dict:
        return {
            "transfer_id": self.transfer_id,
            "player_id": self.player_id,
            "player_name": self.player_name,
            "from_club": self.from_club,
            "from_club_id": self.from_club_id,
            "to_club": self.to_club,
            "to_club_id": self.to_club_id,
            "transfer_fee": self.transfer_fee,
            "transfer_fee_str": self.transfer_fee_str,
            "transfer_date": self.transfer_date,
            "transfer_type": self.transfer_type,
            "is_loan": self.is_loan,
            "season": self.season,
        }


class TransfermarktTransfersScraper(BaseScraper):
    """Scraper for transfer information from Transfermarkt."""
    
    def scrape_team_transfers(self, team_id: str, team_name: str = "") -> List[Transfer]:
        """
        Scrape all transfers for a team in the current season.
        
        Args:
            team_id: Transfermarkt team ID
            team_name: Team name for reference
        
        Returns:
            List of Transfer objects
        """
        url = f"{self.BASE_URL}/-/transfers/verein/{team_id}/saison_id/{self.season_year}"
        
        self.log(f"Scraping transfers: {team_name or team_id}")
        soup = self.fetch_page(url)
        
        if not soup:
            return []
        
        # Get team name if not provided
        if not team_name:
            header = soup.select_one("header.data-header h1")
            team_name = header.text.strip() if header else ""
        
        transfers = []
        
        # Find transfer tables (arrivals and departures)
        for box in soup.select("div.box"):
            header = box.select_one("h2")
            if not header:
                continue
            
            header_text = header.text.strip().lower()
            
            # Determine transfer type
            if "arrival" in header_text or "llegada" in header_text or "zugänge" in header_text:
                transfer_type = "in"
            elif "departure" in header_text or "salida" in header_text or "abgänge" in header_text:
                transfer_type = "out"
            else:
                continue
            
            # Parse transfer rows
            for row in box.select("table.items tbody tr"):
                transfer = self._parse_transfer_row(row, team_id, team_name, transfer_type)
                if transfer:
                    transfers.append(transfer)
        
        self.log(f"  Found {len(transfers)} transfers")
        return transfers
    
    def _parse_transfer_row(self, row, team_id: str, team_name: str, transfer_type: str) -> Optional[Transfer]:
        """Parse a transfer row from the transfers table."""
        try:
            # Player info
            player_link = row.select_one("td.hauptlink a[href*='/spieler/']")
            if not player_link:
                return None
            
            player_id = self.extract_player_id(player_link.get("href", ""))
            player_name = player_link.text.strip()
            
            if not player_id:
                return None
            
            # Other club involved
            other_club_link = row.select_one("td.no-border-links a[href*='/verein/']")
            other_club = other_club_link.text.strip() if other_club_link else "Unknown"
            other_club_id = self.extract_team_id(other_club_link.get("href", "")) if other_club_link else ""
            
            # Determine from/to
            if transfer_type == "in":
                from_club = other_club
                from_club_id = other_club_id
                to_club = team_name
                to_club_id = team_id
            else:
                from_club = team_name
                from_club_id = team_id
                to_club = other_club
                to_club_id = other_club_id
            
            # Transfer fee
            fee_td = row.select_one("td.rechts a, td.rechts.hauptlink")
            transfer_fee_str = fee_td.text.strip() if fee_td else ""
            transfer_fee = self.parse_market_value(transfer_fee_str)
            
            # Check if loan
            is_loan = "loan" in transfer_fee_str.lower() or "préstamo" in transfer_fee_str.lower() or "leih" in transfer_fee_str.lower()
            
            # Transfer date (often not available in basic table)
            transfer_date = ""
            
            # Generate unique ID
            transfer_id = self.generate_id(player_id, from_club_id, to_club_id, self.season)
            
            return Transfer(
                transfer_id=transfer_id,
                player_id=player_id,
                player_name=player_name,
                from_club=from_club,
                from_club_id=from_club_id,
                to_club=to_club,
                to_club_id=to_club_id,
                transfer_fee=transfer_fee,
                transfer_fee_str=transfer_fee_str,
                transfer_date=transfer_date,
                transfer_type=transfer_type,
                is_loan=is_loan,
                season=self.season,
            )
        except Exception as e:
            self.log(f"  Error parsing transfer row: {e}")
            return None
    
    def scrape_league_transfers(self, league: str) -> Dict[str, List[Transfer]]:
        """
        Scrape all transfers from a league.
        
        Args:
            league: League identifier (e.g., "laliga", "premier")
        
        Returns:
            Dict mapping team_id -> list of transfers
        """
        team_infos = self.get_league_teams(league)
        
        if not team_infos:
            self.log(f"No teams found for league: {league}")
            return {}
        
        all_transfers = {}
        
        for i, info in enumerate(team_infos):
            self.log(f"  [{i+1}/{len(team_infos)}] {info['team_name']}")
            
            transfers = self.scrape_team_transfers(
                team_id=info["team_id"],
                team_name=info["team_name"]
            )
            
            all_transfers[info["team_id"]] = transfers
        
        return all_transfers
    
    def run(self, leagues: List[str] = None) -> dict:
        """
        Run the scraper for specified leagues.
        
        Args:
            leagues: List of league identifiers. Defaults to top 5.
        
        Returns:
            Dict with league -> team_id -> list of transfers
        """
        if leagues is None:
            leagues = ["laliga", "premier", "bundesliga", "seriea", "ligue1"]
        
        all_data = {}
        
        for league in leagues:
            self.log(f"\n=== Scraping transfers from {league.upper()} ===")
            transfers_by_team = self.scrape_league_transfers(league)
            all_data[league] = transfers_by_team
            
            # Flatten for saving
            all_transfers = []
            for team_id, transfers in transfers_by_team.items():
                for t in transfers:
                    all_transfers.append(t.to_dict())
            
            self.save_json(all_transfers, f"transfers_{league}_{self.season}")
        
        # Save combined
        combined = []
        for league_data in all_data.values():
            for transfers in league_data.values():
                for t in transfers:
                    combined.append(t.to_dict())
        
        self.save_json(combined, f"transfers_all_{self.season}")
        
        return all_data


if __name__ == "__main__":
    scraper = TransfermarktTransfersScraper()
    scraper.run()
