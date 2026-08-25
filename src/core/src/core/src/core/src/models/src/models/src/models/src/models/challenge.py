"""
Daily Challenge models for GamePulse Bot
Includes DailyChallenge definitions and user completions
"""

from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    Column, BigInteger, String, Integer, Boolean, DateTime, 
    JSON, ForeignKey, Text, Float, Index, UniqueConstraint,
    func, Date
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.ext.hybrid import hybrid_property
import enum
import random

from src.core.database import Base, TimestampMixin


# ==================== Enums ====================
class ChallengeType(str, enum.Enum):
    """Types of daily challenges"""
    PLAY_GAMES = "play_games"
    WIN_GAMES = "win_games"
    SCORE_TARGET = "score_target"
    SPECIFIC_GAME = "specific_game"
    PERFECT_SCORE = "perfect_score"
    STREAK_MAINTAIN = "streak_maintain"
    FRIEND_CHALLENGE = "friend_challenge"
    POINTS_EARN = "points_earn"
    XP_EARN = "xp_earn"
    MULTIPLE_GAMES = "multiple_games"
    ACHIEVEMENT_UNLOCK = "achievement_unlock"
    SPECIAL = "special"
    
    @classmethod
    def list(cls) -> List[str]:
        return [challenge.value for challenge in cls]
    
    @classmethod
    def get_display_name(cls, challenge_type: str) -> str:
        """Get display name for challenge type"""
        names = {
            "play_games": "Play Games",
            "win_games": "Win Games",
            "score_target": "Score Target",
            "specific_game": "Specific Game",
            "perfect_score": "Perfect Score",
            "streak_maintain": "Maintain Streak",
            "friend_challenge": "Friend Challenge",
            "points_earn": "Earn Points",
            "xp_earn": "Earn XP",
            "multiple_games": "Multiple Games",
            "achievement_unlock": "Unlock Achievement",
            "special": "Special Challenge"
        }
        return names.get(challenge_type, challenge_type.title())


class ChallengeDifficulty(str, enum.Enum):
    """Difficulty levels for challenges"""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EXPERT = "expert"
    LEGENDARY = "legendary"
    
    @classmethod
    def list(cls) -> List[str]:
        return [difficulty.value for difficulty in cls]
    
    @classmethod
    def get_multiplier(cls, difficulty: str) -> float:
        """Get reward multiplier for difficulty"""
        multipliers = {
            "easy": 1.0,
            "medium": 1.5,
            "hard": 2.0,
            "expert": 3.0,
            "legendary": 5.0
        }
        return multipliers.get(difficulty, 1.0)
    
    @classmethod
    def get_color(cls, difficulty: str) -> str:
        """Get color for difficulty"""
        colors = {
            "easy": "#00FF00",
            "medium": "#FFA500",
            "hard": "#FF0000",
            "expert": "#800080",
            "legendary": "#FFD700"
        }
        return colors.get(difficulty, "#FFFFFF")


class ChallengeStatus(str, enum.Enum):
    """Status of a user's challenge"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


# ==================== Daily Challenge Model ====================
class DailyChallenge(Base):
    """Daily challenge definitions"""
    
    __tablename__ = "daily_challenges"
    __table_args__ = (
        Index("idx_daily_challenges_date", "challenge_date"),
        Index("idx_daily_challenges_type", "challenge_type"),
        Index("idx_daily_challenges_difficulty", "difficulty"),
        Index("idx_daily_challenges_is_active", "is_active"),
        Index("idx_daily_challenges_game_type", "game_type"),
        Index("idx_daily_challenges_date_type", "challenge_date", "challenge_type"),
        UniqueConstraint('challenge_date', 'game_type', name='uq_daily_challenge_date_game'),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    challenge_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    
    # Challenge details
    challenge_type: Mapped[str] = mapped_column(String(50), nullable=False)
    challenge_type_display: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Target
    target_value: Mapped[int] = mapped_column(Integer, nullable=False)
    game_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    
    # Metadata
    description: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    difficulty: Mapped[str] = mapped_column(String(20), default=ChallengeDifficulty.MEDIUM.value, nullable=False)
    
    # Rewards
    xp_reward: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    points_reward: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bonus_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_repeatable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    completions = relationship("DailyChallengeCompletion", back_populates="challenge", cascade="all, delete-orphan")

    # ==================== Properties ====================
    
    @hybrid_property
    def difficulty_display(self) -> str:
        """Get display name for difficulty"""
        return self.difficulty.title()
    
    @hybrid_property
    def difficulty_color(self) -> str:
        """Get color for difficulty"""
        return ChallengeDifficulty.get_color(self.difficulty)
    
    @hybrid_property
    def reward_multiplier(self) -> float:
        """Get reward multiplier based on difficulty"""
        return ChallengeDifficulty.get_multiplier(self.difficulty)
    
    @hybrid_property
    def display_name(self) -> str:
        """Get display name of challenge"""
        if self.challenge_type_display:
            return self.challenge_type_display
        return ChallengeType.get_display_name(self.challenge_type)
    
    @hybrid_property
    def total_reward(self) -> int:
        """Get total reward value"""
        return int((self.xp_reward + self.points_reward) * self.reward_multiplier)
    
    @hybrid_property
    def is_expired(self) -> bool:
        """Check if challenge is expired"""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        # Default: challenge expires at end of day
        end_of_day = datetime.combine(self.challenge_date, datetime.max.time())
        return datetime.utcnow() > end_of_day
    
    @hybrid_property
    def is_today(self) -> bool:
        """Check if challenge is for today"""
        return self.challenge_date == date.today()
    
    @hybrid_property
    def days_remaining(self) -> int:
        """Get days remaining for challenge"""
        if self.is_expired:
            return 0
        delta = (datetime.combine(self.challenge_date, datetime.max.time()) - datetime.utcnow()).days
        return max(0, delta)

    # ==================== Methods ====================
    
    def check_progress(self, user_data: Dict[str, Any]) -> int:
        """
        Check user's progress towards challenge
        
        Args:
            user_data: Dictionary containing user stats
            
        Returns:
            Current progress value
        """
        # Get the value based on challenge type
        progress = self._get_progress_value(user_data)
        return min(progress, self.target_value)
    
    def _get_progress_value(self, user_data: Dict[str, Any]) -> int:
        """Extract progress value from user data based on challenge type"""
        mapping = {
            ChallengeType.PLAY_GAMES.value: user_data.get('games_played_today', 0),
            ChallengeType.WIN_GAMES.value: user_data.get('games_won_today', 0),
            ChallengeType.SCORE_TARGET.value: user_data.get('best_score', 0),
            ChallengeType.SPECIFIC_GAME.value: self._get_game_specific_progress(user_data),
            ChallengeType.PERFECT_SCORE.value: user_data.get('perfect_scores_today', 0),
            ChallengeType.STREAK_MAINTAIN.value: user_data.get('current_streak', 0),
            ChallengeType.FRIEND_CHALLENGE.value: user_data.get('friend_challenges_won_today', 0),
            ChallengeType.POINTS_EARN.value: user_data.get('points_earned_today', 0),
            ChallengeType.XP_EARN.value: user_data.get('xp_earned_today', 0),
            ChallengeType.MULTIPLE_GAMES.value: self._get_multiple_games_progress(user_data),
            ChallengeType.ACHIEVEMENT_UNLOCK.value: user_data.get('achievements_unlocked_today', 0),
            ChallengeType.SPECIAL.value: self._get_special_progress(user_data),
        }
        
        return mapping.get(self.challenge_type, 0)
    
    def _get_game_specific_progress(self, user_data: Dict[str, Any]) -> int:
        """Get progress for specific game challenges"""
        game_specific = user_data.get('game_specific', {})
        if self.game_type:
            return game_specific.get(self.game_type, {}).get('games_played_today', 0)
        return 0
    
    def _get_multiple_games_progress(self, user_data: Dict[str, Any]) -> int:
        """Get progress for multiple games challenge"""
        # Count how many different games have been played
        game_specific = user_data.get('game_specific', {})
        return len([g for g in game_specific.values() if g.get('games_played_today', 0) > 0])
    
    def _get_special_progress(self, user_data: Dict[str, Any]) -> int:
        """Get progress for special challenges"""
        # Implement special challenge logic here
        # This could include things like:
        # - Combined requirements
        # - Sequential requirements
        # - Rare accomplishments
        return user_data.get('special_progress', 0)
    
    def is_completed(self, progress: int) -> bool:
        """Check if challenge is completed"""
        return progress >= self.target_value
    
    def calculate_rewards(self) -> Dict[str, int]:
        """Calculate rewards with difficulty multiplier"""
        multiplier = self.reward_multiplier
        return {
            "xp": int(self.xp_reward * multiplier),
            "points": int(self.points_reward * multiplier)
        }
    
    def to_dict(self, include_completions: bool = False) -> Dict[str, Any]:
        """Convert challenge to dictionary"""
        data = {
            "id": self.id,
            "challenge_date": self.challenge_date.isoformat() if self.challenge_date else None,
            "challenge_type": self.challenge_type,
            "display_name": self.display_name,
            "target_value": self.target_value,
            "game_type": self.game_type,
            "description": self.description,
            "icon": self.icon,
            "difficulty": self.difficulty,
            "difficulty_display": self.difficulty_display,
            "difficulty_color": self.difficulty_color,
            "reward_multiplier": self.reward_multiplier,
            "xp_reward": self.xp_reward,
            "points_reward": self.points_reward,
            "total_reward": self.total_reward,
            "is_active": self.is_active,
            "is_repeatable": self.is_repeatable,
            "is_today": self.is_today,
            "is_expired": self.is_expired,
            "days_remaining": self.days_remaining,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
        
        if include_completions:
            data["completions"] = [
                completion.to_dict() for completion in self.completions
            ]
        
        return data
    
    def __repr__(self) -> str:
        return f"<DailyChallenge(id={self.id}, date={self.challenge_date}, type={self.challenge_type})>"


# ==================== Daily Challenge Completion Model ====================
class DailyChallengeCompletion(Base):
    """User's completion of daily challenges"""
    
    __tablename__ = "daily_challenge_completions"
    __table_args__ = (
        Index("idx_daily_challenge_completions_user", "user_id"),
        Index("idx_daily_challenge_completions_challenge", "challenge_id"),
        Index("idx_daily_challenge_completions_status", "status"),
        Index("idx_daily_challenge_completions_completed_at", "completed_at"),
        Index("idx_daily_challenge_completions_user_date", "user_id", "challenge_date"),
        UniqueConstraint('user_id', 'challenge_id', name='uq_user_daily_challenge'),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    challenge_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("daily_challenges.id", ondelete="CASCADE"), nullable=False)
    challenge_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    
    # Progress
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    target_value: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default=ChallengeStatus.PENDING.value, nullable=False)
    
    # Rewards earned
    xp_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    points_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Metadata
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Timestamps
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="daily_challenges")
    challenge: Mapped["DailyChallenge"] = relationship("DailyChallenge", back_populates="completions")

    # ==================== Properties ====================
    
    @hybrid_property
    def is_completed(self) -> bool:
        """Check if challenge is completed"""
        return self.status == ChallengeStatus.COMPLETED.value
    
    @hybrid_property
    def is_failed(self) -> bool:
        """Check if challenge failed"""
        return self.status == ChallengeStatus.FAILED.value
    
    @hybrid_property
    def is_in_progress(self) -> bool:
        """Check if challenge is in progress"""
        return self.status == ChallengeStatus.IN_PROGRESS.value
    
    @hybrid_property
    def progress_percentage(self) -> float:
        """Get progress as percentage"""
        if self.target_value == 0:
            return 0.0
        return min(100.0, (self.progress / self.target_value) * 100)
    
    @hybrid_property
    def progress_text(self) -> str:
        """Get progress display text"""
        if self.is_completed:
            return "✅ Completed"
        return f"{self.progress}/{self.target_value}"
    
    @hybrid_property
    def time_remaining(self) -> Optional[str]:
        """Get time remaining for challenge"""
        if self.is_completed:
            return None
        
        # Challenge expires at end of day
        end_of_day = datetime.combine(self.challenge_date, datetime.max.time())
        remaining = end_of_day - datetime.utcnow()
        
        if remaining.total_seconds() <= 0:
            return "Expired"
        elif remaining.days > 0:
            return f"{remaining.days}d {remaining.seconds//3600}h"
        elif remaining.seconds > 3600:
            return f"{remaining.seconds//3600}h {(remaining.seconds%3600)//60}m"
        elif remaining.seconds > 60:
            return f"{remaining.seconds//60}m"
        else:
            return "Less than a minute"

    # ==================== Methods ====================
    
    def update_progress(self, progress: int) -> bool:
        """
        Update progress towards challenge completion
        
        Args:
            progress: Current progress value
            
        Returns:
            True if challenge was completed
        """
        self.progress = min(progress, self.target_value)
        self.updated_at = datetime.utcnow()
        
        if self.status == ChallengeStatus.PENDING.value:
            self.status = ChallengeStatus.IN_PROGRESS.value
        
        if self.progress >= self.target_value and self.status != ChallengeStatus.COMPLETED.value:
            self.complete()
            return True
        
        return False
    
    def complete(self) -> None:
        """Mark challenge as completed"""
        self.status = ChallengeStatus.COMPLETED.value
        self.completed_at = datetime.utcnow()
        
        # Calculate rewards
        rewards = self.challenge.calculate_rewards() if self.challenge else {"xp": 0, "points": 0}
        self.xp_earned = rewards["xp"]
        self.points_earned = rewards["points"]
    
    def fail(self, reason: Optional[str] = None) -> None:
        """Mark challenge as failed"""
        self.status = ChallengeStatus.FAILED.value
        if reason:
            if not self.metadata:
                self.metadata = {}
            self.metadata["fail_reason"] = reason
    
    def expire(self) -> None:
        """Mark challenge as expired"""
        if not self.is_completed:
            self.status = ChallengeStatus.EXPIRED.value
    
    def to_dict(self, include_challenge: bool = False) -> Dict[str, Any]:
        """Convert completion to dictionary"""
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "challenge_id": self.challenge_id,
            "challenge_date": self.challenge_date.isoformat() if self.challenge_date else None,
            "progress": self.progress,
            "target_value": self.target_value,
            "progress_percentage": self.progress_percentage,
            "progress_text": self.progress_text,
            "status": self.status,
            "xp_earned": self.xp_earned,
            "points_earned": self.points_earned,
            "time_remaining": self.time_remaining,
            "is_completed": self.is_completed,
            "metadata": self.metadata,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        
        if include_challenge and self.challenge:
            data["challenge"] = self.challenge.to_dict()
        
        return data
    
    def __repr__(self) -> str:
        return f"<DailyChallengeCompletion(id={self.id}, user_id={self.user_id}, challenge_id={self.challenge_id}, status={self.status})>"


# ==================== Challenge Factory ====================
class ChallengeFactory:
    """Factory for creating daily challenges"""
    
    @staticmethod
    def generate_daily_challenges(date: date) -> List[Dict[str, Any]]:
        """
        Generate daily challenges for a specific date
        
        Args:
            date: Date to generate challenges for
            
        Returns:
            List of challenge data dictionaries
        """
        challenges = []
        
        # Base challenges always included
        base_challenges = [
            {
                "challenge_type": ChallengeType.PLAY_GAMES.value,
                "target_value": 3,
                "description": "Play 3 games today",
                "icon": "🎮",
                "difficulty": ChallengeDifficulty.EASY.value,
                "xp_reward": 10,
                "points_reward": 5,
            },
            {
                "challenge_type": ChallengeType.WIN_GAMES.value,
                "target_value": 2,
                "description": "Win 2 games today",
                "icon": "🏆",
                "difficulty": ChallengeDifficulty.MEDIUM.value,
                "xp_reward": 20,
                "points_reward": 10,
            },
        ]
        
        # Rotating challenges based on day of week
        day = date.weekday()  # 0 = Monday, 6 = Sunday
        
        rotating_challenges = {
            0: [  # Monday
                {
                    "challenge_type": ChallengeType.SCORE_TARGET.value,
                    "target_value": 500,
                    "description": "Score 500 total points",
                    "icon": "📈",
                    "difficulty": ChallengeDifficulty.MEDIUM.value,
                    "xp_reward": 25,
                    "points_reward": 15,
                }
            ],
            1: [  # Tuesday
                {
                    "challenge_type": ChallengeType.SPECIFIC_GAME.value,
                    "target_value": 1,
                    "description": "Play Quick Quiz",
                    "icon": "📚",
                    "difficulty": ChallengeDifficulty.EASY.value,
                    "xp_reward": 15,
                    "points_reward": 10,
                    "game_type": "quiz",
                }
            ],
            2: [  # Wednesday
                {
                    "challenge_type": ChallengeType.PERFECT_SCORE.value,
                    "target_value": 1,
                    "description": "Get a perfect score in any game",
                    "icon": "⭐",
                    "difficulty": ChallengeDifficulty.HARD.value,
                    "xp_reward": 50,
                    "points_reward": 25,
                }
            ],
            3: [  # Thursday
                {
                    "challenge_type": ChallengeType.MULTIPLE_GAMES.value,
                    "target_value": 3,
                    "description": "Play 3 different games",
                    "icon": "🎯",
                    "difficulty": ChallengeDifficulty.MEDIUM.value,
                    "xp_reward": 30,
                    "points_reward": 15,
                }
            ],
            4: [  # Friday
                {
                    "challenge_type": ChallengeType.FRIEND_CHALLENGE.value,
                    "target_value": 1,
                    "description": "Win a friend challenge",
                    "icon": "🤝",
                    "difficulty": ChallengeDifficulty.MEDIUM.value,
                    "xp_reward": 25,
                    "points_reward": 20,
                }
            ],
            5: [  # Saturday
                {
                    "challenge_type": ChallengeType.POINTS_EARN.value,
                    "target_value": 100,
                    "description": "Earn 100 Pulse Points",
                    "icon": "💰",
                    "difficulty": ChallengeDifficulty.MEDIUM.value,
                    "xp_reward": 30,
                    "points_reward": 20,
                }
            ],
            6: [  # Sunday
                {
                    "challenge_type": ChallengeType.XP_EARN.value,
                    "target_value": 150,
                    "description": "Earn 150 XP",
                    "icon": "⭐",
                    "difficulty": ChallengeDifficulty.HARD.value,
                    "xp_reward": 40,
                    "points_reward": 25,
                }
            ],
        }
        
        # Add base challenges
        for challenge in base_challenges:
            challenge_data = ChallengeFactory._create_challenge_data(date, challenge)
            challenges.append(challenge_data)
        
        # Add rotating challenges for the day
        if day in rotating_challenges:
            for challenge in rotating_challenges[day]:
                challenge_data = ChallengeFactory._create_challenge_data(date, challenge)
                challenges.append(challenge_data)
        
        return challenges
    
    @staticmethod
    def _create_challenge_data(date: date, challenge: Dict[str, Any]) -> Dict[str, Any]:
        """Create challenge data dictionary"""
        return {
            "challenge_date": date,
            "challenge_type": challenge["challenge_type"],
            "target_value": challenge["target_value"],
            "description": challenge["description"],
            "icon": challenge.get("icon"),
            "difficulty": challenge.get("difficulty", ChallengeDifficulty.MEDIUM.value),
            "xp_reward": challenge.get("xp_reward", 0),
            "points_reward": challenge.get("points_reward", 0),
            "game_type": challenge.get("game_type"),
            "is_active": True,
            "is_repeatable": False,
            "expires_at": datetime.combine(date, datetime.max.time()),
        }
    
    @staticmethod
    def generate_special_challenge(date: date, user_stats: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Generate a special challenge tailored to the user
        
        Args:
            date: Date for the challenge
            user_stats: User statistics for personalization
            
        Returns:
            Challenge data dictionary or None
        """
        # Example: Challenge based on user's weak points
        weak_games = user_stats.get('weak_games', [])
        if weak_games:
            # Challenge to improve in weak game
            return {
                "challenge_date": date,
                "challenge_type": ChallengeType.SPECIFIC_GAME.value,
                "target_value": 1,
                "description": f"Practice {weak_games[0].title()} - play and improve",
                "icon": "🎯",
                "difficulty": ChallengeDifficulty.MEDIUM.value,
                "xp_reward": 25,
                "points_reward": 15,
                "game_type": weak_games[0],
                "is_active": True,
                "is_repeatable": False,
                "expires_at": datetime.combine(date, datetime.max.time()),
            }
        
        return None


# ==================== Model Registration ====================
__all__ = [
    "ChallengeType",
    "ChallengeDifficulty",
    "ChallengeStatus",
    "DailyChallenge",
    "DailyChallengeCompletion",
    "ChallengeFactory",
]
