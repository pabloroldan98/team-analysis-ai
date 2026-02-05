# scraping/models/valuation.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class Valuation:
    """Represents a player's market valuation at a specific point in time."""
    
    valuation_id: str
    player_id: str
    player_name: str
    
    # Valuation details
    valuation_amount: float  # in euros
    valuation_date: date
    
    # Context
    club_at_valuation: Optional[str] = None
    club_id_at_valuation: Optional[str] = None
    age_at_valuation: Optional[int] = None
    
    # Source
    source: str = "transfermarkt"
    
    def __str__(self) -> str:
        return f"{self.player_name}: €{self.valuation_amount/1_000_000:.1f}M ({self.valuation_date})"
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Valuation):
            return False
        return self.valuation_id == other.valuation_id
    
    def __hash__(self) -> int:
        return hash(self.valuation_id)
    
    def to_dict(self) -> dict:
        """Convert Valuation to dictionary for JSON serialization."""
        return {
            "valuation_id": self.valuation_id,
            "player_id": self.player_id,
            "player_name": self.player_name,
            "valuation_amount": self.valuation_amount,
            "valuation_date": self.valuation_date.isoformat() if self.valuation_date else None,
            "club_at_valuation": self.club_at_valuation,
            "club_id_at_valuation": self.club_id_at_valuation,
            "age_at_valuation": self.age_at_valuation,
            "source": self.source,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Valuation:
        """Create Valuation from dictionary."""
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
        
        valuation_date = parse_date(data.get("valuation_date"))
        if valuation_date is None:
            valuation_date = date.today()
        
        return cls(
            valuation_id=data.get("valuation_id", ""),
            player_id=data.get("player_id", ""),
            player_name=data.get("player_name", ""),
            valuation_amount=data.get("valuation_amount", 0),
            valuation_date=valuation_date,
            club_at_valuation=data.get("club_at_valuation"),
            club_id_at_valuation=data.get("club_id_at_valuation"),
            age_at_valuation=data.get("age_at_valuation"),
            source=data.get("source", "transfermarkt"),
        )
