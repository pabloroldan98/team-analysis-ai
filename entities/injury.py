# injury.py
"""
Injury object for team-analysis-ai.
Represents a player's injury record from Transfermarkt.
"""
from __future__ import annotations
from typing import Optional


class Injury:
    """Represents a player injury record."""
    
    def __init__(
        self,
        injury_id: str,
        player_id: str,
        player_name: str = "",
        season: str = "",
        injury: str = "",
        date_from: str = "",
        date_until: str = "",
        days: Optional[int] = None,
        games_missed: Optional[int] = None,
        club_name: str = "",
        club_id: str = "",
    ):
        self.injury_id = injury_id
        self.player_id = player_id
        self.player_name = player_name
        self.season = season
        self.injury = injury
        self.date_from = date_from
        self.date_until = date_until
        self.days = days
        self.games_missed = games_missed
        self.club_name = club_name
        self.club_id = club_id
    
    def __str__(self):
        days_str = f"{self.days} days" if self.days is not None else "N/A"
        return f"{self.player_name}: {self.injury} ({self.date_from} - {self.date_until}, {days_str})"
    
    def __repr__(self):
        return f"Injury(id={self.injury_id}, player={self.player_name}, injury={self.injury})"
    
    def __eq__(self, other):
        if not isinstance(other, Injury):
            return False
        if self.injury_id and other.injury_id:
            return self.injury_id == other.injury_id
        return (self.player_id == other.player_id and
                self.date_from == other.date_from and
                self.injury == other.injury)
    
    def __hash__(self):
        return hash(self.injury_id or f"{self.player_id}_{self.date_from}_{self.injury}")
    
    def to_dict(self) -> dict:
        """Convert Injury to dictionary for JSON serialization."""
        return {
            "injury_id": self.injury_id,
            "player_id": self.player_id,
            "player_name": self.player_name,
            "season": self.season,
            "injury": self.injury,
            "date_from": self.date_from,
            "date_until": self.date_until,
            "days": self.days,
            "games_missed": self.games_missed,
            "club_name": self.club_name,
            "club_id": self.club_id,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Injury:
        """Create Injury from dictionary."""
        return cls(
            injury_id=data.get("injury_id", ""),
            player_id=data.get("player_id", ""),
            player_name=data.get("player_name", ""),
            season=data.get("season", ""),
            injury=data.get("injury", ""),
            date_from=data.get("date_from", ""),
            date_until=data.get("date_until", ""),
            days=data.get("days"),
            games_missed=data.get("games_missed"),
            club_name=data.get("club_name", ""),
            club_id=data.get("club_id", ""),
        )
