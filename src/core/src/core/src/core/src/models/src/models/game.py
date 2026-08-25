"""
Game models for GamePulse Bot
Includes GameSession, FriendMatch, and related models
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    Column, BigInteger, String, Integer, Boolean, DateTime, 
    JSON, ForeignKey, Text, Float, Index, UniqueConstraint,
    func, Enum as SQLEnum
)
from sqlalchemy.orm import relationship, Mapped, mapped_column, backref
from sqlalchemy.ext.hybrid import hybrid_property, hybrid_method
import uuid
import enum

from src.core.database import Base, TimestampMixin


# ==================== Enums ====================
class GameType(str, enum.Enum):
    """Available game types"""
    REACTION = "reaction"
    QUIZ = "quiz"
    NUMBER_RUSH = "number_rush"
    MEMORY = "memory"
    TAP = "tap"
    
    @classmethod
    def list(cls) -> List[str]:
        return [game.value for game in cls]
    
    @classmethod
    def get_display_name(cls, game_type: str) -> str:
        """Get display name for game type"""
        names = {
            "reaction": "Reaction Challenge",
            "quiz": "Quick Quiz",
            "number_rush": "Number Rush",
            "memory": "Memory Challenge",
            "tap": "Tap Challenge"
        }
        return names.get(game_type, game_type.title())


class MatchStatus(str, enum.Enum):
    """Friend match status"""
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class GameSessionStatus(str, enum.Enum):
    """Game session status"""
    CREATED = "created"
    STARTED = "started"
    COMPLETED = "completed"
    EXPIRED = "expired"
    INVALID = "invalid"


# ==================== Game Session Model ====================
class GameSession(Base):
    """Model for tracking individual game sessions"""
    
    __tablename__ = "game_sessions"
    __table_args__ = (
        Index("idx_game_sessions_user_id", "user_id"),
        Index("idx_game_sessions_game_type", "game_type"),
        Index("idx_game_sessions_session_id", "session_id"),
        Index("idx_game_sessions_status", "status"),
        Index("idx_game_sessions_started_at", "started_at"),
        Index("idx_game_sessions_completed_at", "completed_at"),
        Index("idx_game_sessions_user_game", "user_id", "game_type"),
        Index("idx_game_sessions_valid_sessions", "user_id", "game_type", "is_valid"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    game_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default=GameSessionStatus.CREATED.value, nullable=False)
    
    # Score and rewards
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    xp_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    points_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # in seconds
    
    # Game data
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    game_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Validation
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_suspicious: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    validation_checks: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Timestamps
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="game_sessions")

    def __init__(self, **kwargs):
        if 'session_id' not in kwargs or not kwargs['session_id']:
            kwargs['session_id'] = self._generate_session_id()
        if 'status' not in kwargs:
            kwargs['status'] = GameSessionStatus.CREATED.value
        super().__init__(**kwargs)

    # ==================== Properties ====================
    
    @staticmethod
    def _generate_session_id() -> str:
        """Generate unique session ID"""
        return f"gs_{uuid.uuid4().hex[:16]}"
    
    @hybrid_property
    def is_completed(self) -> bool:
        """Check if session is completed"""
        return self.status == GameSessionStatus.COMPLETED.value
    
    @hybrid_property
    def is_expired(self) -> bool:
        """Check if session is expired"""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        if self.started_at:
            # Default 5-minute timeout
            return (datetime.utcnow() - self.started_at).seconds > 300
        return False
    
    @hybrid_property
    def is_active(self) -> bool:
        """Check if session is active"""
        return self.status in [GameSessionStatus.CREATED.value, GameSessionStatus.STARTED.value] and not self.is_expired
    
    @hybrid_property
    def performance_rating(self) -> str:
        """Get performance rating based on score"""
        if self.score == 0:
            return "No Score"
        elif self.score >= 90:
            return "Legendary"
        elif self.score >= 75:
            return "Excellent"
        elif self.score >= 50:
            return "Good"
        elif self.score >= 25:
            return "Fair"
        else:
            return "Needs Practice"
    
    @hybrid_property
    def game_name(self) -> str:
        """Get display name of the game"""
        return GameType.get_display_name(self.game_type)

    # ==================== Methods ====================
    
    def start(self) -> None:
        """Mark session as started"""
        self.status = GameSessionStatus.STARTED.value
        self.started_at = datetime.utcnow()
        # Set default expiration (5 minutes)
        if not self.expires_at:
            self.expires_at = datetime.utcnow() + timedelta(seconds=300)
    
    def complete(
        self, 
        score: int, 
        xp: int, 
        points: int, 
        duration: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Complete the game session
        
        Args:
            score: Final score
            xp: XP earned
            points: Pulse Points earned
            duration: Duration in seconds
            metadata: Additional metadata
        """
        self.score = score
        self.xp_earned = xp
        self.points_earned = points
        self.duration = duration
        self.status = GameSessionStatus.COMPLETED.value
        self.completed_at = datetime.utcnow()
        
        if metadata:
            if self.metadata:
                self.metadata.update(metadata)
            else:
                self.metadata = metadata
    
    def invalidate(self, reason: str) -> None:
        """Invalidate the session"""
        self.is_valid = False
        self.status = GameSessionStatus.INVALID.value
        if not self.metadata:
            self.metadata = {}
        self.metadata['invalid_reason'] = reason
        self.completed_at = datetime.utcnow()
    
    def mark_suspicious(self, checks: Dict[str, Any]) -> None:
        """Mark session as suspicious"""
        self.is_suspicious = True
        self.validation_checks = checks
        self.is_valid = False
        self.status = GameSessionStatus.INVALID.value
    
    def add_validation_check(self, check_name: str, result: Any) -> None:
        """Add a validation check result"""
        if not self.validation_checks:
            self.validation_checks = {}
        self.validation_checks[check_name] = result
    
    def to_dict(self, include_user: bool = False) -> Dict[str, Any]:
        """Convert session to dictionary"""
        data = {
            "id": self.id,
            "session_id": self.session_id,
            "game_type": self.game_type,
            "game_name": self.game_name,
            "status": self.status,
            "score": self.score,
            "xp_earned": self.xp_earned,
            "points_earned": self.points_earned,
            "duration": self.duration,
            "performance_rating": self.performance_rating,
            "is_valid": self.is_valid,
            "is_suspicious": self.is_suspicious,
            "metadata": self.metadata,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
        
        if include_user and self.user:
            data["user"] = {
                "id": self.user.id,
                "telegram_id": self.user.telegram_id,
                "username": self.user.username,
                "display_name": self.user.display_name,
            }
        
        return data
    
    def __repr__(self) -> str:
        return f"<GameSession(id={self.id}, session_id={self.session_id}, game_type={self.game_type}, status={self.status})>"


# ==================== Friend Match Model ====================
class FriendMatch(Base):
    """Model for friend challenges/matches"""
    
    __tablename__ = "friend_matches"
    __table_args__ = (
        Index("idx_friend_matches_challenger", "challenger_id"),
        Index("idx_friend_matches_opponent", "opponent_id"),
        Index("idx_friend_matches_status", "status"),
        Index("idx_friend_matches_expires_at", "expires_at"),
        Index("idx_friend_matches_created_at", "created_at"),
        Index("idx_friend_matches_game_type", "game_type"),
        Index("idx_friend_matches_completed", "status", "completed_at"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    challenger_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    opponent_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    game_type: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Session tracking
    session_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True)
    challenger_session_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    opponent_session_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Scores
    challenger_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    opponent_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    winner_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default=MatchStatus.PENDING.value, nullable=False)
    
    # Match data
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    declined_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    challenger: Mapped["User"] = relationship("User", foreign_keys=[challenger_id], back_populates="friend_matches_challenger")
    opponent: Mapped["User"] = relationship("User", foreign_keys=[opponent_id], back_populates="friend_matches_opponent")
    winner: Mapped[Optional["User"]] = relationship("User", foreign_keys=[winner_id], back_populates="friend_matches_winner")

    def __init__(self, **kwargs):
        if 'status' not in kwargs:
            kwargs['status'] = MatchStatus.PENDING.value
        if 'session_id' not in kwargs or not kwargs['session_id']:
            kwargs['session_id'] = self._generate_match_id()
        super().__init__(**kwargs)

    # ==================== Properties ====================
    
    @staticmethod
    def _generate_match_id() -> str:
        """Generate unique match ID"""
        return f"fm_{uuid.uuid4().hex[:12]}"
    
    @hybrid_property
    def is_pending(self) -> bool:
        """Check if match is pending"""
        return self.status == MatchStatus.PENDING.value
    
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
        # Default 24-hour expiration
        return (datetime.utcnow() - self.created_at).days >= 1
    
    @hybrid_property
    def is_tie(self) -> bool:
        """Check if match ended in a tie"""
        if not self.is_completed:
            return False
        if self.challenger_score is None or self.opponent_score is None:
            return False
        return self.challenger_score == self.opponent_score
    
    @hybrid_property
    def winner_name(self) -> Optional[str]:
        """Get winner's display name"""
        if self.winner:
            return self.winner.display_name or self.winner.full_name
        return None
    
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
    def game_name(self) -> str:
        """Get display name of the game"""
        return GameType.get_display_name(self.game_type)
    
    @hybrid_property
    def participants(self) -> List[int]:
        """Get list of participant user IDs"""
        return [self.challenger_id, self.opponent_id]

    # ==================== Methods ====================
    
    def accept(self) -> None:
        """Accept the match challenge"""
        self.status = MatchStatus.ACTIVE.value
        self.accepted_at = datetime.utcnow()
        # Set expiration (1 hour for active match)
        self.expires_at = datetime.utcnow() + timedelta(hours=1)
    
    def decline(self) -> None:
        """Decline the match challenge"""
        self.status = MatchStatus.CANCELLED.value
        self.declined_at = datetime.utcnow()
        self.completed_at = datetime.utcnow()
    
    def cancel(self) -> None:
        """Cancel the match"""
        self.status = MatchStatus.CANCELLED.value
        self.completed_at = datetime.utcnow()
    
    def expire(self) -> None:
        """Mark match as expired"""
        self.status = MatchStatus.EXPIRED.value
        self.completed_at = datetime.utcnow()
    
    def submit_score(self, user_id: int, score: int) -> None:
        """
        Submit a score for a participant
        
        Args:
            user_id: ID of the user submitting
            score: Score achieved
        """
        if self.status != MatchStatus.ACTIVE.value:
            raise ValueError(f"Match is not active (status: {self.status})")
        
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
    
    def complete_match(self) -> None:
        """Complete the match and determine winner"""
        if self.status != MatchStatus.ACTIVE.value:
            raise ValueError(f"Cannot complete match with status: {self.status}")
        
        self.winner_id = self.determine_winner()
        self.status = MatchStatus.COMPLETED.value
        self.completed_at = datetime.utcnow()
    
    def is_participant(self, user_id: int) -> bool:
        """Check if a user is a participant in this match"""
        return user_id in [self.challenger_id, self.opponent_id]
    
    def has_submitted(self, user_id: int) -> bool:
        """Check if a user has submitted a score"""
        if user_id == self.challenger_id:
            return self.challenger_score is not None
        elif user_id == self.opponent_id:
            return self.opponent_score is not None
        return False
    
    def to_dict(self, include_participants: bool = True) -> Dict[str, Any]:
        """Convert match to dictionary"""
        data = {
            "id": self.id,
            "match_id": self.session_id,
            "game_type": self.game_type,
            "game_name": self.game_name,
            "status": self.status,
            "challenger_score": self.challenger_score,
            "opponent_score": self.opponent_score,
            "is_tie": self.is_tie,
            "winner_name": self.winner_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "accepted_at": self.accepted_at.isoformat() if self.accepted_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": self.metadata,
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
    
    def __repr__(self) -> str:
        return f"<FriendMatch(id={self.id}, challenger_id={self.challenger_id}, opponent_id={self.opponent_id}, status={self.status})>"


# ==================== Game Leaderboard Entry Model ====================
class GameLeaderboardEntry(Base):
    """Model for game-specific leaderboard entries"""
    
    __tablename__ = "game_leaderboard_entries"
    __table_args__ = (
        Index("idx_game_leaderboard_game_user", "game_type", "user_id"),
        Index("idx_game_leaderboard_score", "score"),
        Index("idx_game_leaderboard_period", "period"),
        Index("idx_game_leaderboard_date", "entry_date"),
        UniqueConstraint('game_type', 'user_id', 'period', 'entry_date', 
                        name='uq_game_leaderboard_entry'),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    game_type: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[str] = mapped_column(String(20), default="all_time", nullable=False)  # all_time, weekly, monthly
    entry_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", backref="leaderboard_entries")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "game_type": self.game_type,
            "score": self.score,
            "period": self.period,
            "entry_date": self.entry_date.isoformat() if self.entry_date else None,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<GameLeaderboardEntry(id={self.id}, game_type={self.game_type}, user_id={self.user_id}, score={self.score})>"


# ==================== Game Stats Model ====================
class GameStats(Base):
    """Aggregated game statistics for analytics"""
    
    __tablename__ = "game_stats"
    __table_args__ = (
        Index("idx_game_stats_game_type", "game_type"),
        Index("idx_game_stats_date", "stat_date"),
        Index("idx_game_stats_game_date", "game_type", "stat_date"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    game_type: Mapped[str] = mapped_column(String(50), nullable=False)
    stat_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Counts
    total_sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_players: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_scores: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Averages
    avg_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_duration: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_xp: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_points: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    
    # High scores
    high_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    high_score_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    
    # Distribution
    score_distribution: Mapped[Optional[Dict[str, int]]] = mapped_column(JSON, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    high_score_user: Mapped[Optional["User"]] = relationship("User", backref="game_stats_high_scores")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "game_type": self.game_type,
            "stat_date": self.stat_date.isoformat() if self.stat_date else None,
            "total_sessions": self.total_sessions,
            "total_players": self.total_players,
            "total_scores": self.total_scores,
            "avg_score": self.avg_score,
            "avg_duration": self.avg_duration,
            "avg_xp": self.avg_xp,
            "avg_points": self.avg_points,
            "high_score": self.high_score,
            "high_score_user_id": self.high_score_user_id,
            "score_distribution": self.score_distribution,
        }

    def __repr__(self) -> str:
        return f"<GameStats(id={self.id}, game_type={self.game_type}, stat_date={self.stat_date})>"


# ==================== Model Registration ====================
__all__ = [
    "GameType",
    "MatchStatus",
    "GameSessionStatus",
    "GameSession",
    "FriendMatch",
    "GameLeaderboardEntry",
    "GameStats",
]
