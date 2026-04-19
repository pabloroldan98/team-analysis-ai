# valuation.py
"""
Valuation object for team-analysis-ai.
Represents a player's market valuation at a point in time.
"""
from __future__ import annotations
from typing import Optional


class Valuation:
    """Represents a player market valuation at a specific date."""
    
    def __init__(
        self,
        valuation_id: str,
        player_id: str,
        player_name: str = "",
        valuation_amount: Optional[float] = None,
        valuation_date: str = "",
        club_name_at_valuation: str = "",
        club_id_at_valuation: str = "",
        age_at_valuation: Optional[int] = None,
    ):
        self.valuation_id = valuation_id
        self.player_id = player_id
        self.player_name = player_name
        self.valuation_amount = valuation_amount
        self.valuation_date = valuation_date
        self.club_name_at_valuation = club_name_at_valuation
        self.club_id_at_valuation = club_id_at_valuation
        self.age_at_valuation = age_at_valuation
    
    def __str__(self):
        value_str = f"€{self.valuation_amount/1_000_000:.1f}M" if self.valuation_amount else "N/A"
        return f"{self.player_name}: {value_str} ({self.valuation_date})"
    
    def __repr__(self):
        return f"Valuation(id={self.valuation_id}, player={self.player_name}, amount={self.valuation_amount})"
    
    def __eq__(self, other):
        if not isinstance(other, Valuation):
            return False
        if self.valuation_id and other.valuation_id:
            return self.valuation_id == other.valuation_id
        return (self.player_id == other.player_id and 
                self.valuation_date == other.valuation_date)
    
    def __hash__(self):
        return hash(self.valuation_id or f"{self.player_id}_{self.valuation_date}")
    
    def __lt__(self, other):
        """Compare by valuation date for sorting."""
        if not isinstance(other, Valuation):
            return NotImplemented
        return self.valuation_date < other.valuation_date
    
    @property
    def valuation_in_millions(self) -> Optional[float]:
        """Get valuation amount in millions."""
        if self.valuation_amount is None:
            return None
        return self.valuation_amount / 1_000_000
    
    def to_dict(self) -> dict:
        """Convert Valuation to dictionary for JSON serialization."""
        return {
            "valuation_id": self.valuation_id,
            "player_id": self.player_id,
            "player_name": self.player_name,
            "valuation_amount": self.valuation_amount,
            "valuation_date": self.valuation_date,
            "club_name_at_valuation": self.club_name_at_valuation,
            "club_id_at_valuation": self.club_id_at_valuation,
            "age_at_valuation": self.age_at_valuation,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Valuation:
        """Create Valuation from dictionary."""
        # Support old field name (club_at_valuation) for backwards compatibility
        club_name = data.get("club_name_at_valuation") or data.get("club_at_valuation", "")
        
        return cls(
            valuation_id=data.get("valuation_id", ""),
            player_id=data.get("player_id", ""),
            player_name=data.get("player_name", ""),
            valuation_amount=data.get("valuation_amount"),
            valuation_date=data.get("valuation_date", ""),
            club_name_at_valuation=club_name,
            club_id_at_valuation=data.get("club_id_at_valuation", ""),
            age_at_valuation=data.get("age_at_valuation"),
        )
