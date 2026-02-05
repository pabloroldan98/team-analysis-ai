# player.py
"""
Player object for team-analysis-ai.
Represents a football player with all relevant attributes.
"""
from __future__ import annotations
from typing import Optional, List
from datetime import date
from unidecode import unidecode


class Player:
    """Represents a football player."""
    
    def __init__(
        self,
        player_id: str,
        name: str,
        team: str = "",
        team_id: str = "",
        position: str = "N/A",
        age: int = None,
        birth_date: str = None,
        nationality: str = "",
        second_nationality: str = "",
        height: int = None,
        preferred_foot: str = "",
        shirt_number: int = None,
        market_value: float = None,
        contract_expires: str = None,
        joined_date: str = None,
        img_url: str = "",
        profile_url: str = "",
        season: str = "",
    ):
        self.player_id = player_id
        self.name = name
        self.team = team
        self.team_id = team_id
        self._position = position
        self.age = age
        self.birth_date = birth_date
        self.nationality = nationality
        self.second_nationality = second_nationality
        self.height = height
        self.preferred_foot = preferred_foot
        self.shirt_number = shirt_number
        self.market_value = market_value
        self.contract_expires = contract_expires
        self.joined_date = joined_date
        self.img_url = img_url
        self.profile_url = profile_url
        self.season = season
    
    def __str__(self):
        value_str = f"€{self.market_value/1_000_000:.1f}M" if self.market_value else "N/A"
        return f"({self.name}, {self.position}, {self.team}, {value_str})"
    
    def __repr__(self):
        return f"Player(id={self.player_id}, name={self.name}, team={self.team})"
    
    def __eq__(self, other):
        if not isinstance(other, Player):
            return False
        # Compare by ID first
        if self.player_id and other.player_id:
            return self.player_id == other.player_id
        # Fallback to name comparison
        return unidecode(self.name).lower().replace(" ", "").replace("-", "") == \
               unidecode(other.name).lower().replace(" ", "").replace("-", "")
    
    def __hash__(self):
        return hash(self.player_id or self.name)
    
    @property
    def position(self):
        return self._position
    
    @position.setter
    def position(self, pos: str = "N/A"):
        valid_positions = ["GK", "DEF", "MID", "ATT", "N/A"]
        if pos in valid_positions:
            self._position = pos
        else:
            self._position = self._normalize_position(pos)
    
    @staticmethod
    def _normalize_position(pos: str) -> str:
        """Normalize position string to standard format."""
        if not pos:
            return "N/A"
        pos = pos.strip().lower()
        
        if any(x in pos for x in ["keeper", "portero", "torwart", "gk", "goalkeeper"]):
            return "GK"
        if any(x in pos for x in ["back", "defens", "cb", "lb", "rb", "defensa", "verteidiger"]):
            return "DEF"
        if any(x in pos for x in ["midfield", "medio", "mittelfeld", "cm", "dm", "am"]):
            return "MID"
        if any(x in pos for x in ["forward", "striker", "wing", "delantero", "stürmer", "cf", "lw", "rw", "attack"]):
            return "ATT"
        
        return "N/A"
    
    def to_dict(self) -> dict:
        """Convert Player to dictionary for JSON serialization."""
        return {
            "player_id": self.player_id,
            "name": self.name,
            "team": self.team,
            "team_id": self.team_id,
            "position": self.position,
            "age": self.age,
            "birth_date": self.birth_date,
            "nationality": self.nationality,
            "second_nationality": self.second_nationality,
            "height": self.height,
            "preferred_foot": self.preferred_foot,
            "shirt_number": self.shirt_number,
            "market_value": self.market_value,
            "contract_expires": self.contract_expires,
            "joined_date": self.joined_date,
            "img_url": self.img_url,
            "profile_url": self.profile_url,
            "season": self.season,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Player:
        """Create Player from dictionary."""
        return cls(
            player_id=data.get("player_id", ""),
            name=data.get("name", ""),
            team=data.get("team", ""),
            team_id=data.get("team_id", ""),
            position=data.get("position", "N/A"),
            age=data.get("age"),
            birth_date=data.get("birth_date"),
            nationality=data.get("nationality", ""),
            second_nationality=data.get("second_nationality", ""),
            height=data.get("height"),
            preferred_foot=data.get("preferred_foot", ""),
            shirt_number=data.get("shirt_number"),
            market_value=data.get("market_value"),
            contract_expires=data.get("contract_expires"),
            joined_date=data.get("joined_date"),
            img_url=data.get("img_url", ""),
            profile_url=data.get("profile_url", ""),
            season=data.get("season", ""),
        )
