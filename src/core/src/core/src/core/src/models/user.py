"""
User models for GamePulse Bot
Includes User, UserStats, BestScore, PointTransaction, and related models
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    Column, BigInteger, String, Integer, Boolean, DateTime, 
    JSON, ForeignKey, Text, Float, Index, UniqueConstraint,
    func, Table
)
from sqlalchemy.orm import relationship, Mapped, mapped_column, backref
from sqlalchemy.ext.hybrid import hybrid_property, hybrid_method
import secrets
import string

from src.core.database import Base, TimestampMixin, SoftDeleteMixin


# ==================== User Model ====================
class User(Base, TimestampMixin):
    """Main user model for GamePulse"""
    
    __tablename__ = "users"
    __table_args__ = (
        Index("idx_users_telegram_id", "telegram_id"),
        Index("idx_users_username", "username"),
        Index("idx_users_level", "level"),
        Index("idx_users_pulse_points", "pulse_points"),
        Index("idx_users_referral_code", "referral_code"),
        Index("idx_users_is_active", "is_active"),
        Index("idx_users_last_active", "last_active_at"),
        {"sqlite_autoincrement": True},
    )

    # Primary identifiers
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Progression
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pulse_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    
    # Stats
    games_played: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    games_won: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    
    # Streaks
    current_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_activity_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Referrals
    referral_code: Mapped[Optional[str]] = mapped_column(String(20), unique=True, nullable=True, index=True)
    referred_by_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True, index=True)
    referral_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    referral_points_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ban_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    banned_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    banned_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    
    # Preferences
    settings: Mapped[Dict[str, Any]] = mapped_column(JSON, default={
        "notifications": True,
        "language": "en",
        "timezone": "UTC",
        "privacy": {
            "show_username": True,
            "show_avatar": True,
            "show_stats": True
        }
    }, nullable=False)
    
    # Timestamps
    registered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_active_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_game_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relationships
    referred_by: Mapped[Optional["User"]] = relationship(
        "User", 
        remote_side=[id], 
        backref=backref("referrals_list", lazy="dynamic")
    )
    
    game_sessions = relationship(
        "GameSession", 
        back_populates="user", 
        cascade="all, delete-orphan",
        lazy="dynamic"
    )
    
    best_scores = relationship(
        "BestScore", 
        back_populates="user", 
        cascade="all, delete-orphan",
        lazy="dynamic"
    )
    
    achievements = relationship(
        "UserAchievement", 
        back_populates="user", 
        cascade="all, delete-orphan",
        lazy="dynamic"
    )
    
    point_transactions = relationship(
        "PointTransaction", 
        back_populates="user", 
        cascade="all, delete-orphan",
        lazy="dynamic"
    )
    
    notifications = relationship(
        "Notification", 
        back_populates="user", 
        cascade="all, delete-orphan",
        lazy="dynamic"
    )
    
    friend_matches_challenger = relationship(
        "FriendMatch",
        foreign_keys="FriendMatch.challenger_id",
        back_populates="challenger",
        lazy="dynamic"
    )
    
    friend_matches_opponent = relationship(
        "FriendMatch",
        foreign_keys="FriendMatch.opponent_id",
        back_populates="opponent",
        lazy="dynamic"
    )
    
    friend_matches_winner = relationship(
        "FriendMatch",
        foreign_keys="FriendMatch.winner_id",
        back_populates="winner",
        lazy="dynamic"
    )
    
    daily_challenges = relationship(
        "DailyChallengeCompletion",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="dynamic"
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.referral_code:
            self.referral_code = self._generate_referral_code()
        if not self.display_name:
            self.display_name = self._generate_display_name()

    # ==================== Properties ====================
    
    @hybrid_property
    def full_name(self) -> str:
        """Get user's full name"""
        if self.display_name:
            return self.display_name
        if self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name
    
    @full_name.expression
    def full_name(cls):
        """SQL expression for full_name"""
        return func.coalesce(
            cls.display_name,
            func.concat(cls.first_name, ' ', cls.last_name),
            cls.first_name
        )
    
    @hybrid_property
    def xp_to_next_level(self) -> int:
        """XP needed to reach next level"""
        return self.level * 100  # Configurable: XP_PER_LEVEL * level
    
    @xp_to_next_level.expression
    def xp_to_next_level(cls):
        """SQL expression for xp_to_next_level"""
        return cls.level * 100
    
    @hybrid_property
    def level_progress(self) -> float:
        """Progress to next level as percentage"""
        xp_for_current = (self.level - 1) * 100
        xp_for_next = self.level * 100
        if xp_for_next == xp_for_current:
            return 100.0
        progress = (self.xp - xp_for_current) / (xp_for_next - xp_for_current) * 100
        return min(100.0, max(0.0, progress))
    
    @hybrid_property
    def is_online(self) -> bool:
        """Check if user is currently online"""
        if not self.last_active_at:
            return False
        return (datetime.utcnow() - self.last_active_at) < timedelta(minutes=5)
    
    @hybrid_property
    def win_rate(self) -> float:
        """Calculate win rate as percentage"""
        if self.games_played == 0:
            return 0.0
        return (self.games_won / self.games_played) * 100
    
    @hybrid_property
    def days_since_registered(self) -> int:
        """Days since user registered"""
        return (datetime.utcnow() - self.registered_at).days
    
    @hybrid_property
    def is_streak_active(self) -> bool:
        """Check if streak is active today"""
        if not self.last_activity_date:
            return False
        return self.last_activity_date.date() >= datetime.utcnow().date()
    
    @hybrid_property
    def should_reset_streak(self) -> bool:
        """Check if streak should be reset"""
        if not self.last_activity_date:
            return True
        days_since_activity = (datetime.utcnow() - self.last_activity_date).days
        return days_since_activity > 1
    
    @hybrid_property
    def referral_link(self) -> str:
        """Generate referral link"""
        return f"https://t.me/GamePulseBot?start=ref_{self.referral_code}"

    # ==================== Methods ====================
    
    @staticmethod
    def _generate_referral_code(length: int = 8) -> str:
        """Generate a unique referral code"""
        alphabet = string.ascii_uppercase + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    def _generate_display_name(self) -> str:
        """Generate display name from first and last name"""
        if self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name
    
    def add_xp(self, amount: int) -> int:
        """
        Add XP and handle level ups
        
        Returns:
            Number of levels gained
        """
        old_level = self.level
        self.xp += amount
        
        # Check for level ups
        levels_gained = 0
        while self.xp >= self.xp_to_next_level:
            self.level += 1
            levels_gained += 1
        
        return levels_gained
    
    def add_points(self, amount: int) -> None:
        """Add Pulse Points"""
        self.pulse_points += amount
    
    def add_game(self, won: bool = False) -> None:
        """Record a game played"""
        self.games_played += 1
        if won:
            self.games_won += 1
    
    def update_streak(self) -> bool:
        """
        Update daily streak
        
        Returns:
            True if streak was updated, False if streak was reset
        """
        today = datetime.utcnow().date()
        
        if not self.last_activity_date:
            # First activity
            self.current_streak = 1
            self.last_activity_date = datetime.utcnow()
            return True
        
        last_date = self.last_activity_date.date()
        
        if last_date == today:
            # Already active today
            return True
        
        if last_date == today - timedelta(days=1):
            # Consecutive day
            self.current_streak += 1
            if self.current_streak > self.longest_streak:
                self.longest_streak = self.current_streak
            self.last_activity_date = datetime.utcnow()
            return True
        
        # Streak broken
        self.current_streak = 0
        self.last_activity_date = datetime.utcnow()
        return False
    
    def get_streak_bonus(self) -> Dict[str, Any]:
        """
        Calculate streak bonus if any
        
        Returns:
            Dictionary with bonus details
        """
        bonus_points = 0
        bonus_xp = 0
        message = None
        
        # Milestone bonuses
        if self.current_streak % 7 == 0 and self.current_streak > 0:
            bonus_points = 50
            bonus_xp = 25
            message = f"🎉 Weekly streak milestone! {self.current_streak} days!"
        
        elif self.current_streak % 30 == 0 and self.current_streak > 0:
            bonus_points = 200
            bonus_xp = 100
            message = f"🎉 Monthly streak milestone! {self.current_streak} days!"
        
        elif self.current_streak % 365 == 0 and self.current_streak > 0:
            bonus_points = 1000
            bonus_xp = 500
            message = f"🎉 Yearly streak milestone! {self.current_streak} days!"
        
        return {
            "points": bonus_points,
            "xp": bonus_xp,
            "message": message,
            "current_streak": self.current_streak,
            "longest_streak": self.longest_streak
        }
    
    def update_settings(self, settings_update: Dict[str, Any]) -> None:
        """Update user settings"""
        if not self.settings:
            self.settings = {}
        self.settings.update(settings_update)
    
    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Convert user to dictionary"""
        data = {
            "id": self.id,
            "telegram_id": self.telegram_id,
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "display_name": self.display_name,
            "full_name": self.full_name,
            "level": self.level,
            "xp": self.xp,
            "xp_to_next_level": self.xp_to_next_level,
            "level_progress": self.level_progress,
            "pulse_points": self.pulse_points,
            "games_played": self.games_played,
            "games_won": self.games_won,
            "win_rate": self.win_rate,
            "current_streak": self.current_streak,
            "longest_streak": self.longest_streak,
            "registered_at": self.registered_at.isoformat() if self.registered_at else None,
            "last_active_at": self.last_active_at.isoformat() if self.last_active_at else None,
            "is_active": self.is_active,
            "is_admin": self.is_admin,
            "is_banned": self.is_banned,
            "is_verified": self.is_verified,
            "referral_code": self.referral_code,
            "referral_count": self.referral_count,
            "referral_link": self.referral_link,
        }
        
        if include_sensitive:
            data.update({
                "settings": self.settings,
                "ban_reason": self.ban_reason,
                "banned_at": self.banned_at.isoformat() if self.banned_at else None,
            })
        
        return data
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, username={self.username})>"


# ==================== Best Score Model ====================
class BestScore(Base):
    """User's best scores for each game"""
    
    __tablename__ = "best_scores"
    __table_args__ = (
        Index("idx_best_scores_user_game", "user_id", "game_type"),
        Index("idx_best_scores_score", "score"),
        UniqueConstraint('user_id', 'game_type', name='uq_best_scores_user_game'),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    game_type: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    achieved_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="best_scores")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "game_type": self.game_type,
            "score": self.score,
            "metadata": self.metadata,
            "achieved_at": self.achieved_at.isoformat() if self.achieved_at else None,
        }

    def __repr__(self) -> str:
        return f"<BestScore(id={self.id}, user_id={self.user_id}, game_type={self.game_type}, score={self.score})>"


# ==================== Point Transaction Model ====================
class PointTransaction(Base):
    """Audit trail for all point transactions"""
    
    __tablename__ = "point_transactions"
    __table_args__ = (
        Index("idx_point_transactions_user_id", "user_id"),
        Index("idx_point_transactions_type", "transaction_type"),
        Index("idx_point_transactions_created_at", "created_at"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False)
    reference_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="point_transactions")

    @classmethod
    def create_game_reward(
        cls,
        user_id: int,
        amount: int,
        session_id: int,
        description: Optional[str] = None
    ) -> "PointTransaction":
        """Create a game reward transaction"""
        return cls(
            user_id=user_id,
            amount=amount,
            transaction_type="game_reward",
            reference_type="game_session",
            reference_id=session_id,
            description=description or f"Game reward: {amount} points"
        )

    @classmethod
    def create_challenge_reward(
        cls,
        user_id: int,
        amount: int,
        challenge_id: int,
        description: Optional[str] = None
    ) -> "PointTransaction":
        """Create a challenge reward transaction"""
        return cls(
            user_id=user_id,
            amount=amount,
            transaction_type="challenge_reward",
            reference_type="daily_challenge",
            reference_id=challenge_id,
            description=description or f"Daily challenge reward: {amount} points"
        )

    @classmethod
    def create_achievement_reward(
        cls,
        user_id: int,
        amount: int,
        achievement_id: int,
        description: Optional[str] = None
    ) -> "PointTransaction":
        """Create an achievement reward transaction"""
        return cls(
            user_id=user_id,
            amount=amount,
            transaction_type="achievement",
            reference_type="achievement",
            reference_id=achievement_id,
            description=description or f"Achievement reward: {amount} points"
        )

    @classmethod
    def create_referral_reward(
        cls,
        user_id: int,
        amount: int,
        referred_user_id: int,
        description: Optional[str] = None
    ) -> "PointTransaction":
        """Create a referral reward transaction"""
        return cls(
            user_id=user_id,
            amount=amount,
            transaction_type="referral",
            reference_type="user",
            reference_id=referred_user_id,
            description=description or f"Referral reward: {amount} points"
        )

    @classmethod
    def create_streak_bonus(
        cls,
        user_id: int,
        amount: int,
        streak_days: int,
        description: Optional[str] = None
    ) -> "PointTransaction":
        """Create a streak bonus transaction"""
        return cls(
            user_id=user_id,
            amount=amount,
            transaction_type="streak_bonus",
            reference_type="streak",
            reference_id=streak_days,
            description=description or f"Streak bonus: {amount} points for {streak_days} days"
        )

    @classmethod
    def create_level_up(
        cls,
        user_id: int,
        amount: int,
        level: int,
        description: Optional[str] = None
    ) -> "PointTransaction":
        """Create a level up transaction"""
        return cls(
            user_id=user_id,
            amount=amount,
            transaction_type="level_up",
            reference_type="level",
            reference_id=level,
            description=description or f"Level up bonus: {amount} points for reaching level {level}"
        )

    @classmethod
    def create_friend_match(
        cls,
        user_id: int,
        amount: int,
        match_id: int,
        description: Optional[str] = None
    ) -> "PointTransaction":
        """Create a friend match transaction"""
        return cls(
            user_id=user_id,
            amount=amount,
            transaction_type="friend_match",
            reference_type="friend_match",
            reference_id=match_id,
            description=description or f"Friend match reward: {amount} points"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "amount": self.amount,
            "transaction_type": self.transaction_type,
            "reference_type": self.reference_type,
            "reference_id": self.reference_id,
            "description": self.description,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<PointTransaction(id={self.id}, user_id={self.user_id}, amount={self.amount}, type={self.transaction_type})>"


# ==================== Notification Model ====================
class Notification(Base):
    """User notifications"""
    
    __tablename__ = "notifications"
    __table_args__ = (
        Index("idx_notifications_user_id", "user_id"),
        Index("idx_notifications_is_read", "is_read"),
        Index("idx_notifications_created_at", "created_at"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="notifications")

    def mark_as_read(self) -> None:
        """Mark notification as read"""
        self.is_read = True
        self.read_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "title": self.title,
            "message": self.message,
            "data": self.data,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None,
        }

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, user_id={self.user_id}, type={self.type})>"


# ==================== User Activity Log Model ====================
class UserActivityLog(Base):
    """Log of user activities for analytics"""
    
    __tablename__ = "user_activity_logs"
    __table_args__ = (
        Index("idx_user_activity_user_id", "user_id"),
        Index("idx_user_activity_action", "action"),
        Index("idx_user_activity_created_at", "created_at"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    user: Mapped["User"] = relationship("User", backref="activity_logs")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<UserActivityLog(id={self.id}, user_id={self.user_id}, action={self.action})>"


# ==================== User Referral Model ====================
class UserReferral(Base):
    """Track user referrals"""
    
    __tablename__ = "user_referrals"
    __table_args__ = (
        Index("idx_user_referrals_referrer", "referrer_id"),
        Index("idx_user_referrals_referred", "referred_id"),
        Index("idx_user_referrals_status", "status"),
        UniqueConstraint('referred_id', name='uq_user_referrals_referred'),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    referrer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    referred_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    referral_code: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)  # pending, rewarded, expired
    reward_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reward_xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rewarded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    referrer: Mapped["User"] = relationship("User", foreign_keys=[referrer_id])
    referred: Mapped["User"] = relationship("User", foreign_keys=[referred_id])

    def mark_rewarded(self) -> None:
        """Mark referral as rewarded"""
        self.status = "rewarded"
        self.rewarded_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "referrer_id": self.referrer_id,
            "referred_id": self.referred_id,
            "referral_code": self.referral_code,
            "status": self.status,
            "reward_points": self.reward_points,
            "reward_xp": self.reward_xp,
            "rewarded_at": self.rewarded_at.isoformat() if self.rewarded_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<UserReferral(id={self.id}, referrer_id={self.referrer_id}, referred_id={self.referred_id})>"


# ==================== User Stats Snapshot Model ====================
class UserStatsSnapshot(Base):
    """
    Daily snapshot of user stats for analytics
    Useful for tracking growth and trends
    """
    
    __tablename__ = "user_stats_snapshots"
    __table_args__ = (
        Index("idx_user_stats_user_date", "user_id", "snapshot_date"),
        Index("idx_user_stats_snapshot_date", "snapshot_date"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    snapshot_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Stats snapshot
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    xp: Mapped[int] = mapped_column(Integer, nullable=False)
    pulse_points: Mapped[int] = mapped_column(Integer, nullable=False)
    games_played: Mapped[int] = mapped_column(Integer, nullable=False)
    games_won: Mapped[int] = mapped_column(Integer, nullable=False)
    current_streak: Mapped[int] = mapped_column(Integer, nullable=False)
    longest_streak: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Daily changes
    xp_gained: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    points_gained: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    games_played_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    games_won_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", backref="stats_snapshots")

    def __repr__(self) -> str:
        return f"<UserStatsSnapshot(id={self.id}, user_id={self.user_id}, date={self.snapshot_date})>"


# ==================== Model Registration ====================
# Export all models for easy importing
__all__ = [
    "User",
    "BestScore",
    "PointTransaction",
    "Notification",
    "UserActivityLog",
    "UserReferral",
    "UserStatsSnapshot",
]
