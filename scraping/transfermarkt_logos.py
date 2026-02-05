# scraping/transfermarkt_logos.py
"""
Scraper for team logos from Transfermarkt.
Downloads logo images and saves them locally.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List, Dict, Optional
import requests

from scraping.base_scraper import BaseScraper, ROOT_DIR


LOGOS_DIR = ROOT_DIR / "assets" / "logos"


class TransfermarktLogosScraper(BaseScraper):
    """Scraper for team logo images from Transfermarkt."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure logos directory exists
        LOGOS_DIR.mkdir(parents=True, exist_ok=True)
    
    def download_logo(self, logo_url: str, team_id: str, team_name: str = "") -> Optional[str]:
        """
        Download a logo image and save it locally.
        
        Args:
            logo_url: URL of the logo image
            team_id: Team ID for filename
            team_name: Team name for reference
        
        Returns:
            Path to saved file or None
        """
        if not logo_url:
            return None
        
        try:
            # Determine file extension
            ext = ".png"
            if ".svg" in logo_url:
                ext = ".svg"
            elif ".jpg" in logo_url or ".jpeg" in logo_url:
                ext = ".jpg"
            elif ".gif" in logo_url:
                ext = ".gif"
            
            # Create filename
            safe_name = re.sub(r"[^\w\-]", "_", team_name.lower()) if team_name else team_id
            filename = f"{team_id}_{safe_name}{ext}"
            filepath = LOGOS_DIR / filename
            
            # Download image
            self.log(f"  Downloading logo: {team_name or team_id}")
            
            response = requests.get(logo_url, headers=self.HEADERS, timeout=10)
            if response.status_code == 200:
                with open(filepath, "wb") as f:
                    f.write(response.content)
                
                return str(filepath)
            else:
                self.log(f"    Failed: HTTP {response.status_code}")
                return None
                
        except Exception as e:
            self.log(f"    Error downloading logo: {e}")
            return None
    
    def scrape_team_logo(self, team_id: str, team_url: str = None, team_name: str = "") -> Optional[Dict]:
        """
        Scrape and download logo for a single team.
        
        Args:
            team_id: Transfermarkt team ID
            team_url: Optional team URL
            team_name: Team name
        
        Returns:
            Dict with team info and logo path
        """
        if not team_url:
            team_url = f"{self.BASE_URL}/verein/startseite/verein/{team_id}"
        
        soup = self.fetch_page(team_url)
        if not soup:
            return None
        
        # Get team name if not provided
        if not team_name:
            header = soup.select_one("header.data-header h1")
            team_name = header.text.strip() if header else ""
        
        # Find logo URL
        logo_img = soup.select_one("div.data-header__profile-container img.data-header__profile-image")
        if not logo_img:
            logo_img = soup.select_one("img.data-header__profile-image")
        
        logo_url = ""
        if logo_img:
            # Try different attributes
            logo_url = logo_img.get("src", "") or logo_img.get("data-src", "")
        
        # Download the logo
        local_path = None
        if logo_url:
            local_path = self.download_logo(logo_url, team_id, team_name)
        
        return {
            "team_id": team_id,
            "team_name": team_name,
            "logo_url": logo_url,
            "local_path": local_path,
        }
    
    def scrape_league_logos(self, league: str) -> List[Dict]:
        """
        Scrape and download logos for all teams in a league.
        
        Args:
            league: League identifier
        
        Returns:
            List of dicts with team info and logo paths
        """
        team_infos = self.get_league_teams(league)
        
        if not team_infos:
            self.log(f"No teams found for league: {league}")
            return []
        
        results = []
        
        for i, info in enumerate(team_infos):
            self.log(f"[{i+1}/{len(team_infos)}] {info['team_name']}")
            
            result = self.scrape_team_logo(
                team_id=info["team_id"],
                team_url=info["team_url"],
                team_name=info["team_name"]
            )
            
            if result:
                results.append(result)
        
        return results
    
    def run(self, leagues: List[str] = None) -> dict:
        """
        Run the scraper for specified leagues.
        
        Args:
            leagues: List of league identifiers. Defaults to top 5.
        
        Returns:
            Dict with league -> list of logo results
        """
        if leagues is None:
            leagues = ["laliga", "premier", "bundesliga", "seriea", "ligue1"]
        
        all_data = {}
        
        for league in leagues:
            self.log(f"\n=== Downloading logos from {league.upper()} ===")
            results = self.scrape_league_logos(league)
            all_data[league] = results
            
            # Save metadata
            self.save_json(results, f"logos_{league}_{self.season}")
        
        # Save combined metadata
        combined = []
        for results in all_data.values():
            combined.extend(results)
        
        self.save_json(combined, f"logos_all_{self.season}")
        
        # Summary
        total = sum(len(r) for r in all_data.values())
        downloaded = sum(1 for r in combined if r.get("local_path"))
        self.log(f"\n=== Downloaded {downloaded}/{total} logos ===")
        
        return all_data


if __name__ == "__main__":
    scraper = TransfermarktLogosScraper()
    scraper.run()
