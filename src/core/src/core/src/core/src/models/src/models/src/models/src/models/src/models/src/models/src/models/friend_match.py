"""
Friend Match models for GamePulse Bot
Handles friend challenges, matchmaking, and competitive gameplay
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    Column, BigInteger, String, Integer, Boolean, DateTime, 
    JSON, ForeignKey, Text, Float, Index, UniqueConstraint,
    func, Enum as SQLEnum
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.ext.hybrid import hybrid_property
import enum
import uuid

from src.core.database import Base, TimestampMixin


# ==================== Enums ====================
class MatchStatus(str, enum.Enum):
    """Status of a friend match"""
    PENDING = "pending"          # Challenge sent, waiting for response
    ACCEPTED = "accepted"        # Challenge accepted, waiting for game
    ACTIVE = "active"            # Game in progress
    COMPLETED = "completed"      # Game completed, winner determined
    EXPIRED = "expired"          # Challenge expired
    CANCELLED = "cancelled"      # Challenge cancelled
    DECLINED = "declined"        # Challenge declined
    
    @classmethod
    def list(cls) -> List[str]:
        return [status.value for status in cls]
    
    @classmethod
    def get_display_name(cls, status: str) -> str:
        """Get display name for status"""
        names = {
            "pending": "⏳ Pending",
            "accepted": "✅ Accepted",
            "active": "🎮 In Progress",
            "completed": "🏆 Completed",
            "expired": "⌛ Expired",
            "cancelled": "❌ Cancelled",
            "declined": "🙅 Declined"
        }
        return names.get(status, status.title())


class MatchType(str, enum.Enum):
    """Type of match"""
    FRIEND_CHALLENGE = "friend_challenge"  # Direct challenge between friends
    QUICK_MATCH = "quick_match"            # Random matchmaking
    TOURNAMENT = "tournament"              # Tournament match
    PRACTICE = "practice"                  # Practice mode
    
    @classmethod
    def list(cls) -> List[str]:
        return [match_type.value for match_type in cls]


class MatchResult(str, enum.Enum):
    """Result of a match"""
    CHALLENGER_WON = "challenger_won"
    OPPONENT_WON = "opponent_won"
    TIE = "tie"
    FORFEIT = "forfeit"
    DISQUALIFIED = "disqualified"
    CANCELLED = "cancelled"
    
    @classmethod
    def list(cls) -> List[str]:
        return [result.value for result in cls]


# ==================== Friend Match Model ====================
class FriendMatch(Base):
    """Friend match/challenge model"""
    
    __tablename__ = "friend_matches"
    __table_args__ = (
        Index("idx_friend_matches_challenger", "challenger_id"),
        Index("idx_friend_matches_opponent", "opponent_id"),
        Index("idx_friend_matches_status", "status"),
        Index("idx_friend_matches_game_type", "game_type"),
        Index("idx_friend_matches_match_type", "match_type"),
        Index("idx_friend_matches_created_at", "created_at"),
        Index("idx_friend_matches_completed_at", "completed_at"),
        Index("idx_friend_matches_expires_at", "expires_at"),
        Index("idx_friend_matches_winner", "winner_id"),
        Index("idx_friend_matches_user_status", "challenger_id", "status"),
        Index("idx_friend_matches_opponent_status", "opponent_id", "status"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    match_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    
    # Participants
    challenger_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    opponent_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Game details
    game_type: Mapped[str] = mapped_column(String(50), nullable=False)
    match_type: Mapped[str] = mapped_column(String(20), default=MatchType.FRIEND_CHALLENGE.value, nullable=False)
    
    # Session tracking
    challenger_session_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    opponent_session_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Scores
    challenger_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    opponent_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    winner_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    
    # Result
    result: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    result_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default=MatchStatus.PENDING.value, nullable=False)
    
    # Match metadata
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    wager_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wager_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    # Stats
    challenger_xp_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    challenger_points_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opponent_xp_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    opponent_points_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    declined_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    challenger: Mapped["User"] = relationship("User", foreign_keys=[challenger_id], back_populates="friend_matches_challenger")
    opponent: Mapped["User"] = relationship("User", foreign_keys=[opponent_id], back_populates="friend_matches_opponent")
    winner: Mapped[Optional["User"]] = relationship("User", foreign_keys=[winner_id], back_populates="friend_matches_winner")

    def __init__(self, **kwargs):
        if 'match_id' not in kwargs or not kwargs['match_id']:
            kwargs['match_id'] = self._generate_match_id()
        if 'expires_at' not in kwargs:
            kwargs['expires_at'] = datetime.utcnow() + timedelta(hours=24)
        super().__init__(**kwargs)

    # ==================== Properties ====================
    
    @staticmethod
    def _generate_match_id() -> str:
        """Generate unique match ID"""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        random_part = uuid.uuid4().hex[:8].upper()
        return f"MATCH{timestamp}{random_part}"
    
    @hybrid_property
    def is_pending(self) -> bool:
        """Check if match is pending"""
        return self.status == MatchStatus.PENDING.value
    
    @hybrid_property
    def is_accepted(self) -> bool:
        """Check if match is accepted"""
        return self.status == MatchStatus.ACCEPTED.value
    
    @hybrid_property
    def is_active(self) -> bool:
        """Check if match is active"""
        return self.status == MatchStatus.ACTIVE.value
    
    @hybrid_property
    def is_completed(self) -> bool:
        """Check if match is completed"""
        return self.status == MatchStatus.COMPLETED.value
    
    @hybrid_property
    def is_expired(self) -> bool:
        """Check if match is expired"""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False
    
    @hybrid_property
    def is_cancelled(self) -> bool:
        """Check if match is cancelled"""
        return self.status == MatchStatus.CANCELLED.value
    
    @hybrid_property
    def is_declined(self) -> bool:
        """Check if match is declined"""
        return self.status == MatchStatus.DECLINED.value
    
    @hybrid_property
    def is_tie(self) -> bool:
        """Check if match ended in a tie"""
        if not self.is_completed:
            return False
        if self.challenger_score is None or self.opponent_score is None:
            return False
        return self.challenger_score == self.opponent_score
    
    @hybrid_property
    def challenger_name(self) -> str:
        """Get challenger's display name"""
        if self.challenger:
            return self.challenger.display_name or self.challenger.full_name
        return "Unknown"
    
    @hybrid_property
    def opponent_name(self) -> str:
        """Get opponent's display name"""
        if self.opponent:
            return self.opponent.display_name or self.opponent.full_name
        return "Unknown"
    
    @hybrid_property
    def winner_name(self) -> Optional[str]:
        """Get winner's display name"""
        if self.winner:
            return self.winner.display_name or self.winner.full_name
        return None
    
    @hybrid_property
    def game_name(self) -> str:
        """Get display name of the game"""
        from src.models.game import GameType
        return GameType.get_display_name(self.game_type)
    
    @hybrid_property
    def status_display(self) -> str:
        """Get display name for status"""
        return MatchStatus.get_display_name(self.status)
    
    @hybrid_property
    def participants(self) -> List[int]:
        """Get list of participant user IDs"""
        return [self.challenger_id, self.opponent_id]
    
    @hybrid_property
    def has_both_scores(self) -> bool:
        """Check if both players have submitted scores"""
        return self.challenger_score is not None and self.opponent_score is not None
    
    @hybrid_property
    def time_remaining(self) -> Optional[str]:
        """Get time remaining before match expires"""
        if not self.expires_at or self.is_expired:
            return None
        remaining = self.expires_at - datetime.utcnow()
        if remaining.days > 0:
            return f"{remaining.days}d {remaining.seconds//3600}h"
        elif remaining.seconds > 3600:
            return f"{remaining.seconds//3600}h {(remaining.seconds%3600)//60}m"
        elif remaining.seconds > 60:
            return f"{remaining.seconds//60}m"
        else:
            return "Less than a minute"

    # ==================== Methods ====================
    
    def accept(self) -> None:
        """Accept the match challenge"""
        if self.status != MatchStatus.PENDING.value:
            raise ValueError(f"Cannot accept match with status: {self.status}")
        
        self.status = MatchStatus.ACCEPTED.value
        self.accepted_at = datetime.utcnow()
        # Set expiration for active match (1 hour)
        self.expires_at = datetime.utcnow() + timedelta(hours=1)
    
    def decline(self) -> None:
        """Decline the match challenge"""
        if self.status != MatchStatus.PENDING.value:
            raise ValueError(f"Cannot decline match with status: {self.status}")
        
        self.status = MatchStatus.DECLINED.value
        self.declined_at = datetime.utcnow()
        self.completed_at = datetime.utcnow()
        self.result = MatchResult.CANCELLED.value
    
    def cancel(self, reason: Optional[str] = None) -> None:
        """Cancel the match"""
        if self.status == MatchStatus.COMPLETED.value:
            raise ValueError("Cannot cancel a completed match")
        
        self.status = MatchStatus.CANCELLED.value
        self.completed_at = datetime.utcnow()
        self.result = MatchResult.CANCELLED.value
        
        if reason:
            if not self.metadata:
                self.metadata = {}
            self.metadata['cancel_reason'] = reason
    
    def start(self) -> None:
        """Start the match"""
        if self.status not in [MatchStatus.ACCEPTED.value, MatchStatus.PENDING.value]:
            raise ValueError(f"Cannot start match with status: {self.status}")
        
        self.status = MatchStatus.ACTIVE.value
        self.started_at = datetime.utcnow()
    
    def submit_score(self, user_id: int, score: int) -> None:
        """
        Submit a score for a participant
        
        Args:
            user_id: ID of the user submitting
            score: Score achieved
        """
        if self.status != MatchStatus.ACTIVE.value:
            raise ValueError(f"Match is not active (status: {self.status})")
        
        if self.is_expired:
            self.expire()
            raise ValueError("Match has expired")
        
        if user_id == self.challenger_id:
            self.challenger_score = score
        elif user_id == self.opponent_id:
            self.opponent_score = score
        else:
            raise ValueError("User is not a participant in this match")
    
    def determine_winner(self) -> Optional[int]:
        """
        Determine the winner of the match
        
        Returns:
            User ID of the winner, or None if tie
        """
        if self.challenger_score is None or self.opponent_score is None:
            return None
        
        if self.challenger_score > self.opponent_score:
            return self.challenger_id
        elif self.opponent_score > self.challenger_score:
            return self.opponent_id
        else:
            return None
    
    def complete_match(self) -> Dict[str, Any]:
        """
        Complete the match and determine winner
        
        Returns:
            Dictionary with match results
        """
        if self.status != MatchStatus.ACTIVE.value:
            raise ValueError(f"Cannot complete match with status: {self.status}")
        
        if not self.has_both_scores:
            # One player didn't submit - forfeit
            if self.challenger_score is None:
                self.result = MatchResult.OPPONENT_WON.value
                self.winner_id = self.opponent_id
                self.result_details = {"reason": "challenger_forfeit"}
            elif self.opponent_score is None:
                self.result = MatchResult.CHALLENGER_WON.value
                self.winner_id = self.challenger_id
                self.result_details = {"reason": "opponent_forfeit"}
        else:
            # Determine winner
            winner_id = self.determine_winner()
            self.winner_id = winner_id
            
            if winner_id == self.challenger_id:
                self.result = MatchResult.CHALLENGER_WON.value
            elif winner_id == self.opponent_id:
                self.result = MatchResult.OPPONENT_WON.value
            else:
                self.result = MatchResult.TIE.value
        
        self.status = MatchStatus.COMPLETED.value
        self.completed_at = datetime.utcnow()
        
        return {
            "winner_id": self.winner_id,
            "result": self.result,
            "challenger_score": self.challenger_score,
            "opponent_score": self.opponent_score,
            "is_tie": self.is_tie
        }
    
    def expire(self) -> None:
        """Mark match as expired"""
        if self.status == MatchStatus.COMPLETED.value:
            return
        
        self.status = MatchStatus.EXPIRED.value
        self.completed_at = datetime.utcnow()
        self.result = MatchResult.CANCELLED.value
    
    def forfeit(self, user_id: int) -> None:
        """
        Forfeit the match for a user
        
        Args:
            user_id: ID of the user forfeiting
        """
        if self.status != MatchStatus.ACTIVE.value:
            raise ValueError(f"Cannot forfeit match with status: {self.status}")
        
        if user_id not in self.participants:
            raise ValueError("User is not a participant in this match")
        
        if user_id == self.challenger_id:
            self.result = MatchResult.OPPONENT_WON.value
            self.winner_id = self.opponent_id
            self.challenger_score = 0
        else:
            self.result = MatchResult.CHALLENGER_WON.value
            self.winner_id = self.challenger_id
            self.opponent_score = 0
        
        self.status = MatchStatus.COMPLETED.value
        self.completed_at = datetime.utcnow()
        
        if not self.metadata:
            self.metadata = {}
        self.metadata['forfeit_user_id'] = user_id
    
    def is_participant(self, user_id: int) -> bool:
        """Check if a user is a participant in this match"""
        return user_id in self.participants
    
    def has_submitted(self, user_id: int) -> bool:
        """Check if a user has submitted a score"""
        if user_id == self.challenger_id:
            return self.challenger_score is not None
        elif user_id == self.opponent_id:
            return self.opponent_score is not None
        return False
    
    def get_score(self, user_id: int) -> Optional[int]:
        """Get score for a participant"""
        if user_id == self.challenger_id:
            return self.challenger_score
        elif user_id == self.opponent_id:
            return self.opponent_score
        return None
    
    def set_rewards(self, challenger_xp: int, challenger_points: int, 
                    opponent_xp: int, opponent_points: int) -> None:
        """Set rewards for both players"""
        self.challenger_xp_earned = challenger_xp
        self.challenger_points_earned = challenger_points
        self.opponent_xp_earned = opponent_xp
        self.opponent_points_earned = opponent_points
    
    def get_rewards(self, user_id: int) -> Dict[str, int]:
        """Get rewards for a user"""
        if user_id == self.challenger_id:
            return {
                "xp": self.challenger_xp_earned,
                "points": self.challenger_points_earned
            }
        elif user_id == self.opponent_id:
            return {
                "xp": self.opponent_xp_earned,
                "points": self.opponent_points_earned
            }
        return {"xp": 0, "points": 0}
    
    # ==================== Validation Methods ====================
    
    def validate_score(self, user_id: int, score: int) -> Dict[str, Any]:
        """Validate a submitted score"""
        validation = {
            "is_valid": True,
            "errors": [],
            "warnings": []
        }
        
        # Check if match is active
        if self.status != MatchStatus.ACTIVE.value:
            validation["is_valid"] = False
            validation["errors"].append(f"Match is not active (status: {self.status})")
        
        # Check if match is expired
        if self.is_expired:
            validation["is_valid"] = False
            validation["errors"].append("Match has expired")
        
        # Check if user is participant
        if not self.is_participant(user_id):
            validation["is_valid"] = False
            validation["errors"].append("User is not a participant in this match")
        
        # Check if user already submitted
        if self.has_submitted(user_id):
            validation["is_valid"] = False
            validation["errors"].append("User has already submitted a score")
        
        # Validate score range
        if score < 0:
            validation["is_valid"] = False
            validation["errors"].append("Score cannot be negative")
        
        if score > 10000:  # Max score
            validation["is_valid"] = False
            validation["errors"].append("Score exceeds maximum allowed")
        
        # Check if score is suspicious (anti-cheat)
        if score > 1000 and self.game_type == "reaction":
            validation["warnings"].append("Score seems unusually high for this game")
        
        return validation
    
    # ==================== Dictionary Methods ====================
    
    def to_dict(self, include_participants: bool = True, include_scores: bool = True) -> Dict[str, Any]:
        """Convert match to dictionary"""
        data = {
            "id": self.id,
            "match_id": self.match_id,
            "game_type": self.game_type,
            "game_name": self.game_name,
            "match_type": self.match_type,
            "status": self.status,
            "status_display": self.status_display,
            "wager_points": self.wager_points,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "accepted_at": self.accepted_at.isoformat() if self.accepted_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "time_remaining": self.time_remaining,
            "is_expired": self.is_expired,
            "is_tie": self.is_tie,
        }
        
        if include_scores:
            data.update({
                "challenger_score": self.challenger_score,
                "opponent_score": self.opponent_score,
                "result": self.result,
                "winner_name": self.winner_name,
            })
            
            # Add rewards
            if self.is_completed:
                data["challenger_rewards"] = {
                    "xp": self.challenger_xp_earned,
                    "points": self.challenger_points_earned
                }
                data["opponent_rewards"] = {
                    "xp": self.opponent_xp_earned,
                    "points": self.opponent_points_earned
                }
        
        if include_participants:
            data["challenger"] = {
                "id": self.challenger_id,
                "name": self.challenger_name,
                "has_submitted": self.has_submitted(self.challenger_id)
            }
            data["opponent"] = {
                "id": self.opponent_id,
                "name": self.opponent_name,
                "has_submitted": self.has_submitted(self.opponent_id)
            }
            if self.winner:
                data["winner"] = {
                    "id": self.winner.id,
                    "name": self.winner_name
                }
        
        return data
    
    def to_summary(self) -> Dict[str, Any]:
        """Get a summary of the match for display"""
        summary = {
            "match_id": self.match_id,
            "game": self.game_name,
            "status": self.status_display,
            "challenger": self.challenger_name,
            "opponent": self.opponent_name,
        }
        
        if self.is_completed:
            if self.is_tie:
                summary["result"] = "🤝 It's a tie!"
            elif self.winner:
                summary["result"] = f"🏆 {self.winner_name} wins!"
            summary["scores"] = f"{self.challenger_score} - {self.opponent_score}"
        
        if self.is_pending:
            summary["action_needed"] = "Accept the challenge!"
        
        return summary
    
    def __repr__(self) -> str:
        return f"<FriendMatch(id={self.id}, match_id={self.match_id}, challenger_id={self.challenger_id}, opponent_id={self.opponent_id}, status={self.status})>"


# ==================== Match Invite Model ====================
class MatchInvite(Base):
    """Track match invites sent to users"""
    
    __tablename__ = "match_invites"
    __table_args__ = (
        Index("idx_match_invites_sender", "sender_id"),
        Index("idx_match_invites_receiver", "receiver_id"),
        Index("idx_match_invites_status", "status"),
        Index("idx_match_invites_match", "match_id"),
        Index("idx_match_invites_created_at", "created_at"),
        UniqueConstraint('match_id', 'receiver_id', name='uq_match_invite'),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    invite_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    
    # Relations
    match_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("friend_matches.id", ondelete="CASCADE"), nullable=False)
    sender_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    receiver_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    
    # Message
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Metadata
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    match: Mapped["FriendMatch"] = relationship("FriendMatch", backref="invites")
    sender: Mapped["User"] = relationship("User", foreign_keys=[sender_id])
    receiver: Mapped["User"] = relationship("User", foreign_keys=[receiver_id])

    def __init__(self, **kwargs):
        if 'invite_id' not in kwargs or not kwargs['invite_id']:
            kwargs['invite_id'] = self._generate_invite_id()
        super().__init__(**kwargs)

    @staticmethod
    def _generate_invite_id() -> str:
        """Generate unique invite ID"""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        random_part = uuid.uuid4().hex[:8].upper()
        return f"INVITE{timestamp}{random_part}"

    def accept(self) -> None:
        """Accept the invite"""
        self.status = "accepted"
        self.responded_at = datetime.utcnow()
    
    def decline(self) -> None:
        """Decline the invite"""
        self.status = "declined"
        self.responded_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "invite_id": self.invite_id,
            "match_id": self.match_id,
            "sender_id": self.sender_id,
            "receiver_id": self.receiver_id,
            "status": self.status,
            "message": self.message,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "responded_at": self.responded_at.isoformat() if self.responded_at else None,
        }
    
    def __repr__(self) -> str:
        return f"<MatchInvite(id={self.id}, invite_id={self.invite_id}, match_id={self.match_id}, status={self.status})>"


# ==================== Match Stats Model ====================
class MatchStats(Base):
    """Aggregated match statistics for users"""
    
    __tablename__ = "match_stats"
    __table_args__ = (
        Index("idx_match_stats_user", "user_id"),
        Index("idx_match_stats_game_type", "game_type"),
        Index("idx_match_stats_period", "period"),
        Index("idx_match_stats_user_game", "user_id", "game_type"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    game_type: Mapped[str] = mapped_column(String(50), nullable=False)
    period: Mapped[str] = mapped_column(String(20), default="all_time", nullable=False)  # all_time, weekly, monthly
    
    # Stats
    matches_played: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matches_won: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matches_lost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matches_tied: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Scoring
    total_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    highest_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lowest_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Streaks
    current_win_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    longest_win_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Metadata
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", backref="match_stats")

    @hybrid_property
    def win_rate(self) -> float:
        """Calculate win rate as percentage"""
        if self.matches_played == 0:
            return 0.0
        return (self.matches_won / self.matches_played) * 100
    
    @hybrid_property
    def total_matches(self) -> int:
        """Get total matches played"""
        return self.matches_played
    
    def update_stats(self, result: str, score: int) -> None:
        """Update stats with a new match result"""
        self.matches_played += 1
        self.total_score += score
        
        # Update average
        self.average_score = self.total_score / self.matches_played
        
        # Update high/low scores
        if score > self.highest_score:
            self.highest_score = score
        if self.lowest_score == 0 or score < self.lowest_score:
            self.lowest_score = score
        
        # Update win/loss/tie counts and streaks
        if result == MatchResult.CHALLENGER_WON.value or result == MatchResult.OPPONENT_WON.value:
            self.matches_won += 1
            self.current_win_streak += 1
            if self.current_win_streak > self.longest_win_streak:
                self.longest_win_streak = self.current_win_streak
        elif result == MatchResult.TIE.value:
            self.matches_tied += 1
            self.current_win_streak = 0
        else:
            self.matches_lost += 1
            self.current_win_streak = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "game_type": self.game_type,
            "period": self.period,
            "matches_played": self.matches_played,
            "matches_won": self.matches_won,
            "matches_lost": self.matches_lost,
            "matches_tied": self.matches_tied,
            "win_rate": self.win_rate,
            "total_score": self.total_score,
            "average_score": self.average_score,
            "highest_score": self.highest_score,
            "lowest_score": self.lowest_score,
            "current_win_streak": self.current_win_streak,
            "longest_win_streak": self.longest_win_streak,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    
    def __repr__(self) -> str:
        return f"<MatchStats(id={self.id}, user_id={self.user_id}, game_type={self.game_type}, period={self.period})>"


# ==================== Model Registration ====================
__all__ = [
    "MatchStatus",
    "MatchType",
    "MatchResult",
    "FriendMatch",
    "MatchInvite",
    "MatchStats",
]
