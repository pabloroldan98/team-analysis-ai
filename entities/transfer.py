# transfer.py
"""
Transfer object for team-analysis-ai.
Represents a player transfer between clubs.
"""
from __future__ import annotations
from typing import Optional


class Transfer:
    """Represents a player transfer."""
    
    def __init__(
        self,
        transfer_id: str,
        player_id: str,
        player_name: str = "",
        from_club_name: str = "",
        from_club_id: str = "",
        to_club_name: str = "",
        to_club_id: str = "",
        price: Optional[float] = None,
        price_str: str = "",
        transfer_date: str = "",
        season: str = "",
        transfer_type: str = "",
        is_loan: bool = False,
        market_value_at_transfer: Optional[float] = None,
    ):
        self.transfer_id = transfer_id
        self.player_id = player_id
        self.player_name = player_name
        self.from_club_name = from_club_name
        self.from_club_id = from_club_id
        self.to_club_name = to_club_name
        self.to_club_id = to_club_id
        self.price = price
        self.price_str = price_str
        self.transfer_date = transfer_date
        self.season = season
        self.transfer_type = transfer_type
        self.is_loan = is_loan
        self.market_value_at_transfer = market_value_at_transfer
    
    def __str__(self):
        fee_str = self.price_str or (f"€{self.price/1_000_000:.1f}M" if self.price else "Free")
        return f"{self.player_name}: {self.from_club_name} -> {self.to_club_name} ({fee_str})"
    
    def __repr__(self):
        return f"Transfer(id={self.transfer_id}, player={self.player_name}, {self.from_club_name}->{self.to_club_name})"
    
    def __eq__(self, other):
        if not isinstance(other, Transfer):
            return False
        if self.transfer_id and other.transfer_id:
            return self.transfer_id == other.transfer_id
        return (self.player_id == other.player_id and 
                self.from_club_id == other.from_club_id and 
                self.to_club_id == other.to_club_id and
                self.season == other.season)
    
    def __hash__(self):
        return hash(self.transfer_id or f"{self.player_id}_{self.from_club_id}_{self.to_club_id}")
    
    @property
    def is_free_transfer(self) -> bool:
        """Check if this was a free transfer."""
        if self.price is not None and self.price == 0:
            return True
        fee_lower = self.price_str.lower()
        return "free" in fee_lower or "ablösefrei" in fee_lower or "libre" in fee_lower
    
    def to_dict(self) -> dict:
        """Convert Transfer to dictionary for JSON serialization."""
        return {
            "transfer_id": self.transfer_id,
            "player_id": self.player_id,
            "player_name": self.player_name,
            "from_club_name": self.from_club_name,
            "from_club_id": self.from_club_id,
            "to_club_name": self.to_club_name,
            "to_club_id": self.to_club_id,
            "price": self.price,
            "price_str": self.price_str,
            "transfer_date": self.transfer_date,
            "season": self.season,
            "transfer_type": self.transfer_type,
            "is_loan": self.is_loan,
            "market_value_at_transfer": self.market_value_at_transfer,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Transfer:
        """Create Transfer from dictionary."""
        # Support old field names for backwards compatibility
        price = data.get("price") if data.get("price") is not None else data.get("transfer_fee")
        price_str = data.get("price_str") or data.get("transfer_fee_str", "")
        from_club_name = data.get("from_club_name") or data.get("from_club", "")
        to_club_name = data.get("to_club_name") or data.get("to_club", "")
        
        return cls(
            transfer_id=data.get("transfer_id", ""),
            player_id=data.get("player_id", ""),
            player_name=data.get("player_name", ""),
            from_club_name=from_club_name,
            from_club_id=data.get("from_club_id", ""),
            to_club_name=to_club_name,
            to_club_id=data.get("to_club_id", ""),
            price=price,
            price_str=price_str,
            transfer_date=data.get("transfer_date", ""),
            season=data.get("season", ""),
            transfer_type=data.get("transfer_type", ""),
            is_loan=data.get("is_loan", False),
            market_value_at_transfer=data.get("market_value_at_transfer"),
        )
