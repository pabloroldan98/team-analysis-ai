# competition.py
"""
Competition Standing object for team-analysis-ai.
Represents a team's final standing in a competition for a specific season.
"""
from __future__ import annotations
from typing import Optional


class CompetitionStanding:
    """Represents a team's standing in a competition."""
    
    def __init__(
        self,
        competition_id: str,
        season: str,
        team_id: str,
        team_name: str,
        position: int,
        matches_played: int,
        wins: int,
        draws: int,
        losses: int,
        goals_for: int,
        goals_against: int,
        goal_difference: int,
        points: int,
    ):
        self.competition_id = competition_id
        self.season = season
        self.team_id = team_id
        self.team_name = team_name
        self.position = position
        self.matches_played = matches_played
        self.wins = wins
        self.draws = draws
        self.losses = losses
        self.goals_for = goals_for
        self.goals_against = goals_against
        self.goal_difference = goal_difference
        self.points = points
        
        # Generate a unique ID for this standing record
        self.id = f"{competition_id}_{season}_{team_id}"

    def __str__(self):
        return f"{self.position}. {self.team_name} - {self.points} pts ({self.season})"
    
    def __repr__(self):
        return f"CompetitionStanding(competition_id={self.competition_id}, team_id={self.team_id}, season={self.season})"
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "competition_id": self.competition_id,
            "season": self.season,
            "team_id": self.team_id,
            "team_name": self.team_name,
            "position": self.position,
            "matches_played": self.matches_played,
            "wins": self.wins,
            "draws": self.draws,
            "losses": self.losses,
            "goals_for": self.goals_for,
            "goals_against": self.goals_against,
            "goal_difference": self.goal_difference,
            "points": self.points,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> CompetitionStanding:
        """Create from dictionary."""
        return cls(
            competition_id=data.get("competition_id", ""),
            season=data.get("season", ""),
            team_id=data.get("team_id", ""),
            team_name=data.get("team_name", ""),
            position=data.get("position", 0),
            matches_played=data.get("matches_played", 0),
            wins=data.get("wins", 0),
            draws=data.get("draws", 0),
            losses=data.get("losses", 0),
            goals_for=data.get("goals_for", 0),
            goals_against=data.get("goals_against", 0),
            goal_difference=data.get("goal_difference", 0),
            points=data.get("points", 0),
        )
