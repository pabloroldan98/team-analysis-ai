# scraping/transfermarkt_transfers.py
"""
Scraper for transfer data from Transfermarkt.
Scrapes transfers from season-specific team pages, with optional detailed
player history via Transfermarkt API for market_value_at_transfer.
"""
from __future__ import annotations

import re
import json
from typing import List, Optional, Dict, Set

from scraping.base_scraper import BaseScraper
from transfer import Transfer


class TransfermarktTransfersScraper(BaseScraper):
    """Scraper for transfer information from Transfermarkt."""
    
    # Transfermarkt API base URL for player transfer history
    TM_API_URL = "https://tmapi-alpha.transfermarkt.technology"
    
    # Cache for club names to avoid repeated API calls
    _club_name_cache: Dict[str, str] = {}
    
    def _fetch_club_names_batch(self, club_ids: Set[str]) -> Dict[str, str]:
        """
        Fetch multiple club names via API, adaptively splitting on 414 errors.
        API: https://tmapi-alpha.transfermarkt.technology/clubs?ids[]=X&ids[]=Y...
        
        Starts with all IDs in one request. If 414 (URL too long) is received,
        splits the batch in half and retries recursively.
        
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
        
        self.log(f"  Fetching {len(ids_to_fetch)} club names via API...")
        
        import requests
        
        def fetch_batch(batch: list) -> None:
            """Recursively fetch a batch, splitting on 414 errors."""
            if not batch:
                return
            
            # Build URL with query params
            params = "&".join([f"ids[]={cid}" for cid in batch])
            api_url = f"{self.TM_API_URL}/clubs?{params}"
            
            try:
                response = requests.get(api_url, timeout=60)
                
                # If URL too long, split in half and retry
                if response.status_code == 414:
                    if len(batch) <= 1:
                        self.log(f"    Cannot split further, skipping ID: {batch[0]}")
                        return
                    
                    mid = len(batch) // 2
                    self.log(f"    414 error with {len(batch)} IDs, splitting in half...")
                    fetch_batch(batch[:mid])
                    fetch_batch(batch[mid:])
                    return
                
                if response.status_code != 200:
                    self.log(f"    API error {response.status_code} for {len(batch)} IDs")
                    return
                
                data = response.json()
                
                if data.get("success"):
                    clubs_data = data.get("data", [])
                    for club in clubs_data:
                        club_id = str(club.get("id", ""))
                        club_name = club.get("name", "")
                        if club_id:
                            self._club_name_cache[club_id] = club_name
                    
                    self.log(f"    Fetched {len(clubs_data)} clubs (batch of {len(batch)})")
                
            except Exception as e:
                self.log(f"    Error fetching {len(batch)} clubs: {e}")
        
        # Start with all IDs
        fetch_batch(ids_to_fetch)
        
        self.log(f"    Total cached club names: {len(self._club_name_cache)}")
        
        return {cid: self._club_name_cache.get(cid, "") for cid in club_ids}
    
    def _fill_club_names(self, transfers: List[Transfer]) -> None:
        """
        Fill from_club_name and to_club_name for all transfers by fetching from API.
        
        Args:
            transfers: List of Transfer objects to update (modified in place)
        """
        # Collect unique club IDs that need names
        club_ids = set()
        for t in transfers:
            if t.from_club_id and not t.from_club_name:
                club_ids.add(t.from_club_id)
            if t.to_club_id and not t.to_club_name:
                club_ids.add(t.to_club_id)
        
        if not club_ids:
            return
        
        self.log(f"\nFetching names for {len(club_ids)} clubs...")
        
        # Fetch all club names in one call
        club_names = self._fetch_club_names_batch(club_ids)
        
        # Fill club names in transfers
        for t in transfers:
            if t.from_club_id and t.from_club_id in club_names and not t.from_club_name:
                t.from_club_name = club_names[t.from_club_id]
            if t.to_club_id and t.to_club_id in club_names and not t.to_club_name:
                t.to_club_name = club_names[t.to_club_id]
    
    def scrape_team_transfers(self, team_id: str, team_name: str = "", 
                               season: str = None) -> List[Transfer]:
        """
        Scrape transfers for a team in a specific season from the season page.
        URL: /team-name/transfers/verein/{team_id}/saison_id/{season_year}
        
        Args:
            team_id: Transfermarkt team ID (e.g., "418" for Real Madrid)
            team_name: Team name for reference
            season: Season string (e.g., "2024-2025"). Defaults to scraper's season.
        
        Returns:
            List of Transfer objects
        """
        season = season or self.season
        season_year = season.split("-")[0] if season else ""
        
        url = f"{self.BASE_URL}/-/transfers/verein/{team_id}/saison_id/{season_year}"
        
        self.log(f"Scraping transfers: {team_name or team_id} ({season})")
        soup = self.fetch_page(url)
        
        if not soup:
            return []
        
        # Get team name from page if not provided
        if not team_name:
            header = soup.select_one("header.data-header h1")
            team_name = header.text.strip() if header else f"Team {team_id}"
        
        transfers = []
        seen_transfers: Set[str] = set()
        
        # Find the transfer sections: "Arrivals" and "Departures"
        # The page typically has two main sections with responsive-table
        for box in soup.select("div.box"):
            header = box.select_one("h2")
            if not header:
                continue
            
            header_text = header.text.strip().lower()
            
            # Determine transfer type from header
            if "arrival" in header_text or "llegada" in header_text or "zugänge" in header_text:
                transfer_type = "in"
            elif "departure" in header_text or "salida" in header_text or "abgänge" in header_text:
                transfer_type = "out"
            else:
                continue
            
            # Find the table in this box
            table = box.select_one("table.items")
            if not table:
                continue
            
            tbody = table.select_one("tbody")
            if not tbody:
                continue
            
            for row in tbody.select("tr.odd, tr.even"):
                transfer = self._parse_transfer_row(
                    row, team_id, team_name, transfer_type, season
                )
                
                if transfer:
                    transfer_key = self._get_transfer_key(transfer)
                    if transfer_key not in seen_transfers:
                        seen_transfers.add(transfer_key)
                        transfers.append(transfer)
        
        self.log(f"  Found {len(transfers)} transfers")
        return transfers
    
    def _parse_transfer_row(self, row, team_id: str, team_name: str,
                            transfer_type: str, season: str) -> Optional[Transfer]:
        """
        Parse a transfer row from the season transfers page.
        
        Table structure typically:
        | Photo | Player Name + Position | Age | Nationality | Club (from/to) | Fee |
        """
        try:
            cells = row.select("td")
            if len(cells) < 4:
                return None
            
            # Player info - find link to player profile
            player_link = row.select_one("a[href*='/profil/spieler/'], a[href*='/spieler/']")
            if not player_link:
                return None
            
            player_href = player_link.get("href", "")
            player_id = self.extract_player_id(player_href)
            player_name_text = player_link.get("title", "") or player_link.text.strip()
            
            if not player_id:
                return None
            
            # Other club info
            other_club_name = ""
            other_club_id = ""
            
            # Find club links - usually with verein in href
            club_links = row.select("a[href*='/verein/']")
            for link in club_links:
                href = link.get("href", "")
                # Extract club ID and name
                club_id_match = re.search(r'/verein/(\d+)', href)
                if club_id_match:
                    # Get club name from title, text, or img alt
                    club_name = link.get("title", "") or link.text.strip()
                    if not club_name:
                        img = link.select_one("img")
                        if img:
                            club_name = img.get("alt", "")
                    
                    if club_name:
                        other_club_name = club_name
                        other_club_id = club_id_match.group(1)
                        break
            
            # Handle special cases (Retired, Without Club, Unknown)
            if not other_club_name:
                # Look for special icons/text
                for cell in cells:
                    cell_text = cell.get_text(strip=True)
                    if cell_text in ["Retired", "Without Club", "Unknown", "-", "?"]:
                        other_club_name = cell_text
                        break
                    # Check for images with alt text
                    for img in cell.select("img"):
                        alt = img.get("alt", "")
                        if alt in ["Retired", "Without Club"]:
                            other_club_name = alt
                            break
            
            # Determine from/to based on transfer type
            if transfer_type == "in":
                from_club_name = other_club_name
                from_club_id = other_club_id
                to_club_name = team_name
                to_club_id = team_id
            else:  # "out"
                from_club_name = team_name
                from_club_id = team_id
                to_club_name = other_club_name
                to_club_id = other_club_id
            
            # Parse transfer fee/price
            price_info = self._parse_price(row)
            price = price_info["price"]
            price_str = price_info["price_str"]
            is_loan = price_info["is_loan"]
            transfer_date = price_info.get("date", "")
            
            # Update transfer_type based on loan status
            if is_loan:
                transfer_type = f"loan_{transfer_type}"
            
            # Generate unique ID
            transfer_id = self.generate_id(
                player_id, from_club_id or "unknown", to_club_id or "unknown", season
            )
            
            return Transfer(
                transfer_id=transfer_id,
                player_id=player_id,
                player_name=player_name_text,
                from_club_name=from_club_name,
                from_club_id=from_club_id,
                to_club_name=to_club_name,
                to_club_id=to_club_id,
                price=price,
                price_str=price_str,
                transfer_date=transfer_date,
                transfer_type=transfer_type,
                is_loan=is_loan,
                market_value_at_transfer=None,  # Only available from API/player page
                season=season,
            )
        except Exception as e:
            self.log(f"  Error parsing transfer row: {e}")
            return None
    
    def _parse_price(self, row) -> Dict:
        """
        Parse transfer price from a row, handling various formats:
        - "€47.50m" -> price: 47500000
        - "free transfer" -> price: 0
        - "loan transfer" / "Loan" -> price: None, is_loan: True
        - "Loan fee: €1.00m" -> price: 1000000, is_loan: True
        - "End of loan" -> price: None, is_loan: True
        - "-" or "?" -> price: None, price_str: "Unknown"
        
        Returns:
            Dict with keys: price, price_str, is_loan, date
        """
        result = {
            "price": None,
            "price_str": "Unknown",
            "is_loan": False,
            "date": ""
        }
        
        # Find the fee cell - usually last cell or one with "rechts" class
        fee_cell = row.select_one("td.rechts")
        if not fee_cell:
            cells = row.select("td")
            if cells:
                fee_cell = cells[-1]
        
        if not fee_cell:
            return result
        
        # Get the text content
        fee_text = ""
        fee_link = fee_cell.select_one("a")
        if fee_link:
            fee_text = fee_link.text.strip()
        else:
            fee_text = fee_cell.get_text(strip=True)
        
        fee_lower = fee_text.lower()
        result["price_str"] = fee_text
        
        # Check for loan types
        if "loan" in fee_lower or "leih" in fee_lower or "préstamo" in fee_lower:
            result["is_loan"] = True
            
            # Check for loan fee amount
            # "Loan fee: €1.00m" or "Loan €500k"
            loan_value = self.parse_market_value(fee_text)
            if loan_value and loan_value > 0:
                result["price"] = loan_value
            else:
                result["price"] = None
            
            # Extract date if present (e.g., "End of loan 30/06/2025")
            date_match = re.search(r'(\d{2}/\d{2}/\d{4})', fee_text)
            if date_match:
                result["date"] = date_match.group(1)
            
            return result
        
        # Check for free transfer
        if "free" in fee_lower or "ablösefrei" in fee_lower or "libre" in fee_lower:
            result["price"] = 0
            result["price_str"] = "Free transfer"
            return result
        
        # Check for unknown/missing
        if fee_text in ["-", "?", "", "N/A"]:
            result["price"] = None
            result["price_str"] = "Unknown"
            return result
        
        # Parse monetary value
        parsed_value = self.parse_market_value(fee_text)
        if parsed_value is not None:
            result["price"] = parsed_value
            result["price_str"] = fee_text
        
        return result
    
    def scrape_player_all_transfers(self, player_id: str, player_name: str = "") -> List[Transfer]:
        """
        Get ALL historical transfers for a player using Transfermarkt API.
        API: https://tmapi-alpha.transfermarkt.technology/transfer/history/player/{player_id}
        
        This method provides market_value_at_transfer for each transfer.
        
        Args:
            player_id: Transfermarkt player ID
            player_name: Player name for reference
        
        Returns:
            List of Transfer objects with market_value_at_transfer populated
        """
        api_url = f"{self.TM_API_URL}/transfer/history/player/{player_id}"
        
        self.log(f"  Fetching player transfers via API: {player_name or player_id}")
        
        try:
            # Use requests directly for the API (JSON response)
            import requests
            response = requests.get(api_url, timeout=30)
            
            if response.status_code != 200:
                self.log(f"    API error: {response.status_code}")
                return []
            
            data = response.json()
            
            if not data.get("success"):
                self.log(f"    API returned error: {data.get('message')}")
                return []
            
            history = data.get("data", {}).get("history", {})
            terminated = history.get("terminated", [])
            
            transfers = []
            
            for item in terminated:
                transfer = self._parse_api_transfer(item, player_id, player_name)
                if transfer:
                    transfers.append(transfer)
            
            self.log(f"    Found {len(transfers)} transfers")
            return transfers
            
        except Exception as e:
            self.log(f"    Error fetching from API: {e}")
            return []
    
    def _parse_api_transfer(self, item: dict, player_id: str, player_name: str) -> Optional[Transfer]:
        """
        Parse a transfer from the Transfermarkt API response.
        
        API structure:
        {
            "id": "5802198",
            "transferSource": {"clubId": "418", ...},
            "transferDestination": {"clubId": "1531", ...},
            "details": {
                "date": "2025-07-22T00:00:00+02:00",
                "seasonId": 2025,
                "marketValue": {"value": 2500000, ...},
                "fee": {"value": 2000000, "compact": {"content": "2.00", "suffix": "M"}}
            },
            "typeDetails": {"type": "STANDARD|ACTIVE_LOAN_TRANSFER|...", "feeDescription": "..."}
        }
        """
        try:
            transfer_id = item.get("id", "")
            
            # Source and destination clubs
            source = item.get("transferSource", {})
            dest = item.get("transferDestination", {})
            
            from_club_id = str(source.get("clubId", ""))
            to_club_id = str(dest.get("clubId", ""))
            
            # Details
            details = item.get("details", {})
            
            # Date - parse from ISO format
            date_str = details.get("date", "")
            transfer_date = ""
            if date_str:
                # Convert "2025-07-22T00:00:00+02:00" to "22/07/2025"
                date_match = re.match(r'(\d{4})-(\d{2})-(\d{2})', date_str)
                if date_match:
                    transfer_date = f"{date_match.group(3)}/{date_match.group(2)}/{date_match.group(1)}"
            
            # Season
            season_id = details.get("seasonId")
            season = f"{season_id}-{season_id + 1}" if season_id else ""
            
            # Market value at transfer
            mv_data = details.get("marketValue", {})
            market_value_at_transfer = mv_data.get("value")
            
            # Price/Fee
            fee_data = details.get("fee", {})
            price = fee_data.get("value")
            
            # Build price_str from compact format
            compact = fee_data.get("compact", {})
            price_str = f"{compact.get('prefix', '')}{compact.get('content', '')}{compact.get('suffix', '')}"
            if not price_str or price_str == "-":
                price_str = "Unknown"
            
            # Type details (loan, standard, etc.)
            type_details = item.get("typeDetails", {})
            transfer_type_raw = type_details.get("type", "STANDARD")
            fee_description = type_details.get("feeDescription", "")
            
            # Determine is_loan and transfer_type
            is_loan = "LOAN" in transfer_type_raw.upper()
            
            if is_loan:
                transfer_type = "loan_out"
            elif transfer_type_raw == "RETURNED_FROM_PREVIOUS_LOAN":
                is_loan = True
                transfer_type = "loan_return"
            else:
                transfer_type = "out"
            
            # Use fee description as price_str if available
            if fee_description and fee_description not in ["", "-"]:
                price_str = fee_description
            
            # Handle free transfers
            if price_str.lower() in ["free transfer", "ablösefrei"]:
                price = 0
            
            return Transfer(
                transfer_id=transfer_id,
                player_id=player_id,
                player_name=player_name,
                from_club_name="",  # API doesn't return club names, only IDs
                from_club_id=from_club_id,
                to_club_name="",
                to_club_id=to_club_id,
                price=price,
                price_str=price_str,
                transfer_date=transfer_date,
                transfer_type=transfer_type,
                is_loan=is_loan,
                market_value_at_transfer=market_value_at_transfer,
                season=season,
            )
            
        except Exception as e:
            self.log(f"    Error parsing API transfer: {e}")
            return None
    
    def _get_transfer_key(self, transfer: Transfer) -> str:
        """Generate a unique key for deduplication."""
        return f"{transfer.player_id}_{transfer.from_club_id}_{transfer.to_club_id}_{transfer.season}"
    
    def scrape_league_transfers(self, league: str, details: bool = True) -> Dict[str, List[Transfer]]:
        """
        Scrape transfers for all teams in a league.
        
        Args:
            league: League identifier (e.g., "laliga", "premier")
            details: If True, fetch full transfer history per player (slower but includes
                     market_value_at_transfer). If False, only current season team transfers.
        
        Returns:
            Dict mapping team_id -> list of transfers
        """
        team_infos = self.get_league_teams(league)
        
        if not team_infos:
            self.log(f"No teams found for league: {league}")
            return {}
        
        all_transfers = {}
        
        for i, info in enumerate(team_infos):
            self.log(f"[{i+1}/{len(team_infos)}] {info['team_name']}")
            
            if details:
                # Get basic team transfers first
                team_transfers = self.scrape_team_transfers(
                    team_id=info["team_id"],
                    team_name=info["team_name"]
                )
                
                # Then for each player, get their full history with market values via API
                player_ids_seen = set()
                detailed_transfers = []
                
                for t in team_transfers:
                    if t.player_id not in player_ids_seen:
                        player_ids_seen.add(t.player_id)
                        player_transfers = self.scrape_player_all_transfers(
                            player_id=t.player_id,
                            player_name=t.player_name
                        )
                        detailed_transfers.extend(player_transfers)
                
                all_transfers[info["team_id"]] = detailed_transfers
            else:
                # Just get current season transfers
                transfers = self.scrape_team_transfers(
                    team_id=info["team_id"],
                    team_name=info["team_name"]
                )
                all_transfers[info["team_id"]] = transfers
        
        return all_transfers
    
    def run(self, leagues: List[str] = None, details: bool = True) -> dict:
        """
        Run the scraper for specified leagues.
        
        Args:
            leagues: List of league identifiers. Defaults to top 5.
            details: If True, fetch detailed player transfer history (slower).
        
        Returns:
            Dict with league -> team_id -> list of transfers
        """
        if leagues is None:
            leagues = ["laliga", "premier", "bundesliga", "seriea", "ligue1"]
        
        all_data = {}
        
        for league in leagues:
            self.log(f"\n=== Scraping transfers from {league.upper()} ===")
            transfers_by_team = self.scrape_league_transfers(league, details=details)
            all_data[league] = transfers_by_team
            
            # Collect all transfers for this league
            all_transfers = []
            for team_id, transfers in transfers_by_team.items():
                all_transfers.extend(transfers)
            
            # Fill club names from API (for transfers from player history API) - single batch call
            if details:
                self._fill_club_names(all_transfers)
            
            # Save per-league file
            transfers_dicts = [t.to_dict() for t in all_transfers]
            self.save_json(transfers_dicts, f"transfers_{league}_{self.season}")
        
        # Save combined _all_ file
        combined = []
        for league_data in all_data.values():
            for transfers in league_data.values():
                combined.extend([t.to_dict() for t in transfers])
        self.save_json(combined, f"transfers_all_{self.season}")
        
        return all_data


if __name__ == "__main__":
    scraper = TransfermarktTransfersScraper()
    scraper.run()
