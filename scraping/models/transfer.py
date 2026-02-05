# scraping/models/transfer.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass
class Transfer:
    """Represents a player transfer between clubs."""
    
    transfer_id: str
    player_id: str
    player_name: str
    
    # Transfer details
    from_club: str
    from_club_id: Optional[str] = None
    to_club: str = ""
    to_club_id: Optional[str] = None
    
    # Financial
    transfer_fee: Optional[float] = None  # in euros, None for undisclosed
    market_value_at_transfer: Optional[float] = None
    
    # Date
    transfer_date: Optional[date] = None
    season: Optional[str] = None
    transfer_window: Optional[str] = None  # "Summer", "Winter"
    
    # Type
    transfer_type: Optional[str] = None  # "purchase", "loan", "free", "loan_return", "end_of_loan"
    loan_fee: Optional[float] = None  # For loans
    
    # Additional info
    is_loan: bool = False
    contract_end_date: Optional[date] = None
    
    def __str__(self) -> str:
        fee_str = f"€{self.transfer_fee/1_000_000:.1f}M" if self.transfer_fee else "Free/Undisclosed"
        return f"{self.player_name}: {self.from_club} → {self.to_club} ({fee_str})"
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Transfer):
            return False
        return self.transfer_id == other.transfer_id
    
    def __hash__(self) -> int:
        return hash(self.transfer_id)
    
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
            "market_value_at_transfer": self.market_value_at_transfer,
            "transfer_date": self.transfer_date.isoformat() if self.transfer_date else None,
            "season": self.season,
            "transfer_window": self.transfer_window,
            "transfer_type": self.transfer_type,
            "loan_fee": self.loan_fee,
            "is_loan": self.is_loan,
            "contract_end_date": self.contract_end_date.isoformat() if self.contract_end_date else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Transfer:
        """Create Transfer from dictionary."""
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
            transfer_id=data.get("transfer_id", ""),
            player_id=data.get("player_id", ""),
            player_name=data.get("player_name", ""),
            from_club=data.get("from_club", ""),
            from_club_id=data.get("from_club_id"),
            to_club=data.get("to_club", ""),
            to_club_id=data.get("to_club_id"),
            transfer_fee=data.get("transfer_fee"),
            market_value_at_transfer=data.get("market_value_at_transfer"),
            transfer_date=parse_date(data.get("transfer_date")),
            season=data.get("season"),
            transfer_window=data.get("transfer_window"),
            transfer_type=data.get("transfer_type"),
            loan_fee=data.get("loan_fee"),
            is_loan=data.get("is_loan", False),
            contract_end_date=parse_date(data.get("contract_end_date")),
        )
