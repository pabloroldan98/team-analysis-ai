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
    
    # LEAGUE_INFO is inherited from BaseScraper
    
    def scrape_team(
        self,
        team_id: str,
        team_url: str = None,
        league_key: str = "",
        league_name: str = "",
        league_id: str = "",
        country: str = "",
    ) -> Optional[Team]:
        """
        Scrape detailed information for a single team.
        
        Args:
            team_id: Transfermarkt team ID
            team_url: Optional team URL (will be constructed if not provided)
            league_key: League identifier for context
            league_name: League name (passed from league scrape)
            league_id: League ID (passed from league scrape)
            country: Country name (passed from league scrape)
        
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

        # Get squad size: count tr in tbody of the detailed squad table (responsive-table).
        # Prefer the table with thead containing "Market value" / "Age" (detailed view).
        # Fallback: first responsive-table; if count seems wrong, use total_mv / avg_mv.
        squad_size = None
        for table in soup.select("div.responsive-table table"):
            thead = table.find("thead")
            if thead:
                header_text = thead.get_text(separator=" ", strip=True).lower()
                # Detailed squad table has "market value" and "age" in header
                if "market value" in header_text or ("age" in header_text and "player" in header_text):
                    tbody_rows = table.select("tbody tr")
                    if tbody_rows:
                        squad_size = len(tbody_rows)
                        break
        if squad_size is None:
            first_responsive = soup.select_one("div.responsive-table")
            if first_responsive:
                tbody_rows = first_responsive.select("table tbody tr")
                squad_size = len(tbody_rows) if tbody_rows else None

        # Get total_market_value, average_market_value, average_age from tfoot (Squad details by position)
        total_market_value = None
        average_market_value = None
        average_age = None

        def _parse_total_row(cells):
            """Parse Total row: Position, ø-Age, Market value, ø-Market value."""
            nonlocal average_age, total_market_value, average_market_value
            if len(cells) >= 4:
                first_text = cells[0].get_text(strip=True).lower()
                if "total" in first_text:
                    try:
                        average_age = float(cells[1].get_text(strip=True).replace(",", "."))
                    except (ValueError, IndexError):
                        pass
                    total_market_value = self.parse_market_value(cells[2].get_text(strip=True))
                    average_market_value = self.parse_market_value(cells[3].get_text(strip=True))
                    return True
            return False

        for table in soup.select("table"):
            tfoot = table.find("tfoot")
            if tfoot:
                for tr in tfoot.select("tr"):
                    if _parse_total_row(tr.select("td, th")):
                        break
            if total_market_value is None and average_age is None:
                # Fallback: last tbody row (some layouts put Total there)
                tbody_rows = table.select("tbody tr")
                if tbody_rows:
                    if _parse_total_row(tbody_rows[-1].select("td, th")):
                        pass
            if total_market_value is not None or average_age is not None:
                break
        
        # Fallback: total_market_value from header if tfoot not found
        if total_market_value is None:
            market_value_el = soup.select_one("a.data-header__market-value-wrapper")
            if market_value_el:
                total_market_value = self.parse_market_value(market_value_el.text)

        # Fallback: squad_size from total/avg when both are available
        if total_market_value and average_market_value and average_market_value > 0:
            squad_size = round(total_market_value / average_market_value)

        # Get foreigners, stadium (keep existing logic)
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
            
            # Parse based on label (squad_size and average_age now from table; only overwrite if not set)
            if "squad size" in label_text or "squad" in label_text or "kader" in label_text:
                if squad_size is None:
                    match = re.search(r"(\d+)", content_text)
                    if match:
                        squad_size = int(match.group(1))
            
            elif "ø-age" in label_text or "average age" in label_text or "-age" in label_text:
                if average_age is None:
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
        
        # Use passed league info, or get from LEAGUE_INFO, or fallback to breadcrumb
        final_league = league_name
        final_league_id = league_id
        final_country = country
        
        # Try to get from LEAGUE_INFO if not passed
        if not final_league and league_key:
            info = self.LEAGUE_INFO.get(league_key, {})
            final_league = info.get("name", league_key)
            final_league_id = info.get("id", "")
            final_country = info.get("country", "")
        
        # Fallback to breadcrumb if still empty
        if not final_league:
            breadcrumb = soup.select("div.breadcrumb a")
            for link in breadcrumb:
                href = link.get("href", "")
                if "/wettbewerb/" in href:
                    final_league = link.text.strip()
                    match = re.search(r"/wettbewerb/(\w+)", href)
                    if match:
                        final_league_id = match.group(1)
        
        return Team(
            team_id=team_id,
            name=name,
            league=final_league,
            league_id=final_league_id,
            country=final_country,
            season=self.season,
            squad_size=squad_size,
            average_age=average_age,
            total_market_value=total_market_value,
            average_market_value=average_market_value,
            foreign_players_count=foreign_players_count,
            national_players_count=national_players_count,
            stadium_name=stadium_name,
            stadium_capacity=stadium_capacity,
            logo_url=logo_url,
            profile_url=team_url,
        )
    
    def scrape_league_teams(
        self,
        league: str,
        skip_team_ids: set = None,
    ) -> List[Team]:
        """
        Scrape all teams from a league.
        
        Args:
            league: League identifier (e.g., "laliga", "premier")
            skip_team_ids: Team IDs to skip (already scraped).
        
        Returns:
            List of Team objects
        """
        team_infos = self.get_league_teams(league)
        
        if not team_infos:
            self.log(f"No teams found for league: {league}")
            return []
        
        # Get league info once to pass to all teams
        league_info = self.LEAGUE_INFO.get(league, {})
        league_name = league_info.get("name", league)
        league_id = league_info.get("id", "")
        country = league_info.get("country", "")
        
        teams = []
        _skip = skip_team_ids or set()
        
        for i, info in enumerate(team_infos):
            if info["team_id"] in _skip:
                self.log(f"  [{i+1}/{len(team_infos)}] {info['team_name']} (already scraped, skipping)")
                continue

            self.log(f"  [{i+1}/{len(team_infos)}] {info['team_name']}")
            
            team = self.scrape_team(
                team_id=info["team_id"],
                team_url=info["team_url"],
                league_key=league,
                league_name=league_name,
                league_id=league_id,
                country=country,
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
        loaded_data: list = []
        loaded_by_id: dict = {}

        # Load existing data for incremental scraping
        skip_team_ids: set = set()
        if self.use_downloaded_data:
            existing_all = self.load_json(f"teams_all_{self.season}")
            if existing_all:
                skip_team_ids = {t["team_id"] for t in existing_all if "team_id" in t}
                loaded_by_id = {t["team_id"]: t for t in existing_all if "team_id" in t}
                loaded_data = existing_all
                self.log(f"\nIncremental mode: {len(skip_team_ids)} teams already scraped")
        
        for league in leagues:
            self.log(f"\n=== Scraping teams from {league.upper()} ===")
            teams = self.scrape_league_teams(league, skip_team_ids=skip_team_ids)
            all_teams[league] = teams
            
            # Save per-league file
            teams_data = [t.to_dict() for t in teams]
            new_ids = {t.team_id for t in teams}
            league_id = self.LEAGUE_INFO.get(league, {}).get("id", "")
            for tid, tdict in loaded_by_id.items():
                if tid not in new_ids and tdict.get("league_id") == league_id:
                    teams_data.append(tdict)
            self.save_json(teams_data, f"teams_{league}_{self.season}")

            # Update skip set so subsequent leagues benefit
            for t in teams:
                skip_team_ids.add(t.team_id)
        
        # Save combined _all_ file (new + existing)
        all_teams_list = []
        for teams in all_teams.values():
            all_teams_list.extend([t.to_dict() for t in teams])
        all_teams_list.extend(loaded_data)
        self.save_json(all_teams_list, f"teams_all_{self.season}")
        
        return all_teams


if __name__ == "__main__":
    scraper = TransfermarktTeamsScraper()
    scraper.run()
