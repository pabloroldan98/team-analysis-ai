# team.py
"""
Team object for team-analysis-ai.
Represents a football team/club with all relevant attributes.
"""
from __future__ import annotations
from typing import Optional
from unidecode import unidecode


class Team:
    """Represents a football team."""
    
    def __init__(
        self,
        team_id: str,
        name: str,
        league: str = "",
        league_id: str = "",
        country: str = "",
        season: str = "",
        squad_size: int = None,
        average_age: float = None,
        total_market_value: float = None,
        average_market_value: float = None,
        foreign_players_count: int = None,
        national_players_count: int = None,
        stadium_name: str = "",
        stadium_capacity: int = None,
        logo_url: str = "",
        profile_url: str = "",
    ):
        self.team_id = team_id
        self.name = name
        self.league = league
        self.league_id = league_id
        self.country = country
        self.season = season
        self.squad_size = squad_size
        self.average_age = average_age
        self.total_market_value = total_market_value
        self.average_market_value = average_market_value
        self.foreign_players_count = foreign_players_count
        self.national_players_count = national_players_count
        self.stadium_name = stadium_name
        self.stadium_capacity = stadium_capacity
        self.logo_url = logo_url
        self.profile_url = profile_url
    
    def __str__(self):
        value_str = f"€{self.total_market_value/1_000_000:.1f}M" if self.total_market_value else "N/A"
        return f"({self.name}, {self.league}, {value_str})"
    
    def __repr__(self):
        return f"Team(id={self.team_id}, name={self.name})"
    
    def __eq__(self, other):
        if not isinstance(other, Team):
            return False
        # Compare by ID first
        if self.team_id and other.team_id:
            return self.team_id == other.team_id
        # Fallback to name comparison
        return unidecode(self.name).lower().replace(" ", "").replace("-", "") in \
               unidecode(other.name).lower().replace(" ", "").replace("-", "") or \
               unidecode(other.name).lower().replace(" ", "").replace("-", "") in \
               unidecode(self.name).lower().replace(" ", "").replace("-", "")
    
    def __hash__(self):
        return hash(self.team_id or self.name)
    
    def to_dict(self) -> dict:
        """Convert Team to dictionary for JSON serialization."""
        return {
            "team_id": self.team_id,
            "name": self.name,
            "league": self.league,
            "league_id": self.league_id,
            "country": self.country,
            "season": self.season,
            "squad_size": self.squad_size,
            "average_age": self.average_age,
            "total_market_value": self.total_market_value,
            "average_market_value": self.average_market_value,
            "foreign_players_count": self.foreign_players_count,
            "national_players_count": self.national_players_count,
            "stadium_name": self.stadium_name,
            "stadium_capacity": self.stadium_capacity,
            "logo_url": self.logo_url,
            "profile_url": self.profile_url,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Team:
        """Create Team from dictionary."""
        return cls(
            team_id=data.get("team_id", ""),
            name=data.get("name", ""),
            league=data.get("league", ""),
            league_id=data.get("league_id", ""),
            country=data.get("country", ""),
            season=data.get("season", ""),
            squad_size=data.get("squad_size"),
            average_age=data.get("average_age"),
            total_market_value=data.get("total_market_value"),
            average_market_value=data.get("average_market_value"),
            foreign_players_count=data.get("foreign_players_count"),
            national_players_count=data.get("national_players_count"),
            stadium_name=data.get("stadium_name", ""),
            stadium_capacity=data.get("stadium_capacity"),
            logo_url=data.get("logo_url", ""),
            profile_url=data.get("profile_url", ""),
        )
