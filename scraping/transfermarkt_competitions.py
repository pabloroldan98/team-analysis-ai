# scraping/transfermarkt_competitions.py
"""
Scraper for league/competition standings from Transfermarkt.
"""
from __future__ import annotations

import re
from typing import List, Optional, Dict

from scraping.base_scraper import BaseScraper
from competition import CompetitionStanding


class TransfermarktCompetitionsScraper(BaseScraper):
    """Scraper for competition standings from Transfermarkt."""
    
    def scrape_competition(self, league_key: str) -> List[CompetitionStanding]:
        """
        Scrape standings for a single competition and season.
        
        Args:
            league_key: League identifier (e.g., "laliga", "premier")
        
        Returns:
            List of CompetitionStanding objects
        """
        # Get base URL for the league, e.g. /premier-league/startseite/wettbewerb/GB1
        league_url = self.get_league_url(league_key)
        if not league_url:
            self.log(f"Unknown league: {league_key}")
            return []
            
        # Transform startseite to tabelle
        competition_url = league_url.replace("/startseite/", "/tabelle/")
        url = f"{self.BASE_URL}{competition_url}/saison_id/{self.season_year}"
        
        self.log(f"Scraping standings: {league_key} for season {self.season}")
        soup = self.fetch_page(url)
        
        if not soup:
            return []
            
        info = self.LEAGUE_INFO.get(league_key, {})
        competition_id = info.get("id", "")
        
        standings = []
        table = soup.select_one("div.responsive-table table")
        if table:
            tbody = table.select_one("tbody")
            if tbody:
                for tr in tbody.select("tr"):
                    tds = tr.select("td")
                    # Transfermarkt standings tables usually have around 10 columns
                    if len(tds) > 8:
                        try:
                            position = int(tds[0].text.strip())
                        except ValueError:
                            continue
                            
                        name_td = tds[2]
                        a_tag = name_td.select_one("a")
                        if not a_tag:
                            continue
                            
                        team_name = a_tag.get("title", "") or a_tag.text.strip()
                        href = a_tag.get("href", "")
                        team_id = self.extract_team_id(href) or ""
                        
                        try:
                            matches_played = int(tds[3].text.strip())
                            wins = int(tds[4].text.strip())
                            draws = int(tds[5].text.strip())
                            losses = int(tds[6].text.strip())
                            
                            goals_text = tds[7].text.strip()
                            goals_for, goals_against = 0, 0
                            if ":" in goals_text:
                                gf, ga = goals_text.split(":")
                                goals_for = int(gf)
                                goals_against = int(ga)
                                
                            gd_text = tds[8].text.strip().replace("+", "")
                            goal_difference = int(gd_text) if gd_text else 0
                            
                            points = int(tds[9].text.strip())
                            
                            standing = CompetitionStanding(
                                competition_id=competition_id,
                                season=self.season_year,
                                team_id=team_id,
                                team_name=team_name,
                                position=position,
                                matches_played=matches_played,
                                wins=wins,
                                draws=draws,
                                losses=losses,
                                goals_for=goals_for,
                                goals_against=goals_against,
                                goal_difference=goal_difference,
                                points=points
                            )
                            standings.append(standing)
                        except (ValueError, IndexError) as e:
                            self.log(f"  Error parsing row for {team_name}: {e}")
                            continue
                            
        self.log(f"  Found {len(standings)} teams in standings")
        return standings

    def run(self, leagues: List[str] = None) -> Dict[str, List[CompetitionStanding]]:
        """
        Run the scraper for specified leagues.
        
        Args:
            leagues: List of league identifiers. Defaults to top 5.
        
        Returns:
            Dict with league_key -> List of CompetitionStanding objects
        """
        if leagues is None:
            leagues = ["laliga", "premier", "bundesliga", "seriea", "ligue1"]
        
        all_competitions = {}
        loaded_data: list = []  # dicts loaded from existing files
        loaded_by_id: dict = {}

        # Load existing data for incremental scraping
        skip_comp_ids: set = set()
        if self.use_downloaded_data:
            existing_all = self.load_json(f"competitions_all_{self.season}")
            if existing_all:
                for comp in existing_all:
                    if "competition_id" in comp:
                        skip_comp_ids.add(comp["competition_id"])
                loaded_data = existing_all
                self.log(f"\nIncremental mode: {len(skip_comp_ids)} competitions already scraped")
        
        for league_key in leagues:
            league_id = self.LEAGUE_INFO.get(league_key, {}).get("id", "")
            
            if league_id and league_id in skip_comp_ids:
                self.log(f"\n=== {league_key.upper()}: already scraped, skipping ===")
                continue
            
            self.log(f"\n=== Scraping {league_key.upper()} ===")
            standings = self.scrape_competition(league_key)
            
            if standings:
                all_competitions[league_key] = standings
                
                # Save per-league file
                self.save_json(
                    [s.to_dict() for s in standings],
                    f"competitions_{league_key}_{self.season}",
                    min_items=1,
                    id_field="id",
                    data_type="competitions"
                )
        
        # Save combined _all_ file (new + existing)
        all_standings_data = []
        for standings_list in all_competitions.values():
            all_standings_data.extend([s.to_dict() for s in standings_list])
            
        all_standings_data.extend(loaded_data)
        
        if all_standings_data:
            self.save_json(
                all_standings_data,
                f"competitions_all_{self.season}",
                min_items=1,
                id_field="id",
                data_type="competitions"
            )
        
        return all_competitions

    @classmethod
    def get_available_leagues(cls) -> List[str]:
        """Get list of available league keys."""
        return list(cls.LEAGUE_INFO.keys())


if __name__ == "__main__":
    scraper = TransfermarktCompetitionsScraper()
    scraper.run()
