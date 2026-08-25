"""
User Repository for GamePulse Bot
Handles all database operations related to users, profiles, and user data
"""

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta, date
from sqlalchemy import select, update, delete, func, and_, or_, desc, asc, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.sql.expression import case

from src.models.user import (
    User, 
    BestScore, 
    PointTransaction, 
    Notification,
    UserActivityLog,
    UserReferral,
    UserStatsSnapshot
)
from src.models.game import GameSession, GameType
from src.core.exceptions import (
    UserNotFoundError,
    UserBannedError,
    UserNotRegisteredError,
    UserAlreadyExistsError,
    DatabaseError
)
from src.core.config import settings
from src.core.redis import redis_manager


class UserRepository:
    """Repository for user-related database operations"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    # ==================== User CRUD Operations ====================
    
    async def create_user(
        self,
        telegram_id: int,
        first_name: str,
        username: Optional[str] = None,
        last_name: Optional[str] = None,
        referred_by_id: Optional[int] = None,
        referral_code: Optional[str] = None
    ) -> User:
        """
        Create a new user
        
        Args:
            telegram_id: User's Telegram ID
            first_name: User's first name
            username: User's Telegram username
            last_name: User's last name
            referred_by_id: ID of user who referred this user
            referral_code: Custom referral code (auto-generated if not provided)
        
        Returns:
            Created User object
        """
        # Check if user already exists
        existing = await self.get_by_telegram_id(telegram_id)
        if existing:
            raise UserAlreadyExistsError(telegram_id)
        
        # Generate unique referral code if not provided
        if not referral_code:
            referral_code = self._generate_referral_code()
            # Ensure uniqueness
            while await self.get_by_referral_code(referral_code):
                referral_code = self._generate_referral_code()
        
        # Create user
        user = User(
            telegram_id=telegram_id,
            first_name=first_name,
            last_name=last_name,
            username=username,
            display_name=f"{first_name} {last_name}" if last_name else first_name,
            referral_code=referral_code,
            referred_by_id=referred_by_id,
            registered_at=datetime.utcnow(),
            last_active_at=datetime.utcnow(),
            settings={
                "notifications": True,
                "language": "en",
                "timezone": "UTC",
                "privacy": {
                    "show_username": True,
                    "show_avatar": True,
                    "show_stats": True
                }
            }
        )
        
        self.session.add(user)
        await self.session.flush()
        
        # Create welcome notification
        welcome_notification = Notification(
            user_id=user.id,
            notification_type="welcome",
            title="🎮 Welcome to GamePulse!",
            message=f"Welcome {user.first_name}! Start your gaming journey today.\n\n"
                   f"Complete your first game to earn XP and Pulse Points!",
            short_message="Welcome to GamePulse!",
            priority="high",
            data={"action": "welcome", "username": user.username},
            buttons=[
                {"text": "🎮 Play Games", "callback_data": "games_menu"},
                {"text": "📖 Help", "callback_data": "help"}
            ]
        )
        self.session.add(welcome_notification)
        
        # Log user registration
        await self._log_activity(
            user_id=user.id,
            action="register",
            details={"telegram_id": telegram_id, "username": username}
        )
        
        await self.session.flush()
        
        # Clear cache
        await self._clear_user_cache(telegram_id)
        
        return user
    
    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """
        Get user by Telegram ID
        
        Args:
            telegram_id: User's Telegram ID
        
        Returns:
            User object or None if not found
        """
        # Try cache first
        cache_key = f"user:telegram:{telegram_id}"
        cached = await redis_manager.get(cache_key)
        if cached:
            # Cache hit - return user from cache (would need to materialize)
            pass
        
        query = select(User).where(User.telegram_id == telegram_id)
        result = await self.session.execute(query)
        user = result.scalar_one_or_none()
        
        if user:
            # Cache the user
            await redis_manager.set(
                cache_key,
                {"id": user.id, "telegram_id": user.telegram_id},
                ttl=300
            )
        
        return user
    
    async def get_by_id(self, user_id: int, load_relations: bool = False) -> Optional[User]:
        """
        Get user by ID
        
        Args:
            user_id: User ID
            load_relations: Whether to load related data
        
        Returns:
            User object or None if not found
        """
        query = select(User).where(User.id == user_id)
        
        if load_relations:
            query = query.options(
                selectinload(User.best_scores),
                selectinload(User.achievements),
                selectinload(User.point_transactions).limit(10)
            )
        
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_by_referral_code(self, referral_code: str) -> Optional[User]:
        """
        Get user by referral code
        
        Args:
            referral_code: User's referral code
        
        Returns:
            User object or None if not found
        """
        query = select(User).where(User.referral_code == referral_code)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_by_username(self, username: str) -> Optional[User]:
        """
        Get user by username
        
        Args:
            username: User's username
        
        Returns:
            User object or None if not found
        """
        query = select(User).where(User.username == username)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_or_create_user(
        self,
        telegram_id: int,
        first_name: str,
        username: Optional[str] = None,
        last_name: Optional[str] = None,
        referred_by_id: Optional[int] = None
    ) -> User:
        """
        Get user or create if not exists
        
        Args:
            telegram_id: User's Telegram ID
            first_name: User's first name
            username: User's Telegram username
            last_name: User's last name
            referred_by_id: ID of user who referred this user
        
        Returns:
            User object
        """
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            # Update last active
            await self.update_last_active(user.id)
            return user
        
        # Create new user
        return await self.create_user(
            telegram_id=telegram_id,
            first_name=first_name,
            username=username,
            last_name=last_name,
            referred_by_id=referred_by_id
        )
    
    # ==================== User Update Operations ====================
    
    async def update_user(
        self,
        user_id: int,
        **kwargs
    ) -> User:
        """
        Update user fields
        
        Args:
            user_id: User ID
            **kwargs: Fields to update
        
        Returns:
            Updated User object
        """
        user = await self.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(user_id)
        
        # Update fields
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        
        user.updated_at = datetime.utcnow()
        await self.session.flush()
        
        # Clear cache
        await self._clear_user_cache(user.telegram_id)
        
        return user
    
    async def update_last_active(self, user_id: int) -> None:
        """Update user's last active timestamp"""
        user = await self.get_by_id(user_id)
        if user:
            user.last_active_at = datetime.utcnow()
            await self.session.flush()
            await self._clear_user_cache(user.telegram_id)
    
    async def update_settings(
        self,
        user_id: int,
        settings_update: Dict[str, Any]
    ) -> User:
        """
        Update user settings
        
        Args:
            user_id: User ID
            settings_update: Settings to update
        
        Returns:
            Updated User object
        """
        user = await self.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(user_id)
        
        if not user.settings:
            user.settings = {}
        
        # Deep merge settings
        self._deep_merge(user.settings, settings_update)
        user.updated_at = datetime.utcnow()
        await self.session.flush()
        
        await self._clear_user_cache(user.telegram_id)
        
        return user
    
    async def update_stats(
        self,
        user_id: int,
        xp_gained: int = 0,
        points_gained: int = 0,
        games_played_increment: int = 0,
        games_won_increment: int = 0,
        score_increment: int = 0,
        completed_challenge: bool = False
    ) -> Dict[str, Any]:
        """
        Update user statistics
        
        Args:
            user_id: User ID
            xp_gained: XP to add
            points_gained: Points to add
            games_played_increment: Games played increment
            games_won_increment: Games won increment
            score_increment: Total score increment
            completed_challenge: Whether a challenge was completed
        
        Returns:
            Dictionary with update results (level_up, etc.)
        """
        user = await self.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(user_id)
        
        result = {
            "level_up": False,
            "old_level": user.level,
            "new_level": user.level,
            "streak_updated": False,
            "streak_bonus": 0
        }
        
        # Update XP and check level up
        if xp_gained > 0:
            old_level = user.level
            user.xp += xp_gained
            user.updated_at = datetime.utcnow()
            
            # Check for level ups
            levels_gained = 0
            while user.xp >= user.xp_to_next_level and user.level < settings.XP_MAX_LEVEL:
                user.level += 1
                levels_gained += 1
                # Level up bonus
                bonus_points = settings.XP_LEVEL_UP_BONUS_POINTS
                user.pulse_points += bonus_points
                
                # Create level up transaction
                transaction = PointTransaction.create_level_up(
                    user_id=user.id,
                    amount=bonus_points,
                    level=user.level,
                    description=f"Level up bonus: {bonus_points} points for reaching level {user.level}"
                )
                self.session.add(transaction)
                
                # Create level up notification
                notification = Notification.create_level_up(
                    user_id=user.id,
                    level=user.level,
                    bonus_points=bonus_points
                )
                self.session.add(notification)
            
            if levels_gained > 0:
                result["level_up"] = True
                result["new_level"] = user.level
                result["levels_gained"] = levels_gained
        
        # Update points
        if points_gained > 0:
            user.pulse_points += points_gained
        
        # Update games played
        if games_played_increment > 0:
            user.games_played += games_played_increment
        
        # Update games won
        if games_won_increment > 0:
            user.games_won += games_won_increment
        
        # Update total score
        if score_increment > 0:
            user.total_score += score_increment
            if user.games_played > 0:
                user.average_score = user.total_score / user.games_played
        
        # Update streak
        if games_played_increment > 0:
            streak_result = await self.update_streak(user_id)
            result["streak_updated"] = True
            result["streak_bonus"] = streak_result.get("bonus", 0)
            result["current_streak"] = streak_result.get("current_streak", 0)
        
        await self.session.flush()
        await self._clear_user_cache(user.telegram_id)
        
        return result
    
    # ==================== User Query Operations ====================
    
    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """
        Get comprehensive user statistics
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary with user stats
        """
        user = await self.get_by_id(user_id, load_relations=True)
        if not user:
            raise UserNotFoundError(user_id)
        
        # Get game sessions stats
        query = select(
            func.count(GameSession.id).label("total_games"),
            func.avg(GameSession.score).label("avg_score"),
            func.sum(GameSession.xp_earned).label("total_xp"),
            func.sum(GameSession.points_earned).label("total_points"),
            func.max(GameSession.score).label("highest_score"),
        ).where(
            GameSession.user_id == user_id,
            GameSession.is_valid == True,
            GameSession.status == "completed"
        )
        result = await self.session.execute(query)
        stats = result.one()
        
        # Get best scores by game type
        query = select(BestScore).where(BestScore.user_id == user_id)
        result = await self.session.execute(query)
        best_scores = result.scalars().all()
        
        best_scores_by_game = {
            score.game_type: score.score for score in best_scores
        }
        
        # Get recent games
        query = select(GameSession).where(
            GameSession.user_id == user_id,
            GameSession.status == "completed"
        ).order_by(desc(GameSession.completed_at)).limit(10)
        result = await self.session.execute(query)
        recent_games = result.scalars().all()
        
        # Get achievement count
        query = select(func.count()).where(
            User.achievements.any(completed=True)
        )
        result = await self.session.execute(query)
        achievement_count = result.scalar() or 0
        
        # Calculate level progress
        xp_for_current = (user.level - 1) * settings.XP_PER_LEVEL
        xp_for_next = user.level * settings.XP_PER_LEVEL
        level_progress = 0
        if xp_for_next > xp_for_current:
            level_progress = (user.xp - xp_for_current) / (xp_for_next - xp_for_current) * 100
        level_progress = min(100, max(0, level_progress))
        
        return {
            "user": {
                "id": user.id,
                "telegram_id": user.telegram_id,
                "username": user.username,
                "display_name": user.full_name,
                "level": user.level,
                "xp": user.xp,
                "xp_to_next": user.xp_to_next_level,
                "level_progress": level_progress,
                "pulse_points": user.pulse_points,
                "games_played": user.games_played,
                "games_won": user.games_won,
                "win_rate": user.win_rate,
                "current_streak": user.current_streak,
                "longest_streak": user.longest_streak,
                "referral_code": user.referral_code,
                "referral_count": user.referral_count,
                "registered_at": user.registered_at.isoformat() if user.registered_at else None,
                "last_active_at": user.last_active_at.isoformat() if user.last_active_at else None,
                "is_active": user.is_active,
                "is_admin": user.is_admin,
                "is_banned": user.is_banned,
                "is_verified": user.is_verified,
            },
            "stats": {
                "total_games": stats.total_games or 0,
                "avg_score": stats.avg_score or 0,
                "total_xp": stats.total_xp or 0,
                "total_points": stats.total_points or 0,
                "highest_score": stats.highest_score or 0,
                "achievement_count": achievement_count,
                "best_scores": best_scores_by_game
            },
            "recent_games": [
                {
                    "game_type": game.game_type,
                    "score": game.score,
                    "xp_earned": game.xp_earned,
                    "points_earned": game.points_earned,
                    "completed_at": game.completed_at.isoformat() if game.completed_at else None,
                    "game_name": GameType.get_display_name(game.game_type)
                }
                for game in recent_games
            ]
        }
    
    async def get_leaderboard(
        self,
        limit: int = 10,
        offset: int = 0,
        game_type: Optional[str] = None,
        period: str = "all_time",
        order_by: str = "points"
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get leaderboard data
        
        Args:
            limit: Number of records to return
            offset: Offset for pagination
            game_type: Filter by game type
            period: Time period (all_time, weekly, monthly)
            order_by: Field to order by (points, level, games_played, win_rate)
        
        Returns:
            Tuple of (leaderboard entries, total count)
        """
        # Base query
        query = select(User).where(
            User.is_active == True,
            User.is_banned == False
        )
        
        # Apply game type filter if specified
        if game_type:
            # Filter users who have played this game
            subquery = select(GameSession.user_id).where(
                GameSession.game_type == game_type,
                GameSession.is_valid == True
            ).distinct()
            query = query.where(User.id.in_(subquery))
        
        # Apply time period filter
        if period == "weekly":
            cutoff = datetime.utcnow() - timedelta(days=7)
            # Users who were active in the last week
            query = query.where(User.last_active_at >= cutoff)
        elif period == "monthly":
            cutoff = datetime.utcnow() - timedelta(days=30)
            query = query.where(User.last_active_at >= cutoff)
        
        # Order by
        if order_by == "points":
            query = query.order_by(desc(User.pulse_points))
        elif order_by == "level":
            query = query.order_by(desc(User.level), desc(User.xp))
        elif order_by == "games_played":
            query = query.order_by(desc(User.games_played))
        elif order_by == "win_rate":
            query = query.order_by(desc(User.games_won / User.games_played))
        else:
            query = query.order_by(desc(User.pulse_points))
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0
        
        # Apply pagination
        query = query.offset(offset).limit(limit)
        result = await self.session.execute(query)
        users = result.scalars().all()
        
        # Build leaderboard entries
        entries = []
        for i, user in enumerate(users):
            entry = {
                "rank": offset + i + 1,
                "user_id": user.id,
                "telegram_id": user.telegram_id,
                "username": user.username,
                "display_name": user.full_name,
                "level": user.level,
                "xp": user.xp,
                "pulse_points": user.pulse_points,
                "games_played": user.games_played,
                "games_won": user.games_won,
                "win_rate": user.win_rate,
            }
            
            # Add game-specific score if game_type specified
            if game_type:
                best_score = await self.get_best_score(user.id, game_type)
                entry["best_score"] = best_score.score if best_score else 0
            
            entries.append(entry)
        
        return entries, total
    
    async def get_leaderboard_rank(self, user_id: int, game_type: Optional[str] = None) -> int:
        """
        Get user's rank on the leaderboard
        
        Args:
            user_id: User ID
            game_type: Game type to filter by
        
        Returns:
            Rank (1-based)
        """
        user = await self.get_by_id(user_id)
        if not user:
            return 0
        
        # Build query for users ahead of this user
        query = select(User).where(
            User.is_active == True,
            User.is_banned == False
        )
        
        if game_type:
            subquery = select(GameSession.user_id).where(
                GameSession.game_type == game_type,
                GameSession.is_valid == True
            ).distinct()
            query = query.where(User.id.in_(subquery))
        
        # Count users with more points
        count_query = select(func.count()).where(
            User.pulse_points > user.pulse_points,
            User.is_active == True,
            User.is_banned == False
        )
        
        if game_type:
            subquery = select(GameSession.user_id).where(
                GameSession.game_type == game_type,
                GameSession.is_valid == True
            ).distinct()
            count_query = count_query.where(User.id.in_(subquery))
        
        result = await self.session.execute(count_query)
        ahead = result.scalar() or 0
        
        return ahead + 1
    
    # ==================== Streak Operations ====================
    
    async def update_streak(self, user_id: int) -> Dict[str, Any]:
        """
        Update user's daily streak
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary with streak update results
        """
        user = await self.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(user_id)
        
        today = datetime.utcnow().date()
        last_active = user.last_active_at.date() if user.last_active_at else None
        
        result = {
            "current_streak": user.current_streak,
            "longest_streak": user.longest_streak,
            "updated": False,
            "bonus": 0,
            "reset": False
        }
        
        if last_active == today:
            # Already active today
            return result
        
        if last_active == today - timedelta(days=1):
            # Consecutive day
            user.current_streak += 1
            if user.current_streak > user.longest_streak:
                user.longest_streak = user.current_streak
            
            result["current_streak"] = user.current_streak
            result["longest_streak"] = user.longest_streak
            result["updated"] = True
            
            # Check for streak bonus
            bonus = 0
            bonus_xp = 0
            milestone = False
            
            if user.current_streak % 7 == 0 and user.current_streak > 0:
                bonus = 50
                bonus_xp = 25
                milestone = True
                # Create streak milestone notification
                notification = Notification.create_streak_milestone(
                    user_id=user.id,
                    streak_days=user.current_streak,
                    bonus_points=bonus,
                    bonus_xp=bonus_xp
                )
                self.session.add(notification)
            
            elif user.current_streak % 30 == 0 and user.current_streak > 0:
                bonus = 200
                bonus_xp = 100
                milestone = True
                notification = Notification.create_streak_milestone(
                    user_id=user.id,
                    streak_days=user.current_streak,
                    bonus_points=bonus,
                    bonus_xp=bonus_xp
                )
                self.session.add(notification)
            
            elif user.current_streak % 365 == 0 and user.current_streak > 0:
                bonus = 1000
                bonus_xp = 500
                milestone = True
                notification = Notification.create_streak_milestone(
                    user_id=user.id,
                    streak_days=user.current_streak,
                    bonus_points=bonus,
                    bonus_xp=bonus_xp
                )
                self.session.add(notification)
            
            if bonus > 0:
                user.pulse_points += bonus
                user.xp += bonus_xp
                
                # Create transaction
                transaction = PointTransaction.create_streak_bonus(
                    user_id=user.id,
                    amount=bonus,
                    streak_days=user.current_streak,
                    description=f"Streak bonus: {bonus} points for {user.current_streak} days"
                )
                self.session.add(transaction)
                
                result["bonus"] = bonus
            
            user.last_active_at = datetime.utcnow()
            await self.session.flush()
            
        else:
            # Streak broken
            if user.current_streak > 0:
                user.current_streak = 0
            
            # Check if we should send streak warning
            if last_active and (today - last_active).days == 1:
                # Day after missing - send warning
                notification = Notification.create_streak_warning(
                    user_id=user.id,
                    current_streak=user.current_streak
                )
                self.session.add(notification)
            
            result["reset"] = True
            user.last_active_at = datetime.utcnow()
            await self.session.flush()
        
        await self._clear_user_cache(user.telegram_id)
        return result
    
    # ==================== Best Score Operations ====================
    
    async def get_best_score(self, user_id: int, game_type: str) -> Optional[BestScore]:
        """
        Get user's best score for a game
        
        Args:
            user_id: User ID
            game_type: Game type
        
        Returns:
            BestScore object or None
        """
        query = select(BestScore).where(
            BestScore.user_id == user_id,
            BestScore.game_type == game_type
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def update_best_score(
        self,
        user_id: int,
        game_type: str,
        score: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Update user's best score for a game
        
        Args:
            user_id: User ID
            game_type: Game type
            score: New score
            metadata: Additional metadata
        
        Returns:
            True if score was updated, False if not
        """
        best = await self.get_best_score(user_id, game_type)
        
        if best:
            if score > best.score:
                best.score = score
                best.achieved_at = datetime.utcnow()
                if metadata:
                    best.metadata = metadata
                await self.session.flush()
                return True
            return False
        else:
            # Create new best score
            new_best = BestScore(
                user_id=user_id,
                game_type=game_type,
                score=score,
                achieved_at=datetime.utcnow(),
                metadata=metadata
            )
            self.session.add(new_best)
            await self.session.flush()
            return True
    
    # ==================== Referral Operations ====================
    
    async def process_referral(self, user_id: int, referral_code: str) -> Dict[str, Any]:
        """
        Process a referral
        
        Args:
            user_id: User ID of the new user
            referral_code: Referral code used
        
        Returns:
            Dictionary with referral results
        """
        # Get referrer
        referrer = await self.get_by_referral_code(referral_code)
        if not referrer:
            return {"success": False, "error": "Invalid referral code"}
        
        # Check self-referral
        user = await self.get_by_id(user_id)
        if not user:
            return {"success": False, "error": "User not found"}
        
        if user.id == referrer.id:
            return {"success": False, "error": "Cannot refer yourself"}
        
        # Check if user was already referred
        if user.referred_by_id:
            return {"success": False, "error": "User already referred by someone else"}
        
        # Check referral limit
        if referrer.referral_count >= settings.REFERRAL_MAX_PER_USER:
            return {"success": False, "error": "Referral limit reached"}
        
        # Process referral
        user.referred_by_id = referrer.id
        referrer.referral_count += 1
        
        # Calculate rewards
        points_reward = settings.REFERRAL_REWARD_POINTS
        xp_reward = settings.REFERRAL_REWARD_XP
        
        # Give rewards to referrer
        referrer.pulse_points += points_reward
        referrer.xp += xp_reward
        referrer.referral_points_earned += points_reward
        
        # Create referral transaction
        transaction = PointTransaction.create_referral_reward(
            user_id=referrer.id,
            amount=points_reward,
            referred_user_id=user.id,
            referred_username=user.username,
            description=f"Referral reward: {points_reward} points for referring {user.full_name}"
        )
        self.session.add(transaction)
        
        # Create referral record
        referral = UserReferral(
            referrer_id=referrer.id,
            referred_id=user.id,
            referral_code=referral_code,
            status="rewarded",
            reward_points=points_reward,
            reward_xp=xp_reward,
            rewarded_at=datetime.utcnow()
        )
        self.session.add(referral)
        
        # Create notification for referrer
        notification = Notification.create_referral_reward(
            user_id=referrer.id,
            referred_username=user.full_name,
            points_reward=points_reward
        )
        self.session.add(notification)
        
        # Create notification for new user
        welcome_referral = Notification(
            user_id=user.id,
            notification_type="referral_joined",
            title="🎉 Welcome from your friend!",
            message=f"You joined GamePulse through {referrer.full_name}'s referral link!\n"
                   f"Start playing to earn your own rewards!",
            short_message="Welcome through referral!",
            priority="medium",
            data={"referrer_id": referrer.id, "referrer_name": referrer.full_name},
            buttons=[
                {"text": "🎮 Play Now", "callback_data": "games_menu"}
            ]
        )
        self.session.add(welcome_referral)
        
        await self.session.flush()
        await self._clear_user_cache(user.telegram_id)
        await self._clear_user_cache(referrer.telegram_id)
        
        return {
            "success": True,
            "referrer_id": referrer.id,
            "points_awarded": points_reward,
            "xp_awarded": xp_reward
        }
    
    async def get_referral_stats(self, user_id: int) -> Dict[str, Any]:
        """
        Get user's referral statistics
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary with referral stats
        """
        user = await self.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(user_id)
        
        # Get referrals
        query = select(User).where(User.referred_by_id == user_id)
        result = await self.session.execute(query)
        referrals = result.scalars().all()
        
        return {
            "referral_code": user.referral_code,
            "total_referrals": user.referral_count,
            "points_earned": user.referral_points_earned,
            "referral_link": user.referral_link,
            "referrals": [
                {
                    "id": ref.id,
                    "username": ref.username or ref.full_name,
                    "display_name": ref.full_name,
                    "registered_at": ref.registered_at.isoformat() if ref.registered_at else None,
                    "level": ref.level,
                    "games_played": ref.games_played
                }
                for ref in referrals
            ]
        }
    
    # ==================== Ban Operations ====================
    
    async def ban_user(
        self,
        user_id: int,
        reason: str,
        admin_id: Optional[int] = None,
        duration_days: Optional[int] = None
    ) -> bool:
        """
        Ban a user
        
        Args:
            user_id: User ID to ban
            reason: Ban reason
            admin_id: Admin performing the ban
            duration_days: Duration of ban in days (None = permanent)
        
        Returns:
            True if successful
        """
        user = await self.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(user_id)
        
        user.is_banned = True
        user.ban_reason = reason
        user.banned_at = datetime.utcnow()
        user.banned_by = admin_id
        user.is_active = False
        
        await self.session.flush()
        await self._clear_user_cache(user.telegram_id)
        
        # Log activity
        await self._log_activity(
            user_id=user_id,
            action="user_banned",
            details={
                "reason": reason,
                "admin_id": admin_id,
                "duration_days": duration_days
            }
        )
        
        return True
    
    async def unban_user(self, user_id: int, admin_id: Optional[int] = None) -> bool:
        """
        Unban a user
        
        Args:
            user_id: User ID to unban
            admin_id: Admin performing the unban
        
        Returns:
            True if successful
        """
        user = await self.get_by_id(user_id)
        if not user:
            raise UserNotFoundError(user_id)
        
        user.is_banned = False
        user.ban_reason = None
        user.banned_at = None
        user.banned_by = None
        user.is_active = True
        
        await self.session.flush()
        await self._clear_user_cache(user.telegram_id)
        
        # Log activity
        await self._log_activity(
            user_id=user_id,
            action="user_unbanned",
            details={"admin_id": admin_id}
        )
        
        return True
    
    # ==================== Search Operations ====================
    
    async def search_users(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0
    ) -> Tuple[List[User], int]:
        """
        Search users by username or display name
        
        Args:
            query: Search query
            limit: Number of results
            offset: Offset for pagination
        
        Returns:
            Tuple of (users, total count)
        """
        search_term = f"%{query}%"
        
        # Build search query
        base_query = select(User).where(
            or_(
                User.username.ilike(search_term),
                User.first_name.ilike(search_term),
                User.last_name.ilike(search_term),
                User.display_name.ilike(search_term)
            )
        )
        
        # Get total count
        count_query = select(func.count()).select_from(base_query.subquery())
        result = await self.session.execute(count_query)
        total = result.scalar() or 0
        
        # Apply pagination and order
        query = base_query.order_by(User.id).offset(offset).limit(limit)
        result = await self.session.execute(query)
        users = result.scalars().all()
        
        return users, total
    
    async def get_active_users(
        self,
        days: int = 7,
        limit: int = 100
    ) -> List[User]:
        """
        Get users active in the last N days
        
        Args:
            days: Number of days
            limit: Maximum number of users
        
        Returns:
            List of active users
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = select(User).where(
            User.last_active_at >= cutoff,
            User.is_active == True,
            User.is_banned == False
        ).order_by(desc(User.last_active_at)).limit(limit)
        
        result = await self.session.execute(query)
        return result.scalars().all()
    
    # ==================== Admin Operations ====================
    
    async def get_all_users(
        self,
        limit: int = 100,
        offset: int = 0,
        include_banned: bool = False
    ) -> Tuple[List[User], int]:
        """
        Get all users (admin only)
        
        Args:
            limit: Number of results
            offset: Offset for pagination
            include_banned: Whether to include banned users
        
        Returns:
            Tuple of (users, total count)
        """
        query = select(User)
        
        if not include_banned:
            query = query.where(User.is_banned == False)
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        result = await self.session.execute(count_query)
        total = result.scalar() or 0
        
        # Apply pagination
        query = query.order_by(desc(User.registered_at)).offset(offset).limit(limit)
        result = await self.session.execute(query)
        users = result.scalars().all()
        
        return users, total
    
    async def get_user_count(self) -> Dict[str, int]:
        """
        Get user count statistics
        
        Returns:
            Dictionary with user counts
        """
        # Total users
        total_query = select(func.count()).where(User.is_active == True)
        result = await self.session.execute(total_query)
        total = result.scalar() or 0
        
        # Banned users
        banned_query = select(func.count()).where(User.is_banned == True)
        result = await self.session.execute(banned_query)
        banned = result.scalar() or 0
        
        # Active today
        today = datetime.utcnow().date()
        active_query = select(func.count()).where(
            User.last_active_at >= datetime.combine(today, datetime.min.time()),
            User.is_active == True
        )
        result = await self.session.execute(active_query)
        active_today = result.scalar() or 0
        
        # New users today
        new_query = select(func.count()).where(
            User.registered_at >= datetime.combine(today, datetime.min.time())
        )
        result = await self.session.execute(new_query)
        new_today = result.scalar() or 0
        
        return {
            "total": total,
            "banned": banned,
            "active_today": active_today,
            "new_today": new_today
        }
    
    # ==================== Utility Methods ====================
    
    def _generate_referral_code(self, length: int = 8) -> str:
        """Generate a unique referral code"""
        import secrets
        import string
        alphabet = string.ascii_uppercase + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    def _deep_merge(self, base: Dict, update: Dict) -> None:
        """Deep merge two dictionaries"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
    
    async def _log_activity(
        self,
        user_id: int,
        action: str,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log user activity"""
        log = UserActivityLog(
            user_id=user_id,
            action=action,
            details=details or {},
            created_at=datetime.utcnow()
        )
        self.session.add(log)
        await self.session.flush()
    
    async def _clear_user_cache(self, telegram_id: int) -> None:
        """Clear user cache"""
        await redis_manager.delete(f"user:telegram:{telegram_id}")
        await redis_manager.delete(f"user:stats:{telegram_id}")
        await redis_manager.delete(f"user:profile:{telegram_id}")
    
    # ==================== Snapshot Operations ====================
    
    async def create_daily_snapshot(self, user_id: int) -> None:
        """
        Create a daily snapshot of user stats for analytics
        
        Args:
            user_id: User ID
        """
        user = await self.get_by_id(user_id)
        if not user:
            return
        
        # Check if snapshot already exists for today
        today = datetime.utcnow().date()
        query = select(UserStatsSnapshot).where(
            UserStatsSnapshot.user_id == user_id,
            UserStatsSnapshot.snapshot_date >= datetime.combine(today, datetime.min.time())
        )
        result = await self.session.execute(query)
        existing = result.scalar_one_or_none()
        
        if existing:
            return
        
        # Create snapshot
        snapshot = UserStatsSnapshot(
            user_id=user.id,
            snapshot_date=datetime.utcnow(),
            level=user.level,
            xp=user.xp,
            pulse_points=user.pulse_points,
            games_played=user.games_played,
            games_won=user.games_won,
            current_streak=user.current_streak,
            longest_streak=user.longest_streak,
            xp_gained=0,
            points_gained=0,
            games_played_today=0,
            games_won_today=0
        )
        self.session.add(snapshot)
        await self.session.flush()
