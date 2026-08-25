"""
Achievement Repository for GamePulse Bot
Handles all database operations related to achievements and user achievements
"""

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy import select, update, delete, func, and_, or_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from src.models.achievement import (
    Achievement,
    UserAchievement,
    AchievementCategory,
    AchievementRarity,
    AchievementRequirementType,
    AchievementFactory
)
from src.models.user import User
from src.models.game import GameSession
from src.core.exceptions import (
    AchievementNotFoundError,
    AchievementAlreadyUnlockedError,
    DatabaseError
)
from src.core.config import settings
from src.core.redis import redis_manager


class AchievementRepository:
    """Repository for achievement-related database operations"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    # ==================== Achievement CRUD Operations ====================
    
    async def create_achievement(
        self,
        code: str,
        name: str,
        description: str,
        requirement_type: str,
        requirement_value: int,
        category: str = AchievementCategory.MILESTONE.value,
        rarity: str = AchievementRarity.COMMON.value,
        icon: Optional[str] = None,
        xp_reward: int = 0,
        points_reward: int = 0,
        requirement_metadata: Optional[Dict[str, Any]] = None,
        bonus_metadata: Optional[Dict[str, Any]] = None,
        is_hidden: bool = False,
        display_order: int = 0
    ) -> Achievement:
        """
        Create a new achievement
        
        Args:
            code: Unique achievement code
            name: Achievement name
            description: Achievement description
            requirement_type: Type of requirement
            requirement_value: Value required
            category: Achievement category
            rarity: Achievement rarity
            icon: Achievement icon (emoji)
            xp_reward: XP reward
            points_reward: Points reward
            requirement_metadata: Additional requirement metadata
            bonus_metadata: Additional bonus metadata
            is_hidden: Whether achievement is hidden
            display_order: Display order
        
        Returns:
            Created Achievement object
        """
        achievement = Achievement(
            code=code,
            name=name,
            description=description,
            category=category,
            rarity=rarity,
            icon=icon,
            requirement_type=requirement_type,
            requirement_value=requirement_value,
            requirement_metadata=requirement_metadata or {},
            xp_reward=xp_reward,
            points_reward=points_reward,
            bonus_metadata=bonus_metadata or {},
            is_hidden=is_hidden,
            display_order=display_order,
            is_active=True
        )
        
        self.session.add(achievement)
        await self.session.flush()
        
        return achievement
    
    async def get_achievement_by_id(self, achievement_id: int) -> Optional[Achievement]:
        """
        Get achievement by ID
        
        Args:
            achievement_id: Achievement ID
        
        Returns:
            Achievement object or None
        """
        query = select(Achievement).where(Achievement.id == achievement_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_achievement_by_code(self, code: str) -> Optional[Achievement]:
        """
        Get achievement by code
        
        Args:
            code: Achievement code
        
        Returns:
            Achievement object or None
        """
        query = select(Achievement).where(Achievement.code == code)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_all_achievements(
        self,
        category: Optional[str] = None,
        rarity: Optional[str] = None,
        include_hidden: bool = False,
        limit: int = 100,
        offset: int = 0
    ) -> Tuple[List[Achievement], int]:
        """
        Get all achievements with filters
        
        Args:
            category: Filter by category
            rarity: Filter by rarity
            include_hidden: Include hidden achievements
            limit: Number of results
            offset: Offset for pagination
        
        Returns:
            Tuple of (achievements, total count)
        """
        query = select(Achievement).where(Achievement.is_active == True)
        
        if category:
            query = query.where(Achievement.category == category)
        
        if rarity:
            query = query.where(Achievement.rarity == rarity)
        
        if not include_hidden:
            query = query.where(Achievement.is_hidden == False)
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        result = await self.session.execute(count_query)
        total = result.scalar() or 0
        
        # Apply pagination and order
        query = query.order_by(
            Achievement.display_order,
            Achievement.rarity,
            Achievement.name
        ).offset(offset).limit(limit)
        
        result = await self.session.execute(query)
        achievements = result.scalars().all()
        
        return achievements, total
    
    async def update_achievement(
        self,
        achievement_id: int,
        **kwargs
    ) -> Achievement:
        """
        Update an achievement
        
        Args:
            achievement_id: Achievement ID
            **kwargs: Fields to update
        
        Returns:
            Updated Achievement object
        """
        achievement = await self.get_achievement_by_id(achievement_id)
        if not achievement:
            raise AchievementNotFoundError(achievement_id)
        
        for key, value in kwargs.items():
            if hasattr(achievement, key):
                setattr(achievement, key, value)
        
        achievement.updated_at = datetime.utcnow()
        await self.session.flush()
        
        return achievement
    
    async def delete_achievement(self, achievement_id: int) -> bool:
        """
        Delete an achievement (soft delete)
        
        Args:
            achievement_id: Achievement ID
        
        Returns:
            True if deleted
        """
        achievement = await self.get_achievement_by_id(achievement_id)
        if not achievement:
            raise AchievementNotFoundError(achievement_id)
        
        achievement.is_active = False
        await self.session.flush()
        
        return True
    
    # ==================== User Achievement Operations ====================
    
    async def get_user_achievement(
        self,
        user_id: int,
        achievement_id: int
    ) -> Optional[UserAchievement]:
        """
        Get user's achievement record
        
        Args:
            user_id: User ID
            achievement_id: Achievement ID
        
        Returns:
            UserAchievement object or None
        """
        query = select(UserAchievement).where(
            UserAchievement.user_id == user_id,
            UserAchievement.achievement_id == achievement_id
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_user_achievements(
        self,
        user_id: int,
        completed_only: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[UserAchievement], int]:
        """
        Get user's achievements
        
        Args:
            user_id: User ID
            completed_only: Only return completed achievements
            limit: Number of results
            offset: Offset for pagination
        
        Returns:
            Tuple of (user_achievements, total count)
        """
        query = select(UserAchievement).where(
            UserAchievement.user_id == user_id
        ).options(
            joinedload(UserAchievement.achievement)
        )
        
        if completed_only:
            query = query.where(UserAchievement.is_completed == True)
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        result = await self.session.execute(count_query)
        total = result.scalar() or 0
        
        # Apply pagination and order
        query = query.order_by(
            desc(UserAchievement.unlocked_at),
            desc(UserAchievement.is_completed)
        ).offset(offset).limit(limit)
        
        result = await self.session.execute(query)
        user_achievements = result.scalars().all()
        
        return user_achievements, total
    
    async def get_unlocked_achievements(self, user_id: int) -> List[Achievement]:
        """
        Get all unlocked achievements for a user
        
        Args:
            user_id: User ID
        
        Returns:
            List of Achievement objects
        """
        query = select(Achievement).join(
            UserAchievement,
            and_(
                UserAchievement.achievement_id == Achievement.id,
                UserAchievement.user_id == user_id,
                UserAchievement.is_completed == True
            )
        )
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def get_achievement_progress(
        self,
        user_id: int,
        achievement_id: int
    ) -> Dict[str, Any]:
        """
        Get user's progress towards an achievement
        
        Args:
            user_id: User ID
            achievement_id: Achievement ID
        
        Returns:
            Dictionary with progress information
        """
        achievement = await self.get_achievement_by_id(achievement_id)
        if not achievement:
            raise AchievementNotFoundError(achievement_id)
        
        user_achievement = await self.get_user_achievement(user_id, achievement_id)
        
        if user_achievement and user_achievement.is_completed:
            return {
                "achievement_id": achievement_id,
                "is_completed": True,
                "progress": achievement.requirement_value,
                "target": achievement.requirement_value,
                "percentage": 100,
                "unlocked_at": user_achievement.unlocked_at.isoformat() if user_achievement.unlocked_at else None
            }
        
        # Calculate current progress
        current_progress = await self._calculate_progress(user_id, achievement)
        
        if user_achievement:
            user_achievement.progress = min(current_progress, achievement.requirement_value)
            await self.session.flush()
        else:
            user_achievement = UserAchievement(
                user_id=user_id,
                achievement_id=achievement_id,
                progress=min(current_progress, achievement.requirement_value),
                is_completed=False
            )
            self.session.add(user_achievement)
            await self.session.flush()
        
        return {
            "achievement_id": achievement_id,
            "is_completed": False,
            "progress": min(current_progress, achievement.requirement_value),
            "target": achievement.requirement_value,
            "percentage": min(100, (current_progress / achievement.requirement_value) * 100)
        }
    
    async def check_and_unlock_achievements(
        self,
        user_id: int,
        user_data: Dict[str, Any]
    ) -> List[Achievement]:
        """
        Check all achievements and unlock any that are completed
        
        Args:
            user_id: User ID
            user_data: User data for checking requirements
        
        Returns:
            List of newly unlocked achievements
        """
        unlocked = []
        
        # Get all active achievements
        query = select(Achievement).where(Achievement.is_active == True)
        result = await self.session.execute(query)
        achievements = result.scalars().all()
        
        for achievement in achievements:
            # Check if already unlocked
            user_achievement = await self.get_user_achievement(user_id, achievement.id)
            if user_achievement and user_achievement.is_completed:
                continue
            
            # Check requirement
            if achievement.check_requirement(user_data):
                # Unlock achievement
                if not user_achievement:
                    user_achievement = UserAchievement(
                        user_id=user_id,
                        achievement_id=achievement.id,
                        progress=achievement.requirement_value
                    )
                    self.session.add(user_achievement)
                
                user_achievement.unlock()
                await self.session.flush()
                
                # Grant rewards
                await self._grant_achievement_rewards(user_id, achievement)
                
                unlocked.append(achievement)
        
        return unlocked
    
    async def grant_achievement(
        self,
        user_id: int,
        achievement_id: int,
        admin_id: Optional[int] = None
    ) -> Achievement:
        """
        Manually grant an achievement to a user (admin only)
        
        Args:
            user_id: User ID
            achievement_id: Achievement ID
            admin_id: Admin granting the achievement
        
        Returns:
            Granted Achievement
        """
        achievement = await self.get_achievement_by_id(achievement_id)
        if not achievement:
            raise AchievementNotFoundError(achievement_id)
        
        user_achievement = await self.get_user_achievement(user_id, achievement_id)
        if user_achievement and user_achievement.is_completed:
            raise AchievementAlreadyUnlockedError(achievement_id, user_id)
        
        if not user_achievement:
            user_achievement = UserAchievement(
                user_id=user_id,
                achievement_id=achievement_id,
                progress=achievement.requirement_value
            )
            self.session.add(user_achievement)
        
        user_achievement.unlock()
        await self.session.flush()
        
        # Grant rewards
        await self._grant_achievement_rewards(user_id, achievement)
        
        return achievement
    
    async def revoke_achievement(
        self,
        user_id: int,
        achievement_id: int,
        admin_id: Optional[int] = None
    ) -> bool:
        """
        Revoke an achievement from a user (admin only)
        
        Args:
            user_id: User ID
            achievement_id: Achievement ID
            admin_id: Admin revoking the achievement
        
        Returns:
            True if revoked
        """
        user_achievement = await self.get_user_achievement(user_id, achievement_id)
        if not user_achievement:
            return False
        
        if not user_achievement.is_completed:
            return False
        
        # Remove achievement
        await self.session.delete(user_achievement)
        await self.session.flush()
        
        return True
    
    # ==================== Helper Methods ====================
    
    async def _calculate_progress(
        self,
        user_id: int,
        achievement: Achievement
    ) -> int:
        """
        Calculate user's progress towards an achievement
        
        Args:
            user_id: User ID
            achievement: Achievement object
        
        Returns:
            Current progress value
        """
        requirement_type = achievement.requirement_type
        
        if requirement_type == AchievementRequirementType.GAMES_PLAYED.value:
            query = select(func.count(GameSession.id)).where(
                GameSession.user_id == user_id,
                GameSession.is_valid == True,
                GameSession.status == "completed"
            )
            result = await self.session.execute(query)
            return result.scalar() or 0
        
        elif requirement_type == AchievementRequirementType.GAMES_WON.value:
            # This requires user stats - simplified version
            query = select(User.games_won).where(User.id == user_id)
            result = await self.session.execute(query)
            return result.scalar() or 0
        
        elif requirement_type == AchievementRequirementType.SCORE.value:
            # Get best score for specific game if specified
            game_type = achievement.requirement_metadata.get('game_type')
            if game_type:
                query = select(GameSession.score).where(
                    GameSession.user_id == user_id,
                    GameSession.game_type == game_type,
                    GameSession.is_valid == True,
                    GameSession.status == "completed"
                ).order_by(desc(GameSession.score)).limit(1)
                result = await self.session.execute(query)
                return result.scalar() or 0
            else:
                # Overall best score
                query = select(func.max(GameSession.score)).where(
                    GameSession.user_id == user_id,
                    GameSession.is_valid == True,
                    GameSession.status == "completed"
                )
                result = await self.session.execute(query)
                return result.scalar() or 0
        
        elif requirement_type == AchievementRequirementType.STREAK.value:
            query = select(User.current_streak).where(User.id == user_id)
            result = await self.session.execute(query)
            return result.scalar() or 0
        
        elif requirement_type == AchievementRequirementType.LEVEL.value:
            query = select(User.level).where(User.id == user_id)
            result = await self.session.execute(query)
            return result.scalar() or 0
        
        elif requirement_type == AchievementRequirementType.XP.value:
            query = select(User.xp).where(User.id == user_id)
            result = await self.session.execute(query)
            return result.scalar() or 0
        
        elif requirement_type == AchievementRequirementType.POINTS.value:
            query = select(User.pulse_points).where(User.id == user_id)
            result = await self.session.execute(query)
            return result.scalar() or 0
        
        elif requirement_type == AchievementRequirementType.REFERRALS.value:
            query = select(User.referral_count).where(User.id == user_id)
            result = await self.session.execute(query)
            return result.scalar() or 0
        
        elif requirement_type == AchievementRequirementType.CHALLENGES_COMPLETED.value:
            from src.models.challenge import DailyChallengeCompletion
            query = select(func.count(DailyChallengeCompletion.id)).where(
                DailyChallengeCompletion.user_id == user_id,
                DailyChallengeCompletion.status == "completed"
            )
            result = await self.session.execute(query)
            return result.scalar() or 0
        
        elif requirement_type == AchievementRequirementType.UNIQUE_GAMES.value:
            query = select(func.count(func.distinct(GameSession.game_type))).where(
                GameSession.user_id == user_id,
                GameSession.is_valid == True,
                GameSession.status == "completed"
            )
            result = await self.session.execute(query)
            return result.scalar() or 0
        
        elif requirement_type == AchievementRequirementType.FRIEND_MATCHES.value:
            from src.models.friend_match import FriendMatch
            query = select(func.count(FriendMatch.id)).where(
                or_(
                    FriendMatch.challenger_id == user_id,
                    FriendMatch.opponent_id == user_id
                ),
                FriendMatch.status == "completed"
            )
            result = await self.session.execute(query)
            return result.scalar() or 0
        
        elif requirement_type == AchievementRequirementType.FRIEND_MATCHES_WON.value:
            from src.models.friend_match import FriendMatch
            query = select(func.count(FriendMatch.id)).where(
                FriendMatch.winner_id == user_id
            )
            result = await self.session.execute(query)
            return result.scalar() or 0
        
        elif requirement_type == AchievementRequirementType.ACHIEVEMENTS_UNLOCKED.value:
            query = select(func.count(UserAchievement.id)).where(
                UserAchievement.user_id == user_id,
                UserAchievement.is_completed == True
            )
            result = await self.session.execute(query)
            return result.scalar() or 0
        
        elif requirement_type == AchievementRequirementType.PERFECT_SCORE.value:
            game_type = achievement.requirement_metadata.get('game_type')
            if game_type:
                query = select(func.count(GameSession.id)).where(
                    GameSession.user_id == user_id,
                    GameSession.game_type == game_type,
                    GameSession.score == 100,
                    GameSession.is_valid == True,
                    GameSession.status == "completed"
                )
                result = await self.session.execute(query)
                return result.scalar() or 0
            else:
                query = select(func.count(GameSession.id)).where(
                    GameSession.user_id == user_id,
                    GameSession.score == 100,
                    GameSession.is_valid == True,
                    GameSession.status == "completed"
                )
                result = await self.session.execute(query)
                return result.scalar() or 0
        
        elif requirement_type == AchievementRequirementType.GAME_SPECIFIC.value:
            game_type = achievement.requirement_metadata.get('game_type')
            if game_type:
                query = select(func.count(GameSession.id)).where(
                    GameSession.user_id == user_id,
                    GameSession.game_type == game_type,
                    GameSession.is_valid == True,
                    GameSession.status == "completed"
                )
                result = await self.session.execute(query)
                return result.scalar() or 0
        
        return 0
    
    async def _grant_achievement_rewards(
        self,
        user_id: int,
        achievement: Achievement
    ) -> None:
        """
        Grant rewards for an unlocked achievement
        
        Args:
            user_id: User ID
            achievement: Achievement object
        """
        from src.repositories.user_repo import UserRepository
        from src.models.user import PointTransaction, Notification
        
        user_repo = UserRepository(self.session)
        
        # Update user stats
        xp_reward = int(achievement.xp_reward * settings.ACHIEVEMENT_XP_MULTIPLIER)
        points_reward = int(achievement.points_reward * settings.ACHIEVEMENT_POINTS_MULTIPLIER)
        
        await user_repo.update_stats(
            user_id=user_id,
            xp_gained=xp_reward,
            points_gained=points_reward
        )
        
        # Create transaction
        transaction = PointTransaction.create_achievement_reward(
            user_id=user_id,
            amount=points_reward,
            achievement_id=achievement.id,
            description=f"Achievement reward: {points_reward} points for {achievement.name}"
        )
        self.session.add(transaction)
        
        # Create notification
        notification = Notification.create_achievement_unlocked(
            user_id=user_id,
            achievement_name=achievement.name,
            achievement_icon=achievement.icon or "🏆",
            xp_reward=xp_reward,
            points_reward=points_reward,
            metadata={
                "achievement_id": achievement.id,
                "achievement_code": achievement.code,
                "category": achievement.category,
                "rarity": achievement.rarity
            }
        )
        self.session.add(notification)
        
        await self.session.flush()
    
    # ==================== Seeding Operations ====================
    
    async def seed_default_achievements(self) -> int:
        """
        Seed default achievements from AchievementFactory
        
        Returns:
            Number of achievements created
        """
        default_achievements = AchievementFactory.get_default_achievements()
        
        count = 0
        for ach_data in default_achievements:
            # Check if achievement already exists
            existing = await self.get_achievement_by_code(ach_data['code'])
            if existing:
                continue
            
            achievement = await self.create_achievement(**ach_data)
            count += 1
        
        return count
    
    # ==================== Analytics Operations ====================
    
    async def get_achievement_stats(self) -> Dict[str, Any]:
        """
        Get achievement statistics
        
        Returns:
            Dictionary with achievement stats
        """
        # Total achievements
        total_query = select(func.count(Achievement.id)).where(
            Achievement.is_active == True
        )
        result = await self.session.execute(total_query)
        total = result.scalar() or 0
        
        # By category
        category_query = select(
            Achievement.category,
            func.count(Achievement.id)
        ).where(
            Achievement.is_active == True
        ).group_by(Achievement.category)
        result = await self.session.execute(category_query)
        by_category = {row[0]: row[1] for row in result.all()}
        
        # By rarity
        rarity_query = select(
            Achievement.rarity,
            func.count(Achievement.id)
        ).where(
            Achievement.is_active == True
        ).group_by(Achievement.rarity)
        result = await self.session.execute(rarity_query)
        by_rarity = {row[0]: row[1] for row in result.all()}
        
        # Total unlocked achievements
        unlocked_query = select(func.count(UserAchievement.id)).where(
            UserAchievement.is_completed == True
        )
        result = await self.session.execute(unlocked_query)
        unlocked_total = result.scalar() or 0
        
        # Most unlocked achievements
        popular_query = select(
            Achievement.name,
            func.count(UserAchievement.id).label("count")
        ).join(
            UserAchievement,
            UserAchievement.achievement_id == Achievement.id
        ).where(
            UserAchievement.is_completed == True
        ).group_by(
            Achievement.id,
            Achievement.name
        ).order_by(desc("count")).limit(10)
        
        result = await self.session.execute(popular_query)
        most_popular = [{"name": row[0], "count": row[1]} for row in result.all()]
        
        return {
            "total_achievements": total,
            "by_category": by_category,
            "by_rarity": by_rarity,
            "total_unlocked": unlocked_total,
            "most_popular": most_popular
        }
    
    async def get_user_achievement_stats(self, user_id: int) -> Dict[str, Any]:
        """
        Get user's achievement statistics
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary with user achievement stats
        """
        # Total achievements unlocked
        unlocked_query = select(func.count(UserAchievement.id)).where(
            UserAchievement.user_id == user_id,
            UserAchievement.is_completed == True
        )
        result = await self.session.execute(unlocked_query)
        unlocked = result.scalar() or 0
        
        # Total achievements available
        total_query = select(func.count(Achievement.id)).where(
            Achievement.is_active == True,
            Achievement.is_hidden == False
        )
        result = await self.session.execute(total_query)
        total = result.scalar() or 0
        
        # By category
        category_query = select(
            Achievement.category,
            func.count(UserAchievement.id)
        ).join(
            UserAchievement,
            UserAchievement.achievement_id == Achievement.id
        ).where(
            UserAchievement.user_id == user_id,
            UserAchievement.is_completed == True
        ).group_by(Achievement.category)
        result = await self.session.execute(category_query)
        by_category = {row[0]: row[1] for row in result.all()}
        
        # By rarity
        rarity_query = select(
            Achievement.rarity,
            func.count(UserAchievement.id)
        ).join(
            UserAchievement,
            UserAchievement.achievement_id == Achievement.id
        ).where(
            UserAchievement.user_id == user_id,
            UserAchievement.is_completed == True
        ).group_by(Achievement.rarity)
        result = await self.session.execute(rarity_query)
        by_rarity = {row[0]: row[1] for row in result.all()}
        
        # Recently unlocked
        recent_query = select(UserAchievement).where(
            UserAchievement.user_id == user_id,
            UserAchievement.is_completed == True
        ).options(
            joinedload(UserAchievement.achievement)
        ).order_by(desc(UserAchievement.unlocked_at)).limit(5)
        result = await self.session.execute(recent_query)
        recent = result.scalars().all()
        
        # Calculate completion percentage
        completion_percentage = 0
        if total > 0:
            completion_percentage = (unlocked / total) * 100
        
        return {
            "unlocked": unlocked,
            "total": total,
            "completion_percentage": completion_percentage,
            "by_category": by_category,
            "by_rarity": by_rarity,
            "recent_unlocked": [
                {
                    "name": ua.achievement.name,
                    "icon": ua.achievement.icon,
                    "rarity": ua.achievement.rarity,
                    "unlocked_at": ua.unlocked_at.isoformat() if ua.unlocked_at else None
                }
                for ua in recent
            ]
        }
