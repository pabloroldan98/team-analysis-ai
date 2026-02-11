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
        main_position: str = "",
        other_positions: List[str] = None,
        age: int = None,
        birth_date: str = None,
        nationality: str = "",
        other_nationalities: List[str] = None,
        height: int = None,
        preferred_foot: str = "",
        shirt_number: int = None,
        market_value: float = None,
        img_url: str = "",
        profile_url: str = "",
        season: str = "",
        predicted_value: float = None,
        on_loan: bool = False,
        loaning_team: str = "",
        loaning_team_id: str = "",
    ):
        self.player_id = player_id
        self.name = name
        self.team = team
        self.team_id = team_id
        self._position = position
        self.main_position = main_position
        self.other_positions = other_positions or []
        self.age = age
        self.birth_date = birth_date
        self.nationality = nationality
        self.other_nationalities = other_nationalities or []
        self.height = height
        self.preferred_foot = preferred_foot
        self.shirt_number = shirt_number
        self.market_value = market_value
        self.img_url = img_url
        self.profile_url = profile_url
        self.season = season
        self.predicted_value = predicted_value  # ML-predicted future value
        self.on_loan = on_loan
        self.loaning_team = loaning_team  # team that owns the player (if on loan)
        self.loaning_team_id = loaning_team_id
    
    def __str__(self):
        value_str = f"€{self.market_value/1_000_000:.1f}M" if self.market_value is not None else "N/A"
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
    def value(self) -> float:
        """
        Get player value, preferring predicted_value if available.
        
        This allows the simulator to use ML-predicted values when set,
        falling back to market_value otherwise.
        """
        if self.predicted_value is not None:
            return self.predicted_value
        return self.market_value or 0.0
    
    @property
    def salary(self) -> float:
        """Salary computed as 10% of market value."""
        if self.market_value is None:
            return 0.0
        return self.market_value * 0.10

    @staticmethod
    def total_salaries(players: List["Player"]) -> float:
        """Return the sum of salaries for a list of players."""
        return sum(p.salary for p in players)

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
        
        if any(x in pos for x in ["goalkeeper", "keeper", "portero", "torwart", "gk", ]):
            return "GK"
        if any(x in pos for x in ["defender", "defend", "back", "defens", "cb", "lb", "rb", "defensa", "verteidiger", "def", ]):
            return "DEF"
        if any(x in pos for x in ["midfield", "midfielder", "medio", "mittelfeld", "cm", "dm", "am", "mid", ]):
            return "MID"
        if any(x in pos for x in ["attack", "attacker", "forward", "striker", "wing", "delantero", "stürmer", "cf", "lw", "rw", "att", ]):
            return "ATT"
        
        return "N/A"
    
    def to_dict(self) -> dict:
        """Convert Player to dictionary for JSON serialization."""
        result = {
            "player_id": self.player_id,
            "name": self.name,
            "team": self.team,
            "team_id": self.team_id,
            "position": self.position,
            "main_position": self.main_position,
            "other_positions": self.other_positions,
            "age": self.age,
            "birth_date": self.birth_date,
            "nationality": self.nationality,
            "other_nationalities": self.other_nationalities,
            "height": self.height,
            "preferred_foot": self.preferred_foot,
            "shirt_number": self.shirt_number,
            "market_value": self.market_value,
            "img_url": self.img_url,
            "profile_url": self.profile_url,
            "season": self.season,
        }
        # Only include predicted_value if set (ML feature)
        if self.predicted_value is not None:
            result["predicted_value"] = self.predicted_value
        if self.on_loan:
            result["on_loan"] = True
            result["loaning_team"] = self.loaning_team
            result["loaning_team_id"] = self.loaning_team_id
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> Player:
        """Create Player from dictionary."""
        return cls(
            player_id=data.get("player_id", ""),
            name=data.get("name", ""),
            team=data.get("team", ""),
            team_id=data.get("team_id", ""),
            position=data.get("position", "N/A"),
            main_position=data.get("main_position", ""),
            other_positions=data.get("other_positions", []),
            age=data.get("age"),
            birth_date=data.get("birth_date"),
            nationality=data.get("nationality", ""),
            other_nationalities=data.get("other_nationalities", []),
            height=data.get("height"),
            preferred_foot=data.get("preferred_foot", ""),
            shirt_number=data.get("shirt_number"),
            market_value=data.get("market_value"),
            img_url=data.get("img_url", ""),
            profile_url=data.get("profile_url", ""),
            season=data.get("season", ""),
            predicted_value=data.get("predicted_value"),
            on_loan=data.get("on_loan", False),
            loaning_team=data.get("loaning_team", ""),
            loaning_team_id=data.get("loaning_team_id", ""),
        )
