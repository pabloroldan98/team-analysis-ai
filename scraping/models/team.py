# scraping/models/team.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class Team:
    """Represents a football team/club with all relevant attributes."""
    
    team_id: str
    name: str
    
    # League info
    league: Optional[str] = None
    league_id: Optional[str] = None
    country: Optional[str] = None
    
    # Season-specific
    season: Optional[str] = None
    
    # Squad info
    squad_size: Optional[int] = None
    average_age: Optional[float] = None
    foreigners_count: Optional[int] = None
    foreigners_percentage: Optional[float] = None
    national_team_players: Optional[int] = None
    
    # Market value
    total_market_value: Optional[float] = None  # in euros
    average_market_value: Optional[float] = None
    
    # Stadium info
    stadium_name: Optional[str] = None
    stadium_capacity: Optional[int] = None
    
    # Media
    logo_url: Optional[str] = None
    profile_url: Optional[str] = None
    
    # Players (list of player_ids)
    player_ids: List[str] = field(default_factory=list)
    
    def __str__(self) -> str:
        value_str = f"€{self.total_market_value/1_000_000:.1f}M" if self.total_market_value else "N/A"
        return f"{self.name} ({self.league}) - Squad: {self.squad_size or 'N/A'}, Value: {value_str}"
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Team):
            return False
        return self.team_id == other.team_id
    
    def __hash__(self) -> int:
        return hash(self.team_id)
    
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
            "foreigners_count": self.foreigners_count,
            "foreigners_percentage": self.foreigners_percentage,
            "national_team_players": self.national_team_players,
            "total_market_value": self.total_market_value,
            "average_market_value": self.average_market_value,
            "stadium_name": self.stadium_name,
            "stadium_capacity": self.stadium_capacity,
            "logo_url": self.logo_url,
            "profile_url": self.profile_url,
            "player_ids": self.player_ids,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Team:
        """Create Team from dictionary."""
        return cls(
            team_id=data.get("team_id", ""),
            name=data.get("name", ""),
            league=data.get("league"),
            league_id=data.get("league_id"),
            country=data.get("country"),
            season=data.get("season"),
            squad_size=data.get("squad_size"),
            average_age=data.get("average_age"),
            foreigners_count=data.get("foreigners_count"),
            foreigners_percentage=data.get("foreigners_percentage"),
            national_team_players=data.get("national_team_players"),
            total_market_value=data.get("total_market_value"),
            average_market_value=data.get("average_market_value"),
            stadium_name=data.get("stadium_name"),
            stadium_capacity=data.get("stadium_capacity"),
            logo_url=data.get("logo_url"),
            profile_url=data.get("profile_url"),
            player_ids=data.get("player_ids", []),
        )
