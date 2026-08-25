"""
Game Repository for GamePulse Bot
Handles all database operations related to game sessions, matches, and game data
"""

from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta, date
from sqlalchemy import select, update, delete, func, and_, or_, desc, asc, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from src.models.game import (
    GameSession,
    GameSessionStatus,
    FriendMatch,
    MatchStatus,
    GameLeaderboardEntry,
    GameStats,
    GameType
)
from src.models.user import User, BestScore
from src.core.exceptions import (
    GameSessionNotFoundError,
    GameSessionExpiredError,
    GameValidationError,
    InvalidScoreError,
    ChallengeNotFoundError,
    ChallengeExpiredError
)
from src.core.config import settings
from src.core.redis import redis_manager


class GameRepository:
    """Repository for game-related database operations"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    # ==================== Game Session Operations ====================
    
    async def create_session(
        self,
        user_id: int,
        game_type: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> GameSession:
        """
        Create a new game session
        
        Args:
            user_id: User ID
            game_type: Type of game
            metadata: Additional metadata
        
        Returns:
            Created GameSession object
        """
        session = GameSession(
            user_id=user_id,
            game_type=game_type,
            metadata=metadata or {},
            status=GameSessionStatus.CREATED.value,
            started_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(seconds=settings.GAME_SESSION_TIMEOUT)
        )
        
        self.session.add(session)
        await self.session.flush()
        
        # Store session in Redis
        await redis_manager.set(
            f"game:session:{session.session_id}",
            {
                "id": session.id,
                "session_id": session.session_id,
                "user_id": session.user_id,
                "game_type": session.game_type,
                "started_at": session.started_at.isoformat(),
                "expires_at": session.expires_at.isoformat() if session.expires_at else None,
                "status": session.status
            },
            ttl=settings.GAME_SESSION_TIMEOUT + 60
        )
        
        return session
    
    async def get_session_by_id(self, session_id: str) -> Optional[GameSession]:
        """
        Get game session by session ID
        
        Args:
            session_id: Session ID
        
        Returns:
            GameSession object or None
        """
        # Try Redis cache first
        cached = await redis_manager.get(f"game:session:{session_id}")
        if cached:
            # Could materialize from cache, but we'll query DB for consistency
            pass
        
        query = select(GameSession).where(GameSession.session_id == session_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_session_by_id_with_user(self, session_id: str) -> Optional[GameSession]:
        """
        Get game session with user data
        
        Args:
            session_id: Session ID
        
        Returns:
            GameSession object with user loaded or None
        """
        query = select(GameSession).where(
            GameSession.session_id == session_id
        ).options(joinedload(GameSession.user))
        
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_active_session(self, user_id: int, game_type: str) -> Optional[GameSession]:
        """
        Get active session for a user and game type
        
        Args:
            user_id: User ID
            game_type: Game type
        
        Returns:
            Active GameSession or None
        """
        query = select(GameSession).where(
            GameSession.user_id == user_id,
            GameSession.game_type == game_type,
            GameSession.status.in_([GameSessionStatus.CREATED.value, GameSessionStatus.STARTED.value]),
            GameSession.is_valid == True
        ).order_by(desc(GameSession.created_at)).limit(1)
        
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_user_sessions(
        self,
        user_id: int,
        limit: int = 20,
        offset: int = 0,
        game_type: Optional[str] = None,
        status: Optional[str] = None
    ) -> Tuple[List[GameSession], int]:
        """
        Get user's game sessions
        
        Args:
            user_id: User ID
            limit: Number of results
            offset: Offset for pagination
            game_type: Filter by game type
            status: Filter by status
        
        Returns:
            Tuple of (sessions, total count)
        """
        query = select(GameSession).where(GameSession.user_id == user_id)
        
        if game_type:
            query = query.where(GameSession.game_type == game_type)
        
        if status:
            query = query.where(GameSession.status == status)
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        result = await self.session.execute(count_query)
        total = result.scalar() or 0
        
        # Apply pagination and order
        query = query.order_by(desc(GameSession.created_at)).offset(offset).limit(limit)
        result = await self.session.execute(query)
        sessions = result.scalars().all()
        
        return sessions, total
    
    async def start_session(self, session_id: str) -> GameSession:
        """
        Start a game session
        
        Args:
            session_id: Session ID
        
        Returns:
            Updated GameSession
        """
        session = await self.get_session_by_id(session_id)
        if not session:
            raise GameSessionNotFoundError(session_id)
        
        if session.status != GameSessionStatus.CREATED.value:
            raise GameValidationError(f"Session already started (status: {session.status})")
        
        if session.is_expired:
            session.status = GameSessionStatus.EXPIRED.value
            await self.session.flush()
            raise GameSessionExpiredError(session_id)
        
        session.start()
        await self.session.flush()
        
        # Update Redis
        await redis_manager.set(
            f"game:session:{session.session_id}",
            {
                "id": session.id,
                "session_id": session.session_id,
                "user_id": session.user_id,
                "game_type": session.game_type,
                "started_at": session.started_at.isoformat(),
                "expires_at": session.expires_at.isoformat() if session.expires_at else None,
                "status": session.status
            },
            ttl=settings.GAME_SESSION_TIMEOUT + 60
        )
        
        return session
    
    async def complete_session(
        self,
        session_id: str,
        score: int,
        duration: int,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Complete a game session
        
        Args:
            session_id: Session ID
            score: Final score
            duration: Duration in seconds
            metadata: Additional metadata
        
        Returns:
            Dictionary with session results
        """
        session = await self.get_session_by_id_with_user(session_id)
        if not session:
            raise GameSessionNotFoundError(session_id)
        
        if session.is_completed:
            raise GameValidationError("Session already completed")
        
        if session.is_expired:
            session.status = GameSessionStatus.EXPIRED.value
            session.is_valid = False
            await self.session.flush()
            raise GameSessionExpiredError(session_id)
        
        # Validate score
        if score < 0:
            raise InvalidScoreError(score, "Score cannot be negative")
        
        if score > settings.ANTI_CHEAT_MAX_SCORE:
            raise InvalidScoreError(score, f"Score exceeds maximum of {settings.ANTI_CHEAT_MAX_SCORE}")
        
        # Calculate rewards (will be implemented by specific game)
        xp_earned, points_earned = await self._calculate_rewards(
            game_type=session.game_type,
            score=score,
            duration=duration
        )
        
        # Complete session
        session.complete(score, xp_earned, points_earned, duration)
        if metadata:
            if session.metadata:
                session.metadata.update(metadata)
            else:
                session.metadata = metadata
        
        await self.session.flush()
        
        # Update Redis
        await redis_manager.delete(f"game:session:{session.session_id}")
        
        # Update user stats
        from src.repositories.user_repo import UserRepository
        user_repo = UserRepository(self.session)
        await user_repo.update_stats(
            user_id=session.user_id,
            xp_gained=xp_earned,
            points_gained=points_earned,
            games_played_increment=1
        )
        
        # Update best score
        await self.update_best_score(session.user_id, session.game_type, score)
        
        # Update leaderboard
        await self.update_leaderboard_entry(session.user_id, session.game_type, score)
        
        return {
            "session": session,
            "xp_earned": xp_earned,
            "points_earned": points_earned,
            "score": score,
            "duration": duration
        }
    
    async def invalidate_session(self, session_id: str, reason: str) -> None:
        """
        Invalidate a game session
        
        Args:
            session_id: Session ID
            reason: Reason for invalidation
        """
        session = await self.get_session_by_id(session_id)
        if not session:
            raise GameSessionNotFoundError(session_id)
        
        session.invalidate(reason)
        await self.session.flush()
        
        # Update Redis
        await redis_manager.delete(f"game:session:{session.session_id}")
    
    async def mark_suspicious_session(
        self,
        session_id: str,
        checks: Dict[str, Any]
    ) -> None:
        """
        Mark a session as suspicious
        
        Args:
            session_id: Session ID
            checks: Validation checks that failed
        """
        session = await self.get_session_by_id(session_id)
        if not session:
            raise GameSessionNotFoundError(session_id)
        
        session.mark_suspicious(checks)
        await self.session.flush()
    
    # ==================== Best Score Operations ====================
    
    async def update_best_score(
        self,
        user_id: int,
        game_type: str,
        score: int
    ) -> bool:
        """
        Update user's best score for a game
        
        Args:
            user_id: User ID
            game_type: Game type
            score: New score
        
        Returns:
            True if score was updated
        """
        # Check existing best score
        query = select(BestScore).where(
            BestScore.user_id == user_id,
            BestScore.game_type == game_type
        )
        result = await self.session.execute(query)
        best_score = result.scalar_one_or_none()
        
        if best_score:
            if score > best_score.score:
                best_score.score = score
                best_score.achieved_at = datetime.utcnow()
                await self.session.flush()
                return True
            return False
        else:
            # Create new best score
            new_best = BestScore(
                user_id=user_id,
                game_type=game_type,
                score=score,
                achieved_at=datetime.utcnow()
            )
            self.session.add(new_best)
            await self.session.flush()
            return True
    
    async def get_best_scores(self, user_id: int) -> Dict[str, int]:
        """
        Get all best scores for a user
        
        Args:
            user_id: User ID
        
        Returns:
            Dictionary of game_type -> best_score
        """
        query = select(BestScore).where(BestScore.user_id == user_id)
        result = await self.session.execute(query)
        scores = result.scalars().all()
        
        return {score.game_type: score.score for score in scores}
    
    # ==================== Leaderboard Operations ====================
    
    async def update_leaderboard_entry(
        self,
        user_id: int,
        game_type: str,
        score: int
    ) -> None:
        """
        Update leaderboard entry for a user
        
        Args:
            user_id: User ID
            game_type: Game type
            score: Score
        """
        today = datetime.utcnow().date()
        
        # Update all-time leaderboard
        await self._update_leaderboard_entry_for_period(
            user_id, game_type, score, "all_time"
        )
        
        # Update weekly leaderboard
        await self._update_leaderboard_entry_for_period(
            user_id, game_type, score, "weekly"
        )
        
        # Update monthly leaderboard
        await self._update_leaderboard_entry_for_period(
            user_id, game_type, score, "monthly"
        )
    
    async def _update_leaderboard_entry_for_period(
        self,
        user_id: int,
        game_type: str,
        score: int,
        period: str
    ) -> None:
        """
        Update leaderboard entry for a specific period
        
        Args:
            user_id: User ID
            game_type: Game type
            score: Score
            period: Period (all_time, weekly, monthly)
        """
        # Check existing entry
        query = select(GameLeaderboardEntry).where(
            GameLeaderboardEntry.user_id == user_id,
            GameLeaderboardEntry.game_type == game_type,
            GameLeaderboardEntry.period == period
        )
        result = await self.session.execute(query)
        entry = result.scalar_one_or_none()
        
        if entry:
            if score > entry.score:
                entry.score = score
                entry.entry_date = datetime.utcnow()
                await self.session.flush()
        else:
            new_entry = GameLeaderboardEntry(
                user_id=user_id,
                game_type=game_type,
                score=score,
                period=period,
                entry_date=datetime.utcnow()
            )
            self.session.add(new_entry)
            await self.session.flush()
    
    async def get_leaderboard(
        self,
        game_type: Optional[str] = None,
        period: str = "all_time",
        limit: int = 10,
        offset: int = 0
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get leaderboard
        
        Args:
            game_type: Filter by game type
            period: Period (all_time, weekly, monthly)
            limit: Number of results
            offset: Offset for pagination
        
        Returns:
            Tuple of (entries, total count)
        """
        # Build query
        query = select(GameLeaderboardEntry).where(
            GameLeaderboardEntry.period == period
        )
        
        if game_type:
            query = query.where(GameLeaderboardEntry.game_type == game_type)
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        result = await self.session.execute(count_query)
        total = result.scalar() or 0
        
        # Apply pagination and order
        query = query.order_by(
            desc(GameLeaderboardEntry.score),
            asc(GameLeaderboardEntry.entry_date)
        ).offset(offset).limit(limit)
        
        query = query.options(joinedload(GameLeaderboardEntry.user))
        result = await self.session.execute(query)
        entries = result.scalars().all()
        
        # Build response
        leaderboard = []
        for i, entry in enumerate(entries):
            leaderboard.append({
                "rank": offset + i + 1,
                "user_id": entry.user_id,
                "username": entry.user.username if entry.user else None,
                "display_name": entry.user.full_name if entry.user else "Unknown",
                "score": entry.score,
                "game_type": entry.game_type,
                "entry_date": entry.entry_date.isoformat() if entry.entry_date else None
            })
        
        return leaderboard, total
    
    async def get_user_rank(
        self,
        user_id: int,
        game_type: Optional[str] = None,
        period: str = "all_time"
    ) -> int:
        """
        Get user's rank on the leaderboard
        
        Args:
            user_id: User ID
            game_type: Filter by game type
            period: Period
        
        Returns:
            Rank (1-based)
        """
        # Get user's score
        query = select(GameLeaderboardEntry).where(
            GameLeaderboardEntry.user_id == user_id,
            GameLeaderboardEntry.period == period
        )
        
        if game_type:
            query = query.where(GameLeaderboardEntry.game_type == game_type)
        
        result = await self.session.execute(query)
        entry = result.scalar_one_or_none()
        
        if not entry:
            return 0
        
        # Count users with higher score
        count_query = select(func.count()).where(
            GameLeaderboardEntry.period == period,
            GameLeaderboardEntry.score > entry.score
        )
        
        if game_type:
            count_query = count_query.where(GameLeaderboardEntry.game_type == game_type)
        
        result = await self.session.execute(count_query)
        ahead = result.scalar() or 0
        
        return ahead + 1
    
    # ==================== Friend Match Operations ====================
    
    async def create_match(
        self,
        challenger_id: int,
        opponent_id: int,
        game_type: str,
        match_type: str = "friend_challenge",
        wager_points: int = 0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> FriendMatch:
        """
        Create a friend match
        
        Args:
            challenger_id: Challenger user ID
            opponent_id: Opponent user ID
            game_type: Game type
            match_type: Type of match
            wager_points: Points wagered (optional)
            metadata: Additional metadata
        
        Returns:
            Created FriendMatch object
        """
        # Check for existing pending match
        query = select(FriendMatch).where(
            and_(
                FriendMatch.challenger_id == challenger_id,
                FriendMatch.opponent_id == opponent_id,
                FriendMatch.status == MatchStatus.PENDING.value
            )
        )
        result = await self.session.execute(query)
        existing = result.scalar_one_or_none()
        
        if existing:
            raise GameValidationError("You already have a pending challenge with this user")
        
        # Create match
        match = FriendMatch(
            challenger_id=challenger_id,
            opponent_id=opponent_id,
            game_type=game_type,
            match_type=match_type,
            wager_points=wager_points,
            metadata=metadata or {},
            status=MatchStatus.PENDING.value,
            expires_at=datetime.utcnow() + timedelta(hours=24)
        )
        
        self.session.add(match)
        await self.session.flush()
        
        return match
    
    async def get_match_by_id(self, match_id: int) -> Optional[FriendMatch]:
        """
        Get match by ID
        
        Args:
            match_id: Match ID
        
        Returns:
            FriendMatch object or None
        """
        query = select(FriendMatch).where(FriendMatch.id == match_id).options(
            joinedload(FriendMatch.challenger),
            joinedload(FriendMatch.opponent),
            joinedload(FriendMatch.winner)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_match_by_match_id(self, match_id: str) -> Optional[FriendMatch]:
        """
        Get match by match ID
        
        Args:
            match_id: Match ID string
        
        Returns:
            FriendMatch object or None
        """
        query = select(FriendMatch).where(FriendMatch.match_id == match_id).options(
            joinedload(FriendMatch.challenger),
            joinedload(FriendMatch.opponent),
            joinedload(FriendMatch.winner)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
    
    async def get_user_matches(
        self,
        user_id: int,
        status: Optional[str] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Tuple[List[FriendMatch], int]:
        """
        Get user's matches
        
        Args:
            user_id: User ID
            status: Filter by status
            limit: Number of results
            offset: Offset for pagination
        
        Returns:
            Tuple of (matches, total count)
        """
        query = select(FriendMatch).where(
            or_(
                FriendMatch.challenger_id == user_id,
                FriendMatch.opponent_id == user_id
            )
        )
        
        if status:
            query = query.where(FriendMatch.status == status)
        
        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        result = await self.session.execute(count_query)
        total = result.scalar() or 0
        
        # Apply pagination and order
        query = query.order_by(
            desc(FriendMatch.created_at)
        ).offset(offset).limit(limit)
        
        query = query.options(
            joinedload(FriendMatch.challenger),
            joinedload(FriendMatch.opponent),
            joinedload(FriendMatch.winner)
        )
        
        result = await self.session.execute(query)
        matches = result.scalars().all()
        
        return matches, total
    
    async def get_pending_matches(self, user_id: int) -> List[FriendMatch]:
        """
        Get pending matches for a user
        
        Args:
            user_id: User ID
        
        Returns:
            List of pending FriendMatch objects
        """
        query = select(FriendMatch).where(
            and_(
                FriendMatch.opponent_id == user_id,
                FriendMatch.status == MatchStatus.PENDING.value,
                FriendMatch.expires_at > datetime.utcnow()
            )
        ).options(
            joinedload(FriendMatch.challenger),
            joinedload(FriendMatch.opponent),
            joinedload(FriendMatch.winner)
        ).order_by(desc(FriendMatch.created_at))
        
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def accept_match(self, match_id: int, opponent_id: int) -> FriendMatch:
        """
        Accept a match challenge
        
        Args:
            match_id: Match ID
            opponent_id: Opponent user ID (must match)
        
        Returns:
            Updated FriendMatch
        """
        match = await self.get_match_by_id(match_id)
        if not match:
            raise ChallengeNotFoundError(match_id)
        
        if match.opponent_id != opponent_id:
            raise GameValidationError("You are not the opponent for this match")
        
        if match.status != MatchStatus.PENDING.value:
            raise GameValidationError(f"Match is already {match.status}")
        
        if match.is_expired:
            await self.expire_match(match_id)
            raise ChallengeExpiredError(match_id)
        
        match.accept()
        await self.session.flush()
        
        return match
    
    async def decline_match(self, match_id: int, opponent_id: int) -> FriendMatch:
        """
        Decline a match challenge
        
        Args:
            match_id: Match ID
            opponent_id: Opponent user ID
        
        Returns:
            Updated FriendMatch
        """
        match = await self.get_match_by_id(match_id)
        if not match:
            raise ChallengeNotFoundError(match_id)
        
        if match.opponent_id != opponent_id:
            raise GameValidationError("You are not the opponent for this match")
        
        if match.status != MatchStatus.PENDING.value:
            raise GameValidationError(f"Match is already {match.status}")
        
        match.decline()
        await self.session.flush()
        
        return match
    
    async def cancel_match(self, match_id: int, user_id: int) -> FriendMatch:
        """
        Cancel a match
        
        Args:
            match_id: Match ID
            user_id: User cancelling the match
        
        Returns:
            Updated FriendMatch
        """
        match = await self.get_match_by_id(match_id)
        if not match:
            raise ChallengeNotFoundError(match_id)
        
        if not match.is_participant(user_id):
            raise GameValidationError("You are not a participant in this match")
        
        if match.status == MatchStatus.COMPLETED.value:
            raise GameValidationError("Cannot cancel a completed match")
        
        match.cancel()
        await self.session.flush()
        
        return match
    
    async def expire_match(self, match_id: int) -> None:
        """
        Mark a match as expired
        
        Args:
            match_id: Match ID
        """
        match = await self.get_match_by_id(match_id)
        if not match:
            raise ChallengeNotFoundError(match_id)
        
        if match.status == MatchStatus.COMPLETED.value:
            return
        
        match.expire()
        await self.session.flush()
    
    async def submit_match_score(
        self,
        match_id: int,
        user_id: int,
        score: int,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Submit a score for a match
        
        Args:
            match_id: Match ID
            user_id: User submitting score
            score: Score achieved
            session_id: Game session ID (optional)
        
        Returns:
            Dictionary with match results
        """
        match = await self.get_match_by_id(match_id)
        if not match:
            raise ChallengeNotFoundError(match_id)
        
        if match.status != MatchStatus.ACTIVE.value:
            raise GameValidationError(f"Match is not active (status: {match.status})")
        
        if match.is_expired:
            await self.expire_match(match_id)
            raise ChallengeExpiredError(match_id)
        
        if not match.is_participant(user_id):
            raise GameValidationError("You are not a participant in this match")
        
        if match.has_submitted(user_id):
            raise GameValidationError("You have already submitted a score for this match")
        
        # Validate score
        if score < 0:
            raise InvalidScoreError(score, "Score cannot be negative")
        
        if score > settings.ANTI_CHEAT_MAX_SCORE:
            raise InvalidScoreError(score, f"Score exceeds maximum of {settings.ANTI_CHEAT_MAX_SCORE}")
        
        # Submit score
        match.submit_score(user_id, score)
        
        # Store session ID if provided
        if session_id:
            if user_id == match.challenger_id:
                match.challenger_session_id = session_id
            else:
                match.opponent_session_id = session_id
        
        await self.session.flush()
        
        # Check if both scores are submitted
        result = {
            "submitted": True,
            "user_id": user_id,
            "score": score,
            "match_id": match.match_id
        }
        
        if match.has_both_scores:
            # Complete the match
            match_results = match.complete_match()
            
            # Calculate rewards
            rewards = await self._calculate_match_rewards(match)
            match.challenger_xp_earned = rewards["challenger_xp"]
            match.challenger_points_earned = rewards["challenger_points"]
            match.opponent_xp_earned = rewards["opponent_xp"]
            match.opponent_points_earned = rewards["opponent_points"]
            
            await self.session.flush()
            
            # Update user stats for both players
            from src.repositories.user_repo import UserRepository
            user_repo = UserRepository(self.session)
            
            # Update challenger stats
            await user_repo.update_stats(
                user_id=match.challenger_id,
                xp_gained=rewards["challenger_xp"],
                points_gained=rewards["challenger_points"],
                games_played_increment=1,
                games_won_increment=1 if match.winner_id == match.challenger_id else 0
            )
            
            # Update opponent stats
            await user_repo.update_stats(
                user_id=match.opponent_id,
                xp_gained=rewards["opponent_xp"],
                points_gained=rewards["opponent_points"],
                games_played_increment=1,
                games_won_increment=1 if match.winner_id == match.opponent_id else 0
            )
            
            # Update match stats
            await self._update_match_stats(match)
            
            result["completed"] = True
            result["winner_id"] = match.winner_id
            result["result"] = match.result
            result["challenger_score"] = match.challenger_score
            result["opponent_score"] = match.opponent_score
            result["rewards"] = rewards
        
        return result
    
    async def forfeit_match(self, match_id: int, user_id: int) -> Dict[str, Any]:
        """
        Forfeit a match
        
        Args:
            match_id: Match ID
            user_id: User forfeiting
        
        Returns:
            Dictionary with match results
        """
        match = await self.get_match_by_id(match_id)
        if not match:
            raise ChallengeNotFoundError(match_id)
        
        if match.status != MatchStatus.ACTIVE.value:
            raise GameValidationError(f"Match is not active (status: {match.status})")
        
        if not match.is_participant(user_id):
            raise GameValidationError("You are not a participant in this match")
        
        match.forfeit(user_id)
        await self.session.flush()
        
        return {
            "forfeited": True,
            "user_id": user_id,
            "winner_id": match.winner_id,
            "result": match.result,
            "match_id": match.match_id
        }
    
    # ==================== Game Stats Operations ====================
    
    async def update_game_stats(
        self,
        game_type: str,
        session: GameSession
    ) -> None:
        """
        Update aggregated game stats
        
        Args:
            game_type: Game type
            session: Completed game session
        """
        today = datetime.utcnow().date()
        
        # Get or create stats for today
        query = select(GameStats).where(
            GameStats.game_type == game_type,
            GameStats.stat_date >= datetime.combine(today, datetime.min.time())
        )
        result = await self.session.execute(query)
        stats = result.scalar_one_or_none()
        
        if not stats:
            stats = GameStats(
                game_type=game_type,
                stat_date=datetime.utcnow()
            )
            self.session.add(stats)
        
        # Update stats
        stats.total_sessions += 1
        
        # Track unique players
        # This is simplified - would need more complex logic
        stats.total_players = stats.total_sessions  # Placeholder
        
        stats.total_scores += session.score
        stats.avg_score = stats.total_scores / stats.total_sessions
        
        if session.duration:
            stats.avg_duration = ((stats.avg_duration * (stats.total_sessions - 1)) + session.duration) / stats.total_sessions
        
        stats.avg_xp = ((stats.avg_xp * (stats.total_sessions - 1)) + session.xp_earned) / stats.total_sessions
        stats.avg_points = ((stats.avg_points * (stats.total_sessions - 1)) + session.points_earned) / stats.total_sessions
        
        # Update high score
        if session.score > stats.high_score:
            stats.high_score = session.score
            stats.high_score_user_id = session.user_id
        
        await self.session.flush()
    
    # ==================== Helper Methods ====================
    
    async def _calculate_rewards(
        self,
        game_type: str,
        score: int,
        duration: int
    ) -> Tuple[int, int]:
        """
        Calculate XP and points rewards for a game
        
        Args:
            game_type: Type of game
            score: Score achieved
            duration: Duration in seconds
        
        Returns:
            Tuple of (xp, points)
        """
        # Base rewards
        xp_base = settings.XP_GAME_BASE
        points_base = settings.POINTS_GAME_BASE
        
        # Score multiplier (max 5x)
        score_multiplier = min(5, max(1, score / 100))
        
        # Duration bonus (faster = better)
        duration_bonus = max(0, 1 - (duration / 300))
        
        # Calculate XP
        xp = int(xp_base * score_multiplier * (1 + duration_bonus))
        
        # Calculate points
        points = int(points_base * score_multiplier)
        
        # Bonus for high scores
        if score > 500:
            xp += 20
            points += 10
        if score > 1000:
            xp += 30
            points += 20
        
        # Game-specific bonuses
        if game_type == "reaction" and duration < 0.5:
            xp += 25
            points += 15
        
        return xp, points
    
    async def _calculate_match_rewards(self, match: FriendMatch) -> Dict[str, int]:
        """
        Calculate rewards for a match
        
        Args:
            match: Completed FriendMatch
        
        Returns:
            Dictionary with rewards for both players
        """
        # Base rewards
        base_xp = 30
        base_points = 20
        
        # Winner bonus
        winner_bonus_xp = 20
        winner_bonus_points = 15
        
        challenger_xp = base_xp
        challenger_points = base_points
        opponent_xp = base_xp
        opponent_points = base_points
        
        if match.winner_id == match.challenger_id:
            challenger_xp += winner_bonus_xp
            challenger_points += winner_bonus_points
        elif match.winner_id == match.opponent_id:
            opponent_xp += winner_bonus_xp
            opponent_points += winner_bonus_points
        else:
            # Tie - both get some points
            challenger_points += 5
            opponent_points += 5
        
        return {
            "challenger_xp": challenger_xp,
            "challenger_points": challenger_points,
            "opponent_xp": opponent_xp,
            "opponent_points": opponent_points
        }
    
    async def _update_match_stats(self, match: FriendMatch) -> None:
        """
        Update match statistics for both players
        
        Args:
            match: Completed FriendMatch
        """
        from src.models.friend_match import MatchStats
        
        for user_id in [match.challenger_id, match.opponent_id]:
            # Get or create stats
            query = select(MatchStats).where(
                MatchStats.user_id == user_id,
                MatchStats.game_type == match.game_type,
                MatchStats.period == "all_time"
            )
            result = await self.session.execute(query)
            stats = result.scalar_one_or_none()
            
            if not stats:
                stats = MatchStats(
                    user_id=user_id,
                    game_type=match.game_type,
                    period="all_time"
                )
                self.session.add(stats)
            
            # Determine result for this player
            if match.winner_id == user_id:
                result = "win"
            elif match.is_tie:
                result = "tie"
            else:
                result = "loss"
            
            # Get score for this player
            score = match.challenger_score if user_id == match.challenger_id else match.opponent_score
            
            # Update stats
            stats.update_stats(result, score or 0)
            await self.session.flush()
    
    # ==================== Cleanup Operations ====================
    
    async def cleanup_expired_sessions(self) -> int:
        """
        Clean up expired game sessions
        
        Returns:
            Number of sessions cleaned up
        """
        now = datetime.utcnow()
        
        # Find expired sessions
        query = select(GameSession).where(
            GameSession.expires_at < now,
            GameSession.status.in_([GameSessionStatus.CREATED.value, GameSessionStatus.STARTED.value])
        )
        result = await self.session.execute(query)
        sessions = result.scalars().all()
        
        count = 0
        for session in sessions:
            session.status = GameSessionStatus.EXPIRED.value
            session.is_valid = False
            count += 1
            
            # Clean up Redis
            await redis_manager.delete(f"game:session:{session.session_id}")
        
        await self.session.flush()
        return count
    
    async def cleanup_expired_matches(self) -> int:
        """
        Clean up expired friend matches
        
        Returns:
            Number of matches cleaned up
        """
        now = datetime.utcnow()
        
        # Find expired matches
        query = select(FriendMatch).where(
            FriendMatch.expires_at < now,
            FriendMatch.status.in_([MatchStatus.PENDING.value, MatchStatus.ACCEPTED.value, MatchStatus.ACTIVE.value])
        )
        result = await self.session.execute(query)
        matches = result.scalars().all()
        
        for match in matches:
            match.expire()
        
        await self.session.flush()
        return len(matches)
