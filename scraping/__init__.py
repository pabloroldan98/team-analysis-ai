# scraping/__init__.py
"""
Scraping module for team-analysis-ai.

Contains modular scrapers for different data types:
- TransfermarktLeaguesScraper: League information
- TransfermarktTeamsScraper: Team information
- TransfermarktPlayersScraper: Player data
- TransfermarktTransfersScraper: Transfer records
- TransfermarktValuationsScraper: Market value history
"""

from scraping.base_scraper import BaseScraper
from scraping.transfermarkt_leagues import TransfermarktLeaguesScraper
from scraping.transfermarkt_teams import TransfermarktTeamsScraper
from scraping.transfermarkt_players import TransfermarktPlayersScraper
from scraping.transfermarkt_transfers import TransfermarktTransfersScraper
from scraping.transfermarkt_valuations import TransfermarktValuationsScraper

__all__ = [
    "BaseScraper",
    "TransfermarktLeaguesScraper",
    "TransfermarktTeamsScraper",
    "TransfermarktPlayersScraper",
    "TransfermarktTransfersScraper",
    "TransfermarktValuationsScraper",
]
