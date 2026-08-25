"""
Achievement models for GamePulse Bot
Includes Achievement definitions and UserAchievement tracking
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    Column, BigInteger, String, Integer, Boolean, DateTime, 
    JSON, ForeignKey, Text, Float, Index, UniqueConstraint,
    func, Enum as SQLEnum
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.ext.hybrid import hybrid_property
import enum

from src.core.database import Base, TimestampMixin


# ==================== Enums ====================
class AchievementCategory(str, enum.Enum):
    """Achievement categories"""
    MILESTONE = "milestone"
    GAME = "game"
    STREAK = "streak"
    SOCIAL = "social"
    CHALLENGE = "challenge"
    PROGRESSION = "progression"
    COMPETITIVE = "competitive"
    SPECIAL = "special"
    
    @classmethod
    def list(cls) -> List[str]:
        return [category.value for category in cls]
    
    @classmethod
    def get_display_name(cls, category: str) -> str:
        """Get display name for category"""
        names = {
            "milestone": "🏆 Milestone",
            "game": "🎮 Game",
            "streak": "🔥 Streak",
            "social": "👥 Social",
            "challenge": "🎯 Challenge",
            "progression": "📈 Progression",
            "competitive": "⚔️ Competitive",
            "special": "✨ Special"
        }
        return names.get(category, category.title())


class AchievementRarity(str, enum.Enum):
    """Achievement rarity levels"""
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"
    MYTHIC = "mythic"
    
    @classmethod
    def list(cls) -> List[str]:
        return [rarity.value for rarity in cls]
    
    @classmethod
    def get_color(cls, rarity: str) -> str:
        """Get color for rarity"""
        colors = {
            "common": "#808080",
            "uncommon": "#1EFF00",
            "rare": "#0070DD",
            "epic": "#A335EE",
            "legendary": "#FF8000",
            "mythic": "#E6CC80"
        }
        return colors.get(rarity, "#808080")
    
    @classmethod
    def get_emoji(cls, rarity: str) -> str:
        """Get emoji for rarity"""
        emojis = {
            "common": "⬜",
            "uncommon": "🟩",
            "rare": "🟦",
            "epic": "🟪",
            "legendary": "🟧",
            "mythic": "🌟"
        }
        return emojis.get(rarity, "⬜")


class AchievementRequirementType(str, enum.Enum):
    """Types of achievement requirements"""
    GAMES_PLAYED = "games_played"
    GAMES_WON = "games_won"
    SCORE = "score"
    STREAK = "streak"
    LEVEL = "level"
    XP = "xp"
    POINTS = "points"
    REFERRALS = "referrals"
    CHALLENGES_COMPLETED = "challenges_completed"
    UNIQUE_GAMES = "unique_games"
    FRIEND_MATCHES = "friend_matches"
    FRIEND_MATCHES_WON = "friend_matches_won"
    TOTAL_SCORE = "total_score"
    ACHIEVEMENTS_UNLOCKED = "achievements_unlocked"
    PERFECT_SCORE = "perfect_score"
    CONSECUTIVE_WINS = "consecutive_wins"
    GAME_SPECIFIC = "game_specific"
    SPECIAL = "special"


# ==================== Achievement Model ====================
class Achievement(Base):
    """Achievement definitions"""
    
    __tablename__ = "achievements"
    __table_args__ = (
        Index("idx_achievements_code", "code"),
        Index("idx_achievements_category", "category"),
        Index("idx_achievements_rarity", "rarity"),
        Index("idx_achievements_is_active", "is_active"),
        Index("idx_achievements_requirement_type", "requirement_type"),
        Index("idx_achievements_points_reward", "points_reward"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    
    # Metadata
    icon: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    rarity: Mapped[str] = mapped_column(String(20), default=AchievementRarity.COMMON.value, nullable=False)
    
    # Requirements
    requirement_type: Mapped[str] = mapped_column(String(50), nullable=False)
    requirement_value: Mapped[int] = mapped_column(Integer, nullable=False)
    requirement_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Rewards
    xp_reward: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    points_reward: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bonus_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Display
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user_achievements = relationship("UserAchievement", back_populates="achievement", cascade="all, delete-orphan")

    # ==================== Properties ====================
    
    @hybrid_property
    def category_display(self) -> str:
        """Get display name for category"""
        return AchievementCategory.get_display_name(self.category)
    
    @hybrid_property
    def rarity_color(self) -> str:
        """Get color for rarity"""
        return AchievementRarity.get_color(self.rarity)
    
    @hybrid_property
    def rarity_emoji(self) -> str:
        """Get emoji for rarity"""
        return AchievementRarity.get_emoji(self.rarity)
    
    @hybrid_property
    def display_name(self) -> str:
        """Get display name with rarity emoji"""
        return f"{self.rarity_emoji} {self.name}"
    
    @hybrid_property
    def total_reward(self) -> int:
        """Get total reward value"""
        return self.xp_reward + self.points_reward
    
    @hybrid_property
    def is_high_value(self) -> bool:
        """Check if achievement is high value"""
        return self.total_reward >= 100
    
    @hybrid_property
    def difficulty(self) -> str:
        """Get difficulty based on requirement value"""
        if self.rarity in [AchievementRarity.MYTHIC.value, AchievementRarity.LEGENDARY.value]:
            return "Very Hard"
        elif self.rarity == AchievementRarity.EPIC.value:
            return "Hard"
        elif self.rarity == AchievementRarity.RARE.value:
            return "Medium"
        else:
            return "Easy"

    # ==================== Methods ====================
    
    def check_requirement(self, user_data: Dict[str, Any]) -> bool:
        """
        Check if user meets achievement requirements
        
        Args:
            user_data: Dictionary containing user stats
            
        Returns:
            True if requirement is met
        """
        # Get the value from user data based on requirement type
        value = self._get_user_value(user_data)
        if value is None:
            return False
        
        # Check requirement with optional metadata
        if self.requirement_metadata:
            # Check specific game type if required
            if self.requirement_metadata.get('game_type'):
                game_type = self.requirement_metadata['game_type']
                if user_data.get('game_type') != game_type:
                    return False
            
            # Check specific category if required
            if self.requirement_metadata.get('category'):
                category = self.requirement_metadata['category']
                if user_data.get('category') != category:
                    return False
        
        # Compare value to requirement
        if isinstance(value, (int, float)):
            return value >= self.requirement_value
        elif isinstance(value, list):
            return len(value) >= self.requirement_value
        elif isinstance(value, bool):
            return value == bool(self.requirement_value)
        
        return False
    
    def _get_user_value(self, user_data: Dict[str, Any]) -> Any:
        """Extract value from user data based on requirement type"""
        mapping = {
            AchievementRequirementType.GAMES_PLAYED.value: user_data.get('games_played', 0),
            AchievementRequirementType.GAMES_WON.value: user_data.get('games_won', 0),
            AchievementRequirementType.SCORE.value: user_data.get('score', 0),
            AchievementRequirementType.STREAK.value: user_data.get('current_streak', 0),
            AchievementRequirementType.LEVEL.value: user_data.get('level', 1),
            AchievementRequirementType.XP.value: user_data.get('xp', 0),
            AchievementRequirementType.POINTS.value: user_data.get('pulse_points', 0),
            AchievementRequirementType.REFERRALS.value: user_data.get('referral_count', 0),
            AchievementRequirementType.CHALLENGES_COMPLETED.value: user_data.get('challenges_completed', 0),
            AchievementRequirementType.UNIQUE_GAMES.value: user_data.get('unique_games_played', 0),
            AchievementRequirementType.FRIEND_MATCHES.value: user_data.get('friend_matches_played', 0),
            AchievementRequirementType.FRIEND_MATCHES_WON.value: user_data.get('friend_matches_won', 0),
            AchievementRequirementType.TOTAL_SCORE.value: user_data.get('total_score', 0),
            AchievementRequirementType.ACHIEVEMENTS_UNLOCKED.value: user_data.get('achievements_unlocked', 0),
            AchievementRequirementType.PERFECT_SCORE.value: user_data.get('perfect_scores', 0),
            AchievementRequirementType.CONSECUTIVE_WINS.value: user_data.get('consecutive_wins', 0),
            AchievementRequirementType.GAME_SPECIFIC.value: self._get_game_specific_value(user_data),
            AchievementRequirementType.SPECIAL.value: self._check_special_requirement(user_data),
        }
        
        return mapping.get(self.requirement_type, 0)
    
    def _get_game_specific_value(self, user_data: Dict[str, Any]) -> Any:
        """Get value for game-specific requirements"""
        game_type = self.requirement_metadata.get('game_type')
        if not game_type:
            return 0
        
        # Check for game-specific data
        game_specific = user_data.get('game_specific', {})
        return game_specific.get(game_type, 0)
    
    def _check_special_requirement(self, user_data: Dict[str, Any]) -> bool:
        """Check special requirements"""
        # Implement special achievement logic here
        # This could include things like:
        # - Perfect game score
        # - Achieve multiple conditions
        # - Rare accomplishments
        special_type = self.requirement_metadata.get('special_type')
        
        if special_type == "perfect_game":
            return user_data.get('score', 0) == 100
        elif special_type == "all_games_played":
            return user_data.get('unique_games_played', 0) >= 5
        
        return False
    
    def to_dict(self, include_metadata: bool = False) -> Dict[str, Any]:
        """Convert achievement to dictionary"""
        data = {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "category": self.category,
            "category_display": self.category_display,
            "rarity": self.rarity,
            "rarity_emoji": self.rarity_emoji,
            "rarity_color": self.rarity_color,
            "display_name": self.display_name,
            "xp_reward": self.xp_reward,
            "points_reward": self.points_reward,
            "total_reward": self.total_reward,
            "difficulty": self.difficulty,
            "is_hidden": self.is_hidden,
            "display_order": self.display_order,
        }
        
        if include_metadata:
            data.update({
                "requirement_type": self.requirement_type,
                "requirement_value": self.requirement_value,
                "requirement_metadata": self.requirement_metadata,
                "bonus_metadata": self.bonus_metadata,
                "is_active": self.is_active,
                "created_at": self.created_at.isoformat() if self.created_at else None,
            })
        
        return data
    
    def __repr__(self) -> str:
        return f"<Achievement(id={self.id}, code={self.code}, name={self.name}, rarity={self.rarity})>"


# ==================== User Achievement Model ====================
class UserAchievement(Base):
    """User's unlocked achievements"""
    
    __tablename__ = "user_achievements"
    __table_args__ = (
        Index("idx_user_achievements_user", "user_id"),
        Index("idx_user_achievements_achievement", "achievement_id"),
        Index("idx_user_achievements_unlocked_at", "unlocked_at"),
        Index("idx_user_achievements_notified", "is_notified"),
        Index("idx_user_achievements_user_achievement", "user_id", "achievement_id"),
        UniqueConstraint('user_id', 'achievement_id', name='uq_user_achievement'),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    achievement_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("achievements.id", ondelete="CASCADE"), nullable=False)
    
    # Tracking
    progress: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Progress towards achievement
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Status
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_notified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    
    # Metadata
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Timestamps
    unlocked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="achievements")
    achievement: Mapped["Achievement"] = relationship("Achievement", back_populates="user_achievements")

    # ==================== Properties ====================
    
    @hybrid_property
    def is_unlocked(self) -> bool:
        """Check if achievement is unlocked"""
        return self.is_completed and self.unlocked_at is not None
    
    @hybrid_property
    def progress_percentage(self) -> float:
        """Get progress as percentage"""
        if self.is_unlocked:
            return 100.0
        if self.progress is None:
            return 0.0
        if self.achievement and self.achievement.requirement_value > 0:
            return min(100.0, (self.progress / self.achievement.requirement_value) * 100)
        return 0.0
    
    @hybrid_property
    def progress_text(self) -> str:
        """Get progress display text"""
        if self.is_unlocked:
            return "✅ Completed"
        if self.progress is not None:
            total = self.achievement.requirement_value
            return f"{self.progress}/{total}"
        return "Not started"
    
    @hybrid_property
    def time_to_unlock(self) -> Optional[str]:
        """Get time since unlock"""
        if self.unlocked_at:
            delta = datetime.utcnow() - self.unlocked_at
            if delta.days > 0:
                return f"{delta.days}d ago"
            elif delta.seconds > 3600:
                return f"{delta.seconds // 3600}h ago"
            elif delta.seconds > 60:
                return f"{delta.seconds // 60}m ago"
            else:
                return "Just now"
        return None

    # ==================== Methods ====================
    
    def unlock(self) -> None:
        """Mark achievement as unlocked"""
        self.is_completed = True
        self.unlocked_at = datetime.utcnow()
        self.completed_at = datetime.utcnow()
    
    def update_progress(self, progress: int) -> bool:
        """
        Update progress towards achievement
        
        Args:
            progress: Current progress value
            
        Returns:
            True if achievement was completed
        """
        self.progress = progress
        self.updated_at = datetime.utcnow()
        
        # Check if completed
        if not self.is_completed:
            if self.achievement.requirement_type == AchievementRequirementType.PERFECT_SCORE.value:
                if progress >= self.achievement.requirement_value:
                    self.unlock()
                    return True
            elif progress >= self.achievement.requirement_value:
                self.unlock()
                return True
        
        return False
    
    def mark_notified(self) -> None:
        """Mark achievement as notified to user"""
        self.is_notified = True
    
    def to_dict(self, include_achievement: bool = False) -> Dict[str, Any]:
        """Convert user achievement to dictionary"""
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "progress": self.progress,
            "progress_percentage": self.progress_percentage,
            "progress_text": self.progress_text,
            "is_completed": self.is_completed,
            "is_unlocked": self.is_unlocked,
            "is_notified": self.is_notified,
            "unlocked_at": self.unlocked_at.isoformat() if self.unlocked_at else None,
            "time_to_unlock": self.time_to_unlock,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        
        if include_achievement and self.achievement:
            data["achievement"] = self.achievement.to_dict()
        
        return data
    
    def __repr__(self) -> str:
        return f"<UserAchievement(id={self.id}, user_id={self.user_id}, achievement_id={self.achievement_id}, completed={self.is_completed})>"


# ==================== Predefined Achievements ====================
class AchievementFactory:
    """Factory for creating predefined achievements"""
    
    @staticmethod
    def get_default_achievements() -> List[Dict[str, Any]]:
        """Get list of default achievements to seed"""
        return [
            # Milestone Achievements
            {
                "code": "first_game",
                "name": "First Steps",
                "description": "Play your first game",
                "icon": "🎮",
                "category": AchievementCategory.MILESTONE.value,
                "rarity": AchievementRarity.COMMON.value,
                "requirement_type": AchievementRequirementType.GAMES_PLAYED.value,
                "requirement_value": 1,
                "xp_reward": 10,
                "points_reward": 5,
                "display_order": 1,
            },
            {
                "code": "first_win",
                "name": "First Victory",
                "description": "Win your first game",
                "icon": "🏆",
                "category": AchievementCategory.MILESTONE.value,
                "rarity": AchievementRarity.COMMON.value,
                "requirement_type": AchievementRequirementType.GAMES_WON.value,
                "requirement_value": 1,
                "xp_reward": 25,
                "points_reward": 10,
                "display_order": 2,
            },
            {
                "code": "game_explorer",
                "name": "Game Explorer",
                "description": "Play all 5 games",
                "icon": "🗺️",
                "category": AchievementCategory.MILESTONE.value,
                "rarity": AchievementRarity.RARE.value,
                "requirement_type": AchievementRequirementType.UNIQUE_GAMES.value,
                "requirement_value": 5,
                "xp_reward": 100,
                "points_reward": 50,
                "display_order": 3,
            },
            
            # Game Achievements
            {
                "code": "reaction_master",
                "name": "Speed Demon",
                "description": "Score 90+ in Reaction Challenge",
                "icon": "⚡",
                "category": AchievementCategory.GAME.value,
                "rarity": AchievementRarity.RARE.value,
                "requirement_type": AchievementRequirementType.SCORE.value,
                "requirement_value": 90,
                "xp_reward": 75,
                "points_reward": 50,
                "display_order": 4,
                "requirement_metadata": {"game_type": "reaction"},
            },
            {
                "code": "quiz_master",
                "name": "Quiz Master",
                "description": "Score 100 in Quick Quiz",
                "icon": "📚",
                "category": AchievementCategory.GAME.value,
                "rarity": AchievementRarity.EPIC.value,
                "requirement_type": AchievementRequirementType.SCORE.value,
                "requirement_value": 100,
                "xp_reward": 150,
                "points_reward": 100,
                "display_order": 5,
                "requirement_metadata": {"game_type": "quiz"},
            },
            {
                "code": "number_genius",
                "name": "Number Genius",
                "description": "Score 50+ in Number Rush",
                "icon": "🔢",
                "category": AchievementCategory.GAME.value,
                "rarity": AchievementRarity.RARE.value,
                "requirement_type": AchievementRequirementType.SCORE.value,
                "requirement_value": 50,
                "xp_reward": 75,
                "points_reward": 50,
                "display_order": 6,
                "requirement_metadata": {"game_type": "number_rush"},
            },
            {
                "code": "memory_champion",
                "name": "Memory Champion",
                "description": "Perfect score in Memory Challenge",
                "icon": "🧠",
                "category": AchievementCategory.GAME.value,
                "rarity": AchievementRarity.EPIC.value,
                "requirement_type": AchievementRequirementType.PERFECT_SCORE.value,
                "requirement_value": 1,
                "xp_reward": 150,
                "points_reward": 100,
                "display_order": 7,
                "requirement_metadata": {"game_type": "memory"},
            },
            {
                "code": "tap_legend",
                "name": "Tap Legend",
                "description": "Score 100+ in Tap Challenge",
                "icon": "👆",
                "category": AchievementCategory.GAME.value,
                "rarity": AchievementRarity.RARE.value,
                "requirement_type": AchievementRequirementType.SCORE.value,
                "requirement_value": 100,
                "xp_reward": 75,
                "points_reward": 50,
                "display_order": 8,
                "requirement_metadata": {"game_type": "tap"},
            },
            
            # Streak Achievements
            {
                "code": "weekly_warrior",
                "name": "7-Day Warrior",
                "description": "Maintain a 7-day streak",
                "icon": "🔥",
                "category": AchievementCategory.STREAK.value,
                "rarity": AchievementRarity.RARE.value,
                "requirement_type": AchievementRequirementType.STREAK.value,
                "requirement_value": 7,
                "xp_reward": 150,
                "points_reward": 100,
                "display_order": 9,
            },
            {
                "code": "monthly_legend",
                "name": "Monthly Legend",
                "description": "Maintain a 30-day streak",
                "icon": "🌟",
                "category": AchievementCategory.STREAK.value,
                "rarity": AchievementRarity.LEGENDARY.value,
                "requirement_type": AchievementRequirementType.STREAK.value,
                "requirement_value": 30,
                "xp_reward": 500,
                "points_reward": 300,
                "display_order": 10,
            },
            {
                "code": "yearly_champion",
                "name": "Yearly Champion",
                "description": "Maintain a 365-day streak",
                "icon": "👑",
                "category": AchievementCategory.STREAK.value,
                "rarity": AchievementRarity.MYTHIC.value,
                "requirement_type": AchievementRequirementType.STREAK.value,
                "requirement_value": 365,
                "xp_reward": 2000,
                "points_reward": 1000,
                "display_order": 11,
            },
            
            # Social Achievements
            {
                "code": "social_butterfly",
                "name": "Social Butterfly",
                "description": "Refer 5 friends",
                "icon": "🦋",
                "category": AchievementCategory.SOCIAL.value,
                "rarity": AchievementRarity.UNCOMMON.value,
                "requirement_type": AchievementRequirementType.REFERRALS.value,
                "requirement_value": 5,
                "xp_reward": 100,
                "points_reward": 75,
                "display_order": 12,
            },
            {
                "code": "influencer",
                "name": "Influencer",
                "description": "Refer 25 friends",
                "icon": "📣",
                "category": AchievementCategory.SOCIAL.value,
                "rarity": AchievementRarity.EPIC.value,
                "requirement_type": AchievementRequirementType.REFERRALS.value,
                "requirement_value": 25,
                "xp_reward": 300,
                "points_reward": 200,
                "display_order": 13,
            },
            {
                "code": "friend_challenger",
                "name": "Friend Challenger",
                "description": "Complete 10 friend challenges",
                "icon": "🤝",
                "category": AchievementCategory.SOCIAL.value,
                "rarity": AchievementRarity.RARE.value,
                "requirement_type": AchievementRequirementType.FRIEND_MATCHES.value,
                "requirement_value": 10,
                "xp_reward": 150,
                "points_reward": 100,
                "display_order": 14,
            },
            
            # Challenge Achievements
            {
                "code": "challenge_champion",
                "name": "Challenge Champion",
                "description": "Complete 20 daily challenges",
                "icon": "🎯",
                "category": AchievementCategory.CHALLENGE.value,
                "rarity": AchievementRarity.EPIC.value,
                "requirement_type": AchievementRequirementType.CHALLENGES_COMPLETED.value,
                "requirement_value": 20,
                "xp_reward": 200,
                "points_reward": 150,
                "display_order": 15,
            },
            
            # Progression Achievements
            {
                "code": "level_10",
                "name": "Rising Star",
                "description": "Reach level 10",
                "icon": "⭐",
                "category": AchievementCategory.PROGRESSION.value,
                "rarity": AchievementRarity.UNCOMMON.value,
                "requirement_type": AchievementRequirementType.LEVEL.value,
                "requirement_value": 10,
                "xp_reward": 100,
                "points_reward": 50,
                "display_order": 16,
            },
            {
                "code": "level_25",
                "name": "Pro Player",
                "description": "Reach level 25",
                "icon": "🎖️",
                "category": AchievementCategory.PROGRESSION.value,
                "rarity": AchievementRarity.RARE.value,
                "requirement_type": AchievementRequirementType.LEVEL.value,
                "requirement_value": 25,
                "xp_reward": 250,
                "points_reward": 150,
                "display_order": 17,
            },
            {
                "code": "level_50",
                "name": "Legendary Player",
                "description": "Reach level 50",
                "icon": "👑",
                "category": AchievementCategory.PROGRESSION.value,
                "rarity": AchievementRarity.LEGENDARY.value,
                "requirement_type": AchievementRequirementType.LEVEL.value,
                "requirement_value": 50,
                "xp_reward": 500,
                "points_reward": 300,
                "display_order": 18,
            },
            {
                "code": "level_100",
                "name": "Ultimate Legend",
                "description": "Reach level 100",
                "icon": "🌟",
                "category": AchievementCategory.PROGRESSION.value,
                "rarity": AchievementRarity.MYTHIC.value,
                "requirement_type": AchievementRequirementType.LEVEL.value,
                "requirement_value": 100,
                "xp_reward": 1000,
                "points_reward": 500,
                "display_order": 19,
            },
            
            # Competitive Achievements
            {
                "code": "top_100",
                "name": "Top 100 Player",
                "description": "Reach top 100 on global leaderboard",
                "icon": "🏅",
                "category": AchievementCategory.COMPETITIVE.value,
                "rarity": AchievementRarity.RARE.value,
                "requirement_type": AchievementRequirementType.SPECIAL.value,
                "requirement_value": 1,
                "xp_reward": 200,
                "points_reward": 150,
                "display_order": 20,
                "requirement_metadata": {"special_type": "top_100"},
            },
        ]


# ==================== Model Registration ====================
__all__ = [
    "AchievementCategory",
    "AchievementRarity",
    "AchievementRequirementType",
    "Achievement",
    "UserAchievement",
    "AchievementFactory",
]
