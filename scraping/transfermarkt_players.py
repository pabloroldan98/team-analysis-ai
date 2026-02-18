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
    
    # Map detailed positions to normalized categories (GK, DEF, MID, ATT)
    POSITION_MAP = {
        # "goalkeeper": "Goalkeeper",
        # "sweeper": "Defender",
        # "centre-back": "Defender",
        # "left-back": "Defender",
        # "right-back": "Defender",
        # "defensive midfield": "Midfield",
        # "central midfield": "Midfield",
        # "right midfield": "Midfield",
        # "left midfield": "Midfield",
        # "attacking midfield": "Midfield",
        # "left winger": "Attack",
        # "right winger": "Attack",
        # "second striker": "Attack",
        # "centre-forward": "Attack",
        "goalkeeper": "GK",
        "sweeper": "DEF",
        "centre-back": "DEF",
        "left-back": "DEF",
        "right-back": "DEF",
        "defensive midfield": "MID",
        "central midfield": "MID",
        "right midfield": "MID",
        "left midfield": "MID",
        "attacking midfield": "MID",
        "left winger": "ATT",
        "right winger": "ATT",
        "second striker": "ATT",
        "centre-forward": "ATT",
    }
    
    @classmethod
    def _map_position(cls, detailed_position: str) -> str:
        """
        Map a detailed position to a normalized category.
        
        Args:
            detailed_position: Position like "Defensive Midfield", "Centre-Back", etc.
        
        Returns:
            Normalized position: "GK", "DEF", "MID", or "ATT"
        """
        if not detailed_position:
            return "N/A"
        
        pos_lower = detailed_position.strip().lower()
        
        # First try exact match
        if pos_lower in cls.POSITION_MAP:
            return cls.POSITION_MAP[pos_lower]
        
        # Then try keyword match
        if "goalkeeper" in pos_lower or "keeper" in pos_lower:
            return "GK"
        if "back" in pos_lower:
            return "DEF"
        if "midfield" in pos_lower:
            return "MID"
        if "forward" in pos_lower or "striker" in pos_lower:
            return "ATT"
        if "winger" in pos_lower or "wing" in pos_lower:
            return "ATT"
        
        return "N/A"
    
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
            
            # Position (from position column) - this is main_position, map to position
            main_position = ""
            pos_td = row.select_one("td.posrela table tr:last-child td")
            if pos_td:
                main_position = pos_td.text.strip()
            
            # Map to general position
            position = self._map_position(main_position)
            
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
            other_nationalities = []
            flags = row.select("td.zentriert img.flaggenrahmen")
            if len(flags) >= 1:
                nationality = flags[0].get("title", "")
            if len(flags) > 1:
                other_nationalities = [f.get("title", "") for f in flags[1:] if f.get("title")]
            
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
                main_position=main_position,
                age=age,
                birth_date=birth_date,
                nationality=nationality,
                other_nationalities=other_nationalities,
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
        Scrape detailed STATIC information for a single player.
        
        IMPORTANT: This only fetches static data that doesn't change over time:
        - height, preferred_foot, birth_date, other_positions, nationality
        
        It does NOT overwrite season-specific data from the team page:
        - market_value, age, team, team_id, joined_date
        
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
        
        # Name from header (only if not already set)
        if not player.name:
            header = soup.select_one("h1.data-header__headline-wrapper")
            if header:
                name_text = header.text.strip()
                # Remove shirt number if present
                name_text = re.sub(r"#\d+", "", name_text).strip()
                player.name = name_text
        
        # Profile image
        img = soup.select_one("img.data-header__profile-image")
        if img:
            player.img_url = img.get("src", "") or img.get("data-src", "")
        
        # NOTE: We do NOT scrape market_value from the player page
        # because it shows current value, not historical season value.
        # Market value comes from the team squad page for the specific season.
        
        # Parse info-table items - ONLY static data
        # Structure: sibling spans - info-table__content--regular (label) followed by --bold (value)
        info_table = soup.select_one("div.info-table")
        if info_table:
            labels = info_table.select("span.info-table__content--regular")
            for label_el in labels:
                # Get next sibling that is the bold value
                value_el = label_el.find_next_sibling("span", class_="info-table__content--bold")
                
                if not value_el:
                    continue
                
                label_text = label_el.get_text(strip=True).lower().rstrip(":")
                content_text = value_el.get_text(strip=True)
                
                # Date of birth (static) - but NOT age (age changes every year)
                if "date of birth" in label_text:
                    # Extract just the date part (before the age in parentheses)
                    date_match = re.match(r"([^(]+)", content_text)
                    if date_match:
                        player.birth_date = date_match.group(1).strip()
                    # NOTE: We do NOT update age here - age comes from team page for that season
                
                # Height: "1,88 m" or "1.88 m" (static)
                elif "height" in label_text:
                    # Extract meters like "1,88" or "1.88" and convert to cm
                    height_match = re.search(r"(\d)[,.](\d+)", content_text)
                    if height_match:
                        meters = int(height_match.group(1))
                        decimals = height_match.group(2)
                        player.height = meters * 100 + int(decimals[:2].ljust(2, '0'))
                
                # Foot: "right" or "left" (static)
                elif "foot" in label_text:
                    player.preferred_foot = content_text
                
                # NOTE: We skip "position" here - position comes from team page
                # NOTE: We skip "contract expires" - removed from model
                # NOTE: We skip "joined" - this is current club join date, not historical
        
        # Parse position details from detail-position__position elements
        # Each element may contain a title (detail-position__title) that we need to exclude
        other_positions = []
        
        # Find ALL detail-position__position elements
        pos_elements = soup.select("dd.detail-position__position, div.detail-position__position")
        
        for i, pos_el in enumerate(pos_elements):
            # Get the title element to exclude its text
            title_el = pos_el.select_one("dt.detail-position__title, div.detail-position__title, span.detail-position__title")
            
            if title_el:
                # Get all text and remove title text
                full_text = pos_el.get_text(strip=True)
                title_text = title_el.get_text(strip=True)
                pos_text = full_text.replace(title_text, "").strip()
            else:
                pos_text = pos_el.get_text(strip=True)
            
            # Clean up any remaining prefixes
            pos_text = re.sub(r"^(Main|Other)\s*position:?\s*", "", pos_text, flags=re.IGNORECASE).strip()
            
            if not pos_text:
                continue
            
            # First position element is main_position (only if not already set from team page)
            if i == 0 and not player.main_position:
                player.main_position = pos_text
            elif i > 0:
                # Other positions - might be concatenated, try to split
                known_positions = [
                    "Goalkeeper", "Sweeper", "Centre-Back", "Left-Back", "Right-Back",
                    "Defensive Midfield", "Central Midfield", "Right Midfield", "Left Midfield",
                    "Attacking Midfield", "Left Winger", "Right Winger", "Second Striker",
                    "Centre-Forward"
                ]
                
                # Check if it's a concatenated string (no spaces between positions)
                found_positions = []
                remaining = pos_text
                for kp in known_positions:
                    if kp in remaining:
                        found_positions.append(kp)
                        remaining = remaining.replace(kp, "")
                
                if found_positions:
                    other_positions.extend(found_positions)
                elif pos_text and pos_text != player.main_position:
                    other_positions.append(pos_text)
        
        # Remove duplicates while preserving order
        player.other_positions = list(dict.fromkeys(other_positions))
        
        # Map position from main_position if not set
        if (not player.position or player.position == "N/A") and player.main_position:
            player.position = self._map_position(player.main_position)
        
        # NOTE: We do NOT update team/team_id here - those come from the season's team page
        
        return player
    
    def scrape_league_players(
        self,
        league: str,
        include_details: bool = False,
        skip_player_ids: set = None,
    ) -> Dict[str, List[Player]]:
        """
        Scrape all players from a league.

        Phase 1 – Squad players:
          Get every team's current squad from the squad page.

        Phase 2 – Transferred players:
          Scrape the season transfer page of each team to discover players
          who moved in/out that season.  For any player NOT already covered
          in Phase 1, fetch their profile via scrape_player_details and add
          them to their respective team's list.

        Players are globally deduplicated so no player appears twice.

        Args:
            league: League identifier (e.g., "laliga", "premier")
            include_details: Whether to fetch detailed player info
            skip_player_ids: Player IDs to skip (already scraped).

        Returns:
            Dict mapping team_id -> list of players
        """
        team_infos = self.get_league_teams(league)

        if not team_infos:
            self.log(f"No teams found for league: {league}")
            return {}

        all_players: Dict[str, List[Player]] = {}
        global_seen: set = set(skip_player_ids) if skip_player_ids else set()

        # ── Phase 1: squad players ───────────────────────────────────────
        self.log(f"\n--- Phase 1: Squad players ({league.upper()}) ---")

        for i, info in enumerate(team_infos):
            self.log(f"  [{i+1}/{len(team_infos)}] {info['team_name']}")

            players = self.scrape_team_players(
                team_id=info["team_id"],
                team_name=info["team_name"],
                team_url=info["team_url"]
            )

            if include_details:
                for j, player in enumerate(players):
                    if player.player_id in global_seen:
                        self.log(f"    [{j+1}/{len(players)}] Details: {player.name} (already scraped, skipping)")
                        continue
                    self.log(f"    [{j+1}/{len(players)}] Details: {player.name}")
                    self.scrape_player_details(player.player_id, player)

            all_players[info["team_id"]] = players
            for p in players:
                global_seen.add(p.player_id)

        # ── Phase 2: transferred players from season transfer pages ──────
        self.log(f"\n--- Phase 2: Transferred players ({league.upper()}) ---")

        for i, info in enumerate(team_infos):
            tid = info["team_id"]
            tname = info["team_name"]
            self.log(f"\n[{i+1}/{len(team_infos)}] {tname} (transfer page)")

            page_players = self.get_transferred_player_ids(tid, tname)

            new_players = [(pid, pname) for pid, pname in page_players if pid not in global_seen]

            if not new_players:
                self.log(f"  No new players found on transfer page")
                continue

            self.log(f"  {len(new_players)} new player(s) from transfer page")

            if tid not in all_players:
                all_players[tid] = []

            for j, (pid, pname) in enumerate(new_players):
                global_seen.add(pid)
                self.log(f"  [{j+1}/{len(new_players)}] {pname or pid}")

                # Create a basic Player and fetch details
                player = Player(
                    player_id=pid,
                    name=pname,
                    team=tname,
                    team_id=tid,
                    season=self.season,
                )
                self.scrape_player_details(pid, player)
                all_players[tid].append(player)

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
        loaded_data: list = []

        # Load existing data for incremental scraping (all years for skip - player details are reusable)
        skip_player_ids: set = set()
        loaded_player_map: Dict[str, dict] = {}
        if self.use_downloaded_data:
            from scraping.utils.helpers import load_entity_all_from_all_years

            skip_player_ids, _, loaded_data = load_entity_all_from_all_years(
                entity="players",
                id_field="player_id",
                current_season=self.season,
            )
            for d in loaded_data:
                pid = d.get("player_id")
                if pid:
                    loaded_player_map[pid] = d
            self.log(
                f"\nIncremental mode: {len(skip_player_ids)} players from all years, "
                f"{len(loaded_data)} in current season"
            )
        
        for league in leagues:
            self.log(f"\n=== Scraping players from {league.upper()} ===")
            players_by_team = self.scrape_league_players(
                league, include_details, skip_player_ids=skip_player_ids,
            )
            all_data[league] = players_by_team
            
            # Flatten for saving – use loaded detailed data for skipped players
            all_players = []
            for team_id, players in players_by_team.items():
                for p in players:
                    # all_players.append(p.to_dict())
                    pd = p.to_dict()
                    pid = pd.get("player_id")
                    loaded = loaded_player_map.get(pid)
                    if loaded and pid in skip_player_ids:
                        all_players.append(loaded)
                    else:
                        all_players.append(pd)
                        if pid:
                            loaded_player_map[pid] = pd
            
            # Save per-league file
            self.save_json(all_players, f"players_{league}_{self.season}")

            # Update skip set so subsequent leagues benefit
            for p_dict in all_players:
                if "player_id" in p_dict:
                    skip_player_ids.add(p_dict["player_id"])
        
        # Save combined _all_ file (new + existing)
        combined = []
        for league_data in all_data.values():
            for players in league_data.values():
                combined.extend([p.to_dict() for p in players])
        combined.extend(loaded_data)
        self.save_json(combined, f"players_all_{self.season}")
        
        return all_data


if __name__ == "__main__":
    scraper = TransfermarktPlayersScraper()
    scraper.run()
