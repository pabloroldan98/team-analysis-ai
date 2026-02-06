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
        from_club: str = "",
        from_club_id: str = "",
        to_club: str = "",
        to_club_id: str = "",
        transfer_fee: Optional[float] = None,
        transfer_fee_str: str = "",
        transfer_date: str = "",
        season: str = "",
        transfer_type: str = "",  # "in", "out", "loan_in", "loan_out"
        is_loan: bool = False,
        loan_fee: Optional[float] = None,
        market_value_at_transfer: Optional[float] = None,
    ):
        self.transfer_id = transfer_id
        self.player_id = player_id
        self.player_name = player_name
        self.from_club = from_club
        self.from_club_id = from_club_id
        self.to_club = to_club
        self.to_club_id = to_club_id
        self.transfer_fee = transfer_fee
        self.transfer_fee_str = transfer_fee_str
        self.transfer_date = transfer_date
        self.season = season
        self.transfer_type = transfer_type
        self.is_loan = is_loan
        self.loan_fee = loan_fee
        self.market_value_at_transfer = market_value_at_transfer
    
    def __str__(self):
        fee_str = self.transfer_fee_str or (f"€{self.transfer_fee/1_000_000:.1f}M" if self.transfer_fee else "Free")
        return f"{self.player_name}: {self.from_club} -> {self.to_club} ({fee_str})"
    
    def __repr__(self):
        return f"Transfer(id={self.transfer_id}, player={self.player_name}, {self.from_club}->{self.to_club})"
    
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
        if self.transfer_fee is not None and self.transfer_fee == 0:
            return True
        fee_lower = self.transfer_fee_str.lower()
        return "free" in fee_lower or "ablösefrei" in fee_lower or "libre" in fee_lower
    
    def to_dict(self) -> dict:
        """Convert Transfer to dictionary for JSON serialization."""
        return {
            "transfer_id": self.transfer_id,
            "player_id": self.player_id,
            "player_name": self.player_name,
            "from_club": self.from_club,
            "from_club_id": self.from_club_id,
            "to_club": self.to_club,
            "to_club_id": self.to_club_id,
            "transfer_fee": self.transfer_fee,
            "transfer_fee_str": self.transfer_fee_str,
            "transfer_date": self.transfer_date,
            "season": self.season,
            "transfer_type": self.transfer_type,
            "is_loan": self.is_loan,
            "loan_fee": self.loan_fee,
            "market_value_at_transfer": self.market_value_at_transfer,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Transfer:
        """Create Transfer from dictionary."""
        return cls(
            transfer_id=data.get("transfer_id", ""),
            player_id=data.get("player_id", ""),
            player_name=data.get("player_name", ""),
            from_club=data.get("from_club", ""),
            from_club_id=data.get("from_club_id", ""),
            to_club=data.get("to_club", ""),
            to_club_id=data.get("to_club_id", ""),
            transfer_fee=data.get("transfer_fee"),
            transfer_fee_str=data.get("transfer_fee_str", ""),
            transfer_date=data.get("transfer_date", ""),
            season=data.get("season", ""),
            transfer_type=data.get("transfer_type", ""),
            is_loan=data.get("is_loan", False),
            loan_fee=data.get("loan_fee"),
            market_value_at_transfer=data.get("market_value_at_transfer"),
        )
