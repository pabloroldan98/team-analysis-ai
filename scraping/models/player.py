# scraping/models/player.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class Player:
    """Represents a football player with all relevant attributes."""
    
    player_id: str
    name: str
    current_club: str
    current_club_id: Optional[str] = None
    
    # Personal info
    age: Optional[int] = None
    birth_date: Optional[date] = None
    nationality: Optional[str] = None
    second_nationality: Optional[str] = None
    
    # Physical attributes
    height: Optional[int] = None  # in cm
    preferred_foot: Optional[str] = None  # "Left", "Right", "Both"
    
    # Playing info
    position: Optional[str] = None  # Main position
    detailed_position: Optional[str] = None  # More specific position
    shirt_number: Optional[int] = None
    
    # Contract info
    contract_expires: Optional[date] = None
    joined_date: Optional[date] = None
    
    # Market value
    current_market_value: Optional[float] = None  # in euros
    highest_market_value: Optional[float] = None
    highest_market_value_date: Optional[date] = None
    
    # Media
    img_url: Optional[str] = None
    profile_url: Optional[str] = None
    
    # Season-specific
    season: Optional[str] = None
    
    def __str__(self) -> str:
        value_str = f"€{self.current_market_value/1_000_000:.1f}M" if self.current_market_value else "N/A"
        return f"{self.name} ({self.position}, {self.current_club}) - {value_str}"
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Player):
            return False
        return self.player_id == other.player_id
    
    def __hash__(self) -> int:
        return hash(self.player_id)
    
    def to_dict(self) -> dict:
        """Convert Player to dictionary for JSON serialization."""
        return {
            "player_id": self.player_id,
            "name": self.name,
            "current_club": self.current_club,
            "current_club_id": self.current_club_id,
            "age": self.age,
            "birth_date": self.birth_date.isoformat() if self.birth_date else None,
            "nationality": self.nationality,
            "second_nationality": self.second_nationality,
            "height": self.height,
            "preferred_foot": self.preferred_foot,
            "position": self.position,
            "detailed_position": self.detailed_position,
            "shirt_number": self.shirt_number,
            "contract_expires": self.contract_expires.isoformat() if self.contract_expires else None,
            "joined_date": self.joined_date.isoformat() if self.joined_date else None,
            "current_market_value": self.current_market_value,
            "highest_market_value": self.highest_market_value,
            "highest_market_value_date": self.highest_market_value_date.isoformat() if self.highest_market_value_date else None,
            "img_url": self.img_url,
            "profile_url": self.profile_url,
            "season": self.season,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Player:
        """Create Player from dictionary."""
        from datetime import datetime
        
        def parse_date(d):
            if d is None:
                return None
            if isinstance(d, date):
                return d
            try:
                return datetime.fromisoformat(d).date()
            except (ValueError, TypeError):
                return None
        
        return cls(
            player_id=data.get("player_id", ""),
            name=data.get("name", ""),
            current_club=data.get("current_club", ""),
            current_club_id=data.get("current_club_id"),
            age=data.get("age"),
            birth_date=parse_date(data.get("birth_date")),
            nationality=data.get("nationality"),
            second_nationality=data.get("second_nationality"),
            height=data.get("height"),
            preferred_foot=data.get("preferred_foot"),
            position=data.get("position"),
            detailed_position=data.get("detailed_position"),
            shirt_number=data.get("shirt_number"),
            contract_expires=parse_date(data.get("contract_expires")),
            joined_date=parse_date(data.get("joined_date")),
            current_market_value=data.get("current_market_value"),
            highest_market_value=data.get("highest_market_value"),
            highest_market_value_date=parse_date(data.get("highest_market_value_date")),
            img_url=data.get("img_url"),
            profile_url=data.get("profile_url"),
            season=data.get("season"),
        )
