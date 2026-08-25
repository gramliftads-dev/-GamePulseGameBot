"""
Transaction models for GamePulse Bot
Tracks all point transactions, referrals, and financial audit trails
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    Column, BigInteger, String, Integer, Boolean, DateTime, 
    JSON, ForeignKey, Text, Float, Index, UniqueConstraint,
    func, Numeric, Enum as SQLEnum
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.ext.hybrid import hybrid_property
import enum
import uuid

from src.core.database import Base, TimestampMixin


# ==================== Enums ====================
class TransactionType(str, enum.Enum):
    """Types of transactions"""
    # Rewards
    GAME_REWARD = "game_reward"
    CHALLENGE_REWARD = "challenge_reward"
    ACHIEVEMENT_REWARD = "achievement_reward"
    REFERRAL_REWARD = "referral_reward"
    STREAK_BONUS = "streak_bonus"
    LEVEL_UP_BONUS = "level_up_bonus"
    FRIEND_MATCH_WIN = "friend_match_win"
    DAILY_BONUS = "daily_bonus"
    SPECIAL_BONUS = "special_bonus"
    
    # Penalties
    GAME_PENALTY = "game_penalty"
    ADMIN_PENALTY = "admin_penalty"
    CHEAT_PENALTY = "cheat_penalty"
    
    # Adjustments
    ADMIN_ADJUSTMENT = "admin_adjustment"
    SYSTEM_ADJUSTMENT = "system_adjustment"
    REFUND = "refund"
    
    # Purchases (for future Mini App)
    PURCHASE = "purchase"
    GIFT = "gift"
    TRANSFER = "transfer"
    
    @classmethod
    def list(cls) -> List[str]:
        return [t.value for t in cls]
    
    @classmethod
    def get_display_name(cls, transaction_type: str) -> str:
        """Get display name for transaction type"""
        names = {
            "game_reward": "Game Reward",
            "challenge_reward": "Challenge Reward",
            "achievement_reward": "Achievement Reward",
            "referral_reward": "Referral Reward",
            "streak_bonus": "Streak Bonus",
            "level_up_bonus": "Level Up Bonus",
            "friend_match_win": "Friend Match Win",
            "daily_bonus": "Daily Bonus",
            "special_bonus": "Special Bonus",
            "game_penalty": "Game Penalty",
            "admin_penalty": "Admin Penalty",
            "cheat_penalty": "Cheat Penalty",
            "admin_adjustment": "Admin Adjustment",
            "system_adjustment": "System Adjustment",
            "refund": "Refund",
            "purchase": "Purchase",
            "gift": "Gift",
            "transfer": "Transfer"
        }
        return names.get(transaction_type, transaction_type.title())


class TransactionStatus(str, enum.Enum):
    """Status of a transaction"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REVERSED = "reversed"
    CANCELLED = "cancelled"
    FLAGGED = "flagged"
    
    @classmethod
    def list(cls) -> List[str]:
        return [status.value for status in cls]


class TransactionCategory(str, enum.Enum):
    """Category of transaction"""
    REWARD = "reward"
    PENALTY = "penalty"
    ADJUSTMENT = "adjustment"
    PURCHASE = "purchase"
    TRANSFER = "transfer"
    
    @classmethod
    def list(cls) -> List[str]:
        return [category.value for category in cls]


# ==================== Point Transaction Model ====================
class PointTransaction(Base):
    """Main transaction model for tracking all point changes"""
    
    __tablename__ = "point_transactions"
    __table_args__ = (
        Index("idx_point_transactions_user_id", "user_id"),
        Index("idx_point_transactions_type", "transaction_type"),
        Index("idx_point_transactions_status", "status"),
        Index("idx_point_transactions_created_at", "created_at"),
        Index("idx_point_transactions_reference", "reference_type", "reference_id"),
        Index("idx_point_transactions_user_date", "user_id", "created_at"),
        Index("idx_point_transactions_amount", "amount"),
        Index("idx_point_transactions_completed_at", "completed_at"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    transaction_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    
    # User
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Amount
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    balance_before: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    # Type and category
    transaction_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    
    # Reference
    reference_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    reference_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Description
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default=TransactionStatus.PENDING.value, nullable=False)
    is_reversed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reversed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reversed_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    
    # Flags
    is_suspicious: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    flag_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    flagged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="point_transactions")

    def __init__(self, **kwargs):
        if 'transaction_id' not in kwargs or not kwargs['transaction_id']:
            kwargs['transaction_id'] = self._generate_transaction_id()
        if 'category' not in kwargs:
            kwargs['category'] = self._determine_category(kwargs.get('transaction_type', ''))
        super().__init__(**kwargs)

    # ==================== Properties ====================
    
    @staticmethod
    def _generate_transaction_id() -> str:
        """Generate unique transaction ID"""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        random_part = uuid.uuid4().hex[:8].upper()
        return f"TX{timestamp}{random_part}"
    
    @staticmethod
    def _determine_category(transaction_type: str) -> str:
        """Determine category from transaction type"""
        reward_types = [
            TransactionType.GAME_REWARD.value,
            TransactionType.CHALLENGE_REWARD.value,
            TransactionType.ACHIEVEMENT_REWARD.value,
            TransactionType.REFERRAL_REWARD.value,
            TransactionType.STREAK_BONUS.value,
            TransactionType.LEVEL_UP_BONUS.value,
            TransactionType.FRIEND_MATCH_WIN.value,
            TransactionType.DAILY_BONUS.value,
            TransactionType.SPECIAL_BONUS.value,
        ]
        
        penalty_types = [
            TransactionType.GAME_PENALTY.value,
            TransactionType.ADMIN_PENALTY.value,
            TransactionType.CHEAT_PENALTY.value,
        ]
        
        adjustment_types = [
            TransactionType.ADMIN_ADJUSTMENT.value,
            TransactionType.SYSTEM_ADJUSTMENT.value,
            TransactionType.REFUND.value,
        ]
        
        purchase_types = [
            TransactionType.PURCHASE.value,
            TransactionType.GIFT.value,
        ]
        
        if transaction_type in reward_types:
            return TransactionCategory.REWARD.value
        elif transaction_type in penalty_types:
            return TransactionCategory.PENALTY.value
        elif transaction_type in adjustment_types:
            return TransactionCategory.ADJUSTMENT.value
        elif transaction_type in purchase_types:
            return TransactionCategory.PURCHASE.value
        elif transaction_type == TransactionType.TRANSFER.value:
            return TransactionCategory.TRANSFER.value
        
        return TransactionCategory.ADJUSTMENT.value
    
    @hybrid_property
    def is_completed(self) -> bool:
        """Check if transaction is completed"""
        return self.status == TransactionStatus.COMPLETED.value
    
    @hybrid_property
    def is_pending(self) -> bool:
        """Check if transaction is pending"""
        return self.status == TransactionStatus.PENDING.value
    
    @hybrid_property
    def is_reward(self) -> bool:
        """Check if transaction is a reward"""
        return self.category == TransactionCategory.REWARD.value
    
    @hybrid_property
    def is_penalty(self) -> bool:
        """Check if transaction is a penalty"""
        return self.category == TransactionCategory.PENALTY.value
    
    @hybrid_property
    def is_adjustment(self) -> bool:
        """Check if transaction is an adjustment"""
        return self.category == TransactionCategory.ADJUSTMENT.value
    
    @hybrid_property
    def display_type(self) -> str:
        """Get display name for transaction type"""
        return TransactionType.get_display_name(self.transaction_type)
    
    @hybrid_property
    def amount_display(self) -> str:
        """Get formatted amount with sign"""
        if self.amount > 0:
            return f"+{self.amount}"
        return str(self.amount)
    
    @hybrid_property
    def days_ago(self) -> int:
        """Get days since transaction"""
        return (datetime.utcnow() - self.created_at).days

    # ==================== Methods ====================
    
    def complete(self) -> None:
        """Mark transaction as completed"""
        self.status = TransactionStatus.COMPLETED.value
        self.completed_at = datetime.utcnow()
    
    def fail(self, reason: Optional[str] = None) -> None:
        """Mark transaction as failed"""
        self.status = TransactionStatus.FAILED.value
        if reason:
            if not self.metadata:
                self.metadata = {}
            self.metadata['fail_reason'] = reason
    
    def reverse(self, reason: str, reversed_by: Optional[int] = None) -> None:
        """Reverse the transaction"""
        self.is_reversed = True
        self.status = TransactionStatus.REVERSED.value
        self.reversed_at = datetime.utcnow()
        self.reversed_by = reversed_by
        
        if not self.metadata:
            self.metadata = {}
        self.metadata['reverse_reason'] = reason
    
    def flag(self, reason: str) -> None:
        """Flag transaction as suspicious"""
        self.is_flagged = True
        self.flag_reason = reason
        self.flagged_at = datetime.utcnow()
        self.status = TransactionStatus.FLAGGED.value
    
    def unflag(self) -> None:
        """Remove flag from transaction"""
        self.is_flagged = False
        self.flag_reason = None
        self.flagged_at = None
        if self.status == TransactionStatus.FLAGGED.value:
            self.status = TransactionStatus.PENDING.value
    
    # ==================== Factory Methods ====================
    
    @classmethod
    def create_game_reward(
        cls,
        user_id: int,
        amount: int,
        session_id: int,
        score: int = 0,
        description: Optional[str] = None
    ) -> "PointTransaction":
        """Create a game reward transaction"""
        return cls(
            user_id=user_id,
            amount=amount,
            transaction_type=TransactionType.GAME_REWARD.value,
            reference_type="game_session",
            reference_id=session_id,
            description=description or f"Game reward: {amount} points (Score: {score})",
            metadata={"score": score}
        )
    
    @classmethod
    def create_challenge_reward(
        cls,
        user_id: int,
        amount: int,
        challenge_id: int,
        challenge_date: str,
        description: Optional[str] = None
    ) -> "PointTransaction":
        """Create a challenge reward transaction"""
        return cls(
            user_id=user_id,
            amount=amount,
            transaction_type=TransactionType.CHALLENGE_REWARD.value,
            reference_type="daily_challenge",
            reference_id=challenge_id,
            description=description or f"Daily challenge reward: {amount} points ({challenge_date})",
            metadata={"challenge_date": challenge_date}
        )
    
    @classmethod
    def create_achievement_reward(
        cls,
        user_id: int,
        amount: int,
        achievement_id: int,
        achievement_name: str,
        description: Optional[str] = None
    ) -> "PointTransaction":
        """Create an achievement reward transaction"""
        return cls(
            user_id=user_id,
            amount=amount,
            transaction_type=TransactionType.ACHIEVEMENT_REWARD.value,
            reference_type="achievement",
            reference_id=achievement_id,
            description=description or f"Achievement reward: {amount} points ({achievement_name})",
            metadata={"achievement_name": achievement_name}
        )
    
    @classmethod
    def create_referral_reward(
        cls,
        user_id: int,
        amount: int,
        referred_user_id: int,
        referred_username: Optional[str] = None,
        description: Optional[str] = None
    ) -> "PointTransaction":
        """Create a referral reward transaction"""
        return cls(
            user_id=user_id,
            amount=amount,
            transaction_type=TransactionType.REFERRAL_REWARD.value,
            reference_type="user",
            reference_id=referred_user_id,
            description=description or f"Referral reward: {amount} points from @{referred_username or referred_user_id}",
            metadata={"referred_user_id": referred_user_id, "referred_username": referred_username}
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
            transaction_type=TransactionType.STREAK_BONUS.value,
            reference_type="streak",
            reference_id=streak_days,
            description=description or f"Streak bonus: {amount} points for {streak_days} days",
            metadata={"streak_days": streak_days}
        )
    
    @classmethod
    def create_level_up_bonus(
        cls,
        user_id: int,
        amount: int,
        level: int,
        description: Optional[str] = None
    ) -> "PointTransaction":
        """Create a level up bonus transaction"""
        return cls(
            user_id=user_id,
            amount=amount,
            transaction_type=TransactionType.LEVEL_UP_BONUS.value,
            reference_type="level",
            reference_id=level,
            description=description or f"Level up bonus: {amount} points for reaching level {level}",
            metadata={"level": level}
        )
    
    @classmethod
    def create_friend_match_win(
        cls,
        user_id: int,
        amount: int,
        match_id: int,
        opponent_name: str,
        description: Optional[str] = None
    ) -> "PointTransaction":
        """Create a friend match win transaction"""
        return cls(
            user_id=user_id,
            amount=amount,
            transaction_type=TransactionType.FRIEND_MATCH_WIN.value,
            reference_type="friend_match",
            reference_id=match_id,
            description=description or f"Friend match win: {amount} points against {opponent_name}",
            metadata={"match_id": match_id, "opponent_name": opponent_name}
        )
    
    @classmethod
    def create_daily_bonus(
        cls,
        user_id: int,
        amount: int,
        day: int,
        description: Optional[str] = None
    ) -> "PointTransaction":
        """Create a daily bonus transaction"""
        return cls(
            user_id=user_id,
            amount=amount,
            transaction_type=TransactionType.DAILY_BONUS.value,
            description=description or f"Daily bonus: {amount} points (Day {day})",
            metadata={"day": day}
        )
    
    @classmethod
    def create_admin_adjustment(
        cls,
        user_id: int,
        amount: int,
        admin_id: int,
        reason: str,
        description: Optional[str] = None
    ) -> "PointTransaction":
        """Create an admin adjustment transaction"""
        return cls(
            user_id=user_id,
            amount=amount,
            transaction_type=TransactionType.ADMIN_ADJUSTMENT.value,
            description=description or f"Admin adjustment: {amount} points ({reason})",
            metadata={"admin_id": admin_id, "reason": reason}
        )
    
    @classmethod
    def create_cheat_penalty(
        cls,
        user_id: int,
        amount: int,
        reason: str,
        session_id: Optional[str] = None,
        description: Optional[str] = None
    ) -> "PointTransaction":
        """Create a cheat penalty transaction"""
        return cls(
            user_id=user_id,
            amount=amount,  # Should be negative
            transaction_type=TransactionType.CHEAT_PENALTY.value,
            reference_type="game_session",
            reference_id=session_id,
            description=description or f"Cheat penalty: {amount} points ({reason})",
            metadata={"reason": reason, "session_id": session_id}
        )
    
    # ==================== Query Helpers ====================
    
    def to_dict(self, include_user: bool = False) -> Dict[str, Any]:
        """Convert transaction to dictionary"""
        data = {
            "id": self.id,
            "transaction_id": self.transaction_id,
            "user_id": self.user_id,
            "amount": self.amount,
            "amount_display": self.amount_display,
            "balance_before": self.balance_before,
            "balance_after": self.balance_after,
            "transaction_type": self.transaction_type,
            "display_type": self.display_type,
            "category": self.category,
            "reference_type": self.reference_type,
            "reference_id": self.reference_id,
            "session_id": self.session_id,
            "description": self.description,
            "metadata": self.metadata,
            "status": self.status,
            "is_completed": self.is_completed,
            "is_reversed": self.is_reversed,
            "is_suspicious": self.is_suspicious,
            "is_flagged": self.is_flagged,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "days_ago": self.days_ago,
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
        return f"<PointTransaction(id={self.id}, transaction_id={self.transaction_id}, user_id={self.user_id}, amount={self.amount}, type={self.transaction_type})>"


# ==================== Referral Transaction Model ====================
class ReferralTransaction(Base):
    """Tracks referral rewards and status"""
    
    __tablename__ = "referral_transactions"
    __table_args__ = (
        Index("idx_referral_transactions_referrer", "referrer_id"),
        Index("idx_referral_transactions_referred", "referred_id"),
        Index("idx_referral_transactions_status", "status"),
        Index("idx_referral_transactions_created_at", "created_at"),
        Index("idx_referral_transactions_rewarded_at", "rewarded_at"),
        UniqueConstraint('referred_id', name='uq_referral_transaction_referred'),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    referrer_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    referred_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Referral code used
    referral_code: Mapped[str] = mapped_column(String(20), nullable=False)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    
    # Rewards
    points_rewarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    xp_rewarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Metadata
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    rewarded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expired_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    referrer: Mapped["User"] = relationship("User", foreign_keys=[referrer_id])
    referred: Mapped["User"] = relationship("User", foreign_keys=[referred_id])

    def mark_rewarded(self, points: int, xp: int) -> None:
        """Mark referral as rewarded"""
        self.status = "rewarded"
        self.points_rewarded = points
        self.xp_rewarded = xp
        self.rewarded_at = datetime.utcnow()
    
    def mark_expired(self) -> None:
        """Mark referral as expired"""
        self.status = "expired"
        self.expired_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "referrer_id": self.referrer_id,
            "referred_id": self.referred_id,
            "referral_code": self.referral_code,
            "status": self.status,
            "points_rewarded": self.points_rewarded,
            "xp_rewarded": self.xp_rewarded,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "rewarded_at": self.rewarded_at.isoformat() if self.rewarded_at else None,
            "expired_at": self.expired_at.isoformat() if self.expired_at else None,
        }
    
    def __repr__(self) -> str:
        return f"<ReferralTransaction(id={self.id}, referrer_id={self.referrer_id}, referred_id={self.referred_id}, status={self.status})>"


# ==================== Transaction Summary Model ====================
class TransactionSummary(Base):
    """Daily summary of transactions for analytics"""
    
    __tablename__ = "transaction_summaries"
    __table_args__ = (
        Index("idx_transaction_summaries_date", "summary_date"),
        Index("idx_transaction_summaries_user", "user_id"),
        Index("idx_transaction_summaries_date_user", "summary_date", "user_id"),
        UniqueConstraint('user_id', 'summary_date', name='uq_transaction_summary_user_date'),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    summary_date: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Daily totals
    total_points_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_points_spent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    net_points_change: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Breakdown by type
    game_rewards: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    challenge_rewards: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    achievement_rewards: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    referral_rewards: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    streak_bonuses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    level_up_bonuses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    friend_match_wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    penalties: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    adjustments: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Counts
    transaction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Metadata
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", backref="transaction_summaries")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "summary_date": self.summary_date.isoformat() if self.summary_date else None,
            "total_points_earned": self.total_points_earned,
            "total_points_spent": self.total_points_spent,
            "net_points_change": self.net_points_change,
            "game_rewards": self.game_rewards,
            "challenge_rewards": self.challenge_rewards,
            "achievement_rewards": self.achievement_rewards,
            "referral_rewards": self.referral_rewards,
            "streak_bonuses": self.streak_bonuses,
            "level_up_bonuses": self.level_up_bonuses,
            "friend_match_wins": self.friend_match_wins,
            "penalties": self.penalties,
            "adjustments": self.adjustments,
            "transaction_count": self.transaction_count,
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        return f"<TransactionSummary(id={self.id}, user_id={self.user_id}, date={self.summary_date})>"


# ==================== Model Registration ====================
__all__ = [
    "TransactionType",
    "TransactionStatus",
    "TransactionCategory",
    "PointTransaction",
    "ReferralTransaction",
    "TransactionSummary",
]
