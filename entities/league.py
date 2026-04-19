# league.py
"""
League object for team-analysis-ai.
Represents a football league/competition for a season.
"""
from __future__ import annotations
from typing import Optional


class League:
    """Represents a football league/competition."""
    
    def __init__(
        self,
        league_id: str,
        name: str,
        country: str = "",
        season: str = "",
        tier: int = 1,  # 1 = top division, 2 = second division, etc.
        total_market_value: Optional[float] = None,
        num_teams: int = 0,
        num_players: int = 0,
        average_age: Optional[float] = None,
        average_market_value: Optional[float] = None,
        most_valuable_player: str = "",
        logo_url: str = "",
        profile_url: str = "",
    ):
        self.league_id = league_id
        self.name = name
        self.country = country
        self.season = season
        self.tier = tier
        self.total_market_value = total_market_value
        self.num_teams = num_teams
        self.num_players = num_players
        self.average_age = average_age
        self.average_market_value = average_market_value
        self.most_valuable_player = most_valuable_player
        self.logo_url = logo_url
        self.profile_url = profile_url
    
    def __str__(self):
        value_str = f"€{self.total_market_value/1_000_000_000:.2f}B" if self.total_market_value else "N/A"
        return f"{self.name} ({self.country}, {self.season}) - {self.num_teams} teams, {value_str}"
    
    def __repr__(self):
        return f"League(id={self.league_id}, name={self.name}, season={self.season})"
    
    def __eq__(self, other):
        if not isinstance(other, League):
            return False
        if self.league_id and other.league_id:
            return self.league_id == other.league_id and self.season == other.season
        return self.name == other.name and self.season == other.season
    
    def __hash__(self):
        return hash(f"{self.league_id}_{self.season}")
    
    @property
    def total_market_value_billions(self) -> Optional[float]:
        """Get total market value in billions."""
        if self.total_market_value is None:
            return None
        return self.total_market_value / 1_000_000_000
    
    def to_dict(self) -> dict:
        """Convert League to dictionary for JSON serialization."""
        return {
            "league_id": self.league_id,
            "name": self.name,
            "country": self.country,
            "season": self.season,
            "tier": self.tier,
            "total_market_value": self.total_market_value,
            "num_teams": self.num_teams,
            "num_players": self.num_players,
            "average_age": self.average_age,
            "average_market_value": self.average_market_value,
            "most_valuable_player": self.most_valuable_player,
            "logo_url": self.logo_url,
            "profile_url": self.profile_url,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> League:
        """Create League from dictionary."""
        return cls(
            league_id=data.get("league_id", ""),
            name=data.get("name", ""),
            country=data.get("country", ""),
            season=data.get("season", ""),
            tier=data.get("tier", 1),
            total_market_value=data.get("total_market_value"),
            num_teams=data.get("num_teams", 0),
            num_players=data.get("num_players", 0),
            average_age=data.get("average_age"),
            average_market_value=data.get("average_market_value"),
            most_valuable_player=data.get("most_valuable_player", ""),
            logo_url=data.get("logo_url", ""),
            profile_url=data.get("profile_url", ""),
        )
