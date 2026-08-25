"""
Admin Log models for GamePulse Bot
Tracks all admin actions for auditing, security, and accountability
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    Column, BigInteger, String, Integer, Boolean, DateTime, 
    JSON, ForeignKey, Text, Index, UniqueConstraint,
    func, Enum as SQLEnum
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.ext.hybrid import hybrid_property
import enum
import uuid
import ipaddress

from src.core.database import Base, TimestampMixin


# ==================== Enums ====================
class AdminActionType(str, enum.Enum):
    """Types of admin actions"""
    # User Management
    USER_VIEW = "user_view"
    USER_SEARCH = "user_search"
    USER_BAN = "user_ban"
    USER_UNBAN = "user_unban"
    USER_KICK = "user_kick"
    USER_WARN = "user_warn"
    USER_MUTE = "user_mute"
    USER_UNMUTE = "user_unmute"
    USER_DELETE = "user_delete"
    USER_RESTORE = "user_restore"
    USER_ROLE_CHANGE = "user_role_change"
    USER_VERIFY = "user_verify"
    USER_UNVERIFY = "user_unverify"
    
    # Point Management
    POINTS_ADD = "points_add"
    POINTS_REMOVE = "points_remove"
    POINTS_ADJUST = "points_adjust"
    POINTS_RESET = "points_reset"
    POINTS_VIEW = "points_view"
    
    # Game Management
    GAME_START = "game_start"
    GAME_END = "game_end"
    GAME_INTERVENE = "game_intervene"
    GAME_CANCEL = "game_cancel"
    GAME_SETTINGS_UPDATE = "game_settings_update"
    GAME_DISABLE = "game_disable"
    GAME_ENABLE = "game_enable"
    
    # Challenge Management
    CHALLENGE_CREATE = "challenge_create"
    CHALLENGE_UPDATE = "challenge_update"
    CHALLENGE_DELETE = "challenge_delete"
    CHALLENGE_DISABLE = "challenge_disable"
    CHALLENGE_ENABLE = "challenge_enable"
    CHALLENGE_SKIP = "challenge_skip"
    
    # Achievement Management
    ACHIEVEMENT_CREATE = "achievement_create"
    ACHIEVEMENT_UPDATE = "achievement_update"
    ACHIEVEMENT_DELETE = "achievement_delete"
    ACHIEVEMENT_GRANT = "achievement_grant"
    ACHIEVEMENT_REVOKE = "achievement_revoke"
    ACHIEVEMENT_DISABLE = "achievement_disable"
    ACHIEVEMENT_ENABLE = "achievement_enable"
    
    # Leaderboard Management
    LEADERBOARD_VIEW = "leaderboard_view"
    LEADERBOARD_RESET = "leaderboard_reset"
    LEADERBOARD_EXPORT = "leaderboard_export"
    LEADERBOARD_CLEAR = "leaderboard_clear"
    
    # Referral Management
    REFERRAL_VIEW = "referral_view"
    REFERRAL_CLEAR = "referral_clear"
    REFERRAL_BLOCK = "referral_block"
    
    # Match Management
    MATCH_VIEW = "match_view"
    MATCH_CANCEL = "match_cancel"
    MATCH_OVERRIDE = "match_override"
    MATCH_RESET = "match_reset"
    
    # System Management
    SYSTEM_MAINTENANCE = "system_maintenance"
    SYSTEM_BACKUP = "system_backup"
    SYSTEM_RESTORE = "system_restore"
    SYSTEM_UPDATE = "system_update"
    SYSTEM_REBOOT = "system_reboot"
    SYSTEM_CLEAR_CACHE = "system_clear_cache"
    
    # Broadcast
    BROADCAST_SEND = "broadcast_send"
    BROADCAST_SCHEDULE = "broadcast_schedule"
    BROADCAST_CANCEL = "broadcast_cancel"
    BROADCAST_VIEW = "broadcast_view"
    
    # Anti-Cheat
    ANTI_CHEAT_VIEW = "anti_cheat_view"
    ANTI_CHEAT_RESOLVE = "anti_cheat_resolve"
    ANTI_CHEAT_DISMISS = "anti_cheat_dismiss"
    ANTI_CHEAT_RULES_UPDATE = "anti_cheat_rules_update"
    
    # Configuration
    CONFIG_UPDATE = "config_update"
    CONFIG_VIEW = "config_view"
    CONFIG_EXPORT = "config_export"
    CONFIG_IMPORT = "config_import"
    CONFIG_RESET = "config_reset"
    
    # Audit
    AUDIT_VIEW = "audit_view"
    AUDIT_EXPORT = "audit_export"
    AUDIT_CLEAR = "audit_clear"
    
    @classmethod
    def list(cls) -> List[str]:
        return [action.value for action in cls]
    
    @classmethod
    def get_display_name(cls, action_type: str) -> str:
        """Get display name for action type"""
        names = {
            "user_view": "View User",
            "user_search": "Search Users",
            "user_ban": "Ban User",
            "user_unban": "Unban User",
            "user_kick": "Kick User",
            "user_warn": "Warn User",
            "user_mute": "Mute User",
            "user_unmute": "Unmute User",
            "user_delete": "Delete User",
            "user_restore": "Restore User",
            "user_role_change": "Change User Role",
            "user_verify": "Verify User",
            "user_unverify": "Unverify User",
            "points_add": "Add Points",
            "points_remove": "Remove Points",
            "points_adjust": "Adjust Points",
            "points_reset": "Reset Points",
            "points_view": "View Points",
            "game_start": "Start Game",
            "game_end": "End Game",
            "game_intervene": "Intervene in Game",
            "game_cancel": "Cancel Game",
            "game_settings_update": "Update Game Settings",
            "game_disable": "Disable Game",
            "game_enable": "Enable Game",
            "challenge_create": "Create Challenge",
            "challenge_update": "Update Challenge",
            "challenge_delete": "Delete Challenge",
            "challenge_disable": "Disable Challenge",
            "challenge_enable": "Enable Challenge",
            "challenge_skip": "Skip Challenge",
            "achievement_create": "Create Achievement",
            "achievement_update": "Update Achievement",
            "achievement_delete": "Delete Achievement",
            "achievement_grant": "Grant Achievement",
            "achievement_revoke": "Revoke Achievement",
            "achievement_disable": "Disable Achievement",
            "achievement_enable": "Enable Achievement",
            "leaderboard_view": "View Leaderboard",
            "leaderboard_reset": "Reset Leaderboard",
            "leaderboard_export": "Export Leaderboard",
            "leaderboard_clear": "Clear Leaderboard",
            "referral_view": "View Referrals",
            "referral_clear": "Clear Referrals",
            "referral_block": "Block Referral",
            "match_view": "View Match",
            "match_cancel": "Cancel Match",
            "match_override": "Override Match",
            "match_reset": "Reset Match",
            "system_maintenance": "System Maintenance",
            "system_backup": "System Backup",
            "system_restore": "System Restore",
            "system_update": "System Update",
            "system_reboot": "System Reboot",
            "system_clear_cache": "Clear Cache",
            "broadcast_send": "Send Broadcast",
            "broadcast_schedule": "Schedule Broadcast",
            "broadcast_cancel": "Cancel Broadcast",
            "broadcast_view": "View Broadcasts",
            "anti_cheat_view": "View Anti-Cheat",
            "anti_cheat_resolve": "Resolve Anti-Cheat",
            "anti_cheat_dismiss": "Dismiss Anti-Cheat",
            "anti_cheat_rules_update": "Update Anti-Cheat Rules",
            "config_update": "Update Configuration",
            "config_view": "View Configuration",
            "config_export": "Export Configuration",
            "config_import": "Import Configuration",
            "config_reset": "Reset Configuration",
            "audit_view": "View Audit Log",
            "audit_export": "Export Audit Log",
            "audit_clear": "Clear Audit Log",
        }
        return names.get(action_type, action_type.replace('_', ' ').title())


class AdminActionSeverity(str, enum.Enum):
    """Severity levels for admin actions"""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    
    @classmethod
    def list(cls) -> List[str]:
        return [severity.value for severity in cls]
    
    @classmethod
    def get_color(cls, severity: str) -> str:
        """Get color for severity"""
        colors = {
            "info": "#00FF00",
            "low": "#FFFF00",
            "medium": "#FFA500",
            "high": "#FF0000",
            "critical": "#8B0000"
        }
        return colors.get(severity, "#FFFFFF")


class AdminActionStatus(str, enum.Enum):
    """Status of admin actions"""
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    PENDING = "pending"
    CANCELLED = "cancelled"


# ==================== Admin Log Model ====================
class AdminLog(Base):
    """Admin action audit log"""
    
    __tablename__ = "admin_logs"
    __table_args__ = (
        Index("idx_admin_logs_admin", "admin_id"),
        Index("idx_admin_logs_action_type", "action_type"),
        Index("idx_admin_logs_target_type", "target_type"),
        Index("idx_admin_logs_severity", "severity"),
        Index("idx_admin_logs_status", "status"),
        Index("idx_admin_logs_created_at", "created_at"),
        Index("idx_admin_logs_ip_address", "ip_address"),
        Index("idx_admin_logs_admin_action", "admin_id", "action_type"),
        Index("idx_admin_logs_target", "target_type", "target_id"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    log_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    
    # Admin
    admin_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    admin_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Action
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    action_display: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Target
    target_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    target_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    target_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    
    # Details
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    before_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    after_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Metadata
    severity: Mapped[str] = mapped_column(String(20), default=AdminActionSeverity.INFO.value, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=AdminActionStatus.SUCCESS.value, nullable=False)
    
    # Error information
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_stack: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Request information
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Metadata
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    admin: Mapped[Optional["User"]] = relationship("User", foreign_keys=[admin_id])

    def __init__(self, **kwargs):
        if 'log_id' not in kwargs or not kwargs['log_id']:
            kwargs['log_id'] = self._generate_log_id()
        if 'action_display' not in kwargs or not kwargs['action_display']:
            kwargs['action_display'] = AdminActionType.get_display_name(kwargs.get('action_type', ''))
        super().__init__(**kwargs)

    # ==================== Properties ====================
    
    @staticmethod
    def _generate_log_id() -> str:
        """Generate unique log ID"""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        random_part = uuid.uuid4().hex[:8].upper()
        return f"ADMIN{timestamp}{random_part}"
    
    @hybrid_property
    def severity_color(self) -> str:
        """Get color for severity"""
        return AdminActionSeverity.get_color(self.severity)
    
    @hybrid_property
    def severity_display(self) -> str:
        """Get display name for severity"""
        return self.severity.title()
    
    @hybrid_property
    def status_display(self) -> str:
        """Get display name for status"""
        return self.status.title()
    
    @hybrid_property
    def is_success(self) -> bool:
        """Check if action was successful"""
        return self.status == AdminActionStatus.SUCCESS.value
    
    @hybrid_property
    def is_failed(self) -> bool:
        """Check if action failed"""
        return self.status == AdminActionStatus.FAILED.value
    
    @hybrid_property
    def days_ago(self) -> int:
        """Get days since action"""
        return (datetime.utcnow() - self.created_at).days
    
    @hybrid_property
    def time_ago(self) -> str:
        """Get time since action"""
        delta = datetime.utcnow() - self.created_at
        if delta.days > 0:
            return f"{delta.days}d ago"
        elif delta.seconds > 3600:
            return f"{delta.seconds // 3600}h ago"
        elif delta.seconds > 60:
            return f"{delta.seconds // 60}m ago"
        else:
            return "Just now"
    
    @hybrid_property
    def admin_name(self) -> str:
        """Get admin display name"""
        if self.admin:
            return self.admin.display_name or self.admin.full_name
        return self.admin_username or "Unknown Admin"
    
    @hybrid_property
    def target_display(self) -> str:
        """Get target display name"""
        if self.target_name:
            return self.target_name
        if self.target_type and self.target_id:
            return f"{self.target_type} #{self.target_id}"
        return "N/A"

    # ==================== Factory Methods ====================
    
    @classmethod
    def create_user_action(
        cls,
        admin_id: int,
        action_type: str,
        target_user_id: int,
        target_username: str,
        details: Dict[str, Any] = None,
        severity: str = AdminActionSeverity.MEDIUM.value,
        ip_address: str = None
    ) -> "AdminLog":
        """Create a user-related admin log"""
        return cls(
            admin_id=admin_id,
            action_type=action_type,
            target_type="user",
            target_id=target_user_id,
            target_name=target_username,
            details=details or {},
            severity=severity,
            ip_address=ip_address
        )
    
    @classmethod
    def create_game_action(
        cls,
        admin_id: int,
        action_type: str,
        game_type: str,
        game_id: int = None,
        details: Dict[str, Any] = None,
        severity: str = AdminActionSeverity.MEDIUM.value,
        ip_address: str = None
    ) -> "AdminLog":
        """Create a game-related admin log"""
        return cls(
            admin_id=admin_id,
            action_type=action_type,
            target_type="game",
            target_id=game_id,
            target_name=game_type,
            details=details or {},
            severity=severity,
            ip_address=ip_address
        )
    
    @classmethod
    def create_points_action(
        cls,
        admin_id: int,
        action_type: str,
        target_user_id: int,
        target_username: str,
        amount: int,
        reason: str,
        before_state: Dict[str, Any] = None,
        after_state: Dict[str, Any] = None,
        severity: str = AdminActionSeverity.HIGH.value,
        ip_address: str = None
    ) -> "AdminLog":
        """Create a points-related admin log"""
        details = {
            "amount": amount,
            "reason": reason
        }
        return cls(
            admin_id=admin_id,
            action_type=action_type,
            target_type="user",
            target_id=target_user_id,
            target_name=target_username,
            details=details,
            before_state=before_state,
            after_state=after_state,
            severity=severity,
            ip_address=ip_address
        )
    
    @classmethod
    def create_system_action(
        cls,
        admin_id: int,
        action_type: str,
        details: Dict[str, Any] = None,
        severity: str = AdminActionSeverity.CRITICAL.value,
        ip_address: str = None
    ) -> "AdminLog":
        """Create a system-related admin log"""
        return cls(
            admin_id=admin_id,
            action_type=action_type,
            target_type="system",
            details=details or {},
            severity=severity,
            ip_address=ip_address
        )
    
    @classmethod
    def create_anti_cheat_action(
        cls,
        admin_id: int,
        action_type: str,
        target_user_id: int,
        target_username: str,
        details: Dict[str, Any] = None,
        severity: str = AdminActionSeverity.HIGH.value,
        ip_address: str = None
    ) -> "AdminLog":
        """Create an anti-cheat related admin log"""
        return cls(
            admin_id=admin_id,
            action_type=action_type,
            target_type="user",
            target_id=target_user_id,
            target_name=target_username,
            details=details or {},
            severity=severity,
            ip_address=ip_address
        )
    
    # ==================== Methods ====================
    
    def set_status(self, status: str) -> None:
        """Set the status of the action"""
        self.status = status
    
    def set_success(self) -> None:
        """Mark action as successful"""
        self.status = AdminActionStatus.SUCCESS.value
    
    def set_failed(self, error: str, stack: str = None) -> None:
        """Mark action as failed"""
        self.status = AdminActionStatus.FAILED.value
        self.error_message = error
        self.error_stack = stack
    
    def add_details(self, details: Dict[str, Any]) -> None:
        """Add details to the log"""
        if not self.details:
            self.details = {}
        self.details.update(details)
    
    def set_before_state(self, state: Dict[str, Any]) -> None:
        """Set the before state"""
        self.before_state = state
    
    def set_after_state(self, state: Dict[str, Any]) -> None:
        """Set the after state"""
        self.after_state = state
    
    def validate_ip(self) -> bool:
        """Validate IP address format"""
        if not self.ip_address:
            return True
        try:
            ipaddress.ip_address(self.ip_address)
            return True
        except ValueError:
            return False
    
    # ==================== Dictionary Methods ====================
    
    def to_dict(self, include_admin: bool = False, include_state: bool = False) -> Dict[str, Any]:
        """Convert admin log to dictionary"""
        data = {
            "id": self.id,
            "log_id": self.log_id,
            "admin_id": self.admin_id,
            "admin_name": self.admin_name,
            "action_type": self.action_type,
            "action_display": self.action_display,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "target_display": self.target_display,
            "details": self.details,
            "severity": self.severity,
            "severity_color": self.severity_color,
            "severity_display": self.severity_display,
            "status": self.status,
            "status_display": self.status_display,
            "is_success": self.is_success,
            "is_failed": self.is_failed,
            "error_message": self.error_message,
            "ip_address": self.ip_address,
            "metadata": self.metadata,
            "time_ago": self.time_ago,
            "days_ago": self.days_ago,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        
        if include_admin and self.admin:
            data["admin"] = {
                "id": self.admin.id,
                "telegram_id": self.admin.telegram_id,
                "username": self.admin.username,
                "display_name": self.admin.display_name,
                "is_admin": self.admin.is_admin,
            }
        
        if include_state:
            data["before_state"] = self.before_state
            data["after_state"] = self.after_state
        
        return data
    
    def to_summary(self) -> Dict[str, Any]:
        """Get a summary of the admin action"""
        return {
            "log_id": self.log_id,
            "admin": self.admin_name,
            "action": self.action_display,
            "target": self.target_display,
            "status": self.status_display,
            "severity": self.severity_display,
            "time": self.time_ago,
        }
    
    def __repr__(self) -> str:
        return f"<AdminLog(id={self.id}, log_id={self.log_id}, admin_id={self.admin_id}, action={self.action_type}, status={self.status})>"


# ==================== Admin Session Model ====================
class AdminSession(Base):
    """Track admin sessions for activity monitoring"""
    
    __tablename__ = "admin_sessions"
    __table_args__ = (
        Index("idx_admin_sessions_admin", "admin_id"),
        Index("idx_admin_sessions_token", "session_token"),
        Index("idx_admin_sessions_status", "status"),
        Index("idx_admin_sessions_created_at", "created_at"),
        Index("idx_admin_sessions_expires_at", "expires_at"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    session_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    
    # Session details
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    
    # Activity tracking
    last_activity: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    activity_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    # Metadata
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    logged_out_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    admin: Mapped["User"] = relationship("User")

    def __init__(self, **kwargs):
        if 'session_token' not in kwargs or not kwargs['session_token']:
            kwargs['session_token'] = self._generate_session_token()
        if 'expires_at' not in kwargs:
            kwargs['expires_at'] = datetime.utcnow() + timedelta(days=7)
        super().__init__(**kwargs)

    @staticmethod
    def _generate_session_token() -> str:
        """Generate unique session token"""
        random_part = uuid.uuid4().hex[:32]
        return f"SESS{random_part.upper()}"

    @hybrid_property
    def is_active(self) -> bool:
        """Check if session is active"""
        return self.status == "active" and (not self.expires_at or datetime.utcnow() < self.expires_at)
    
    @hybrid_property
    def is_expired(self) -> bool:
        """Check if session is expired"""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False

    def update_activity(self) -> None:
        """Update last activity timestamp"""
        self.last_activity = datetime.utcnow()
        self.activity_count += 1

    def logout(self) -> None:
        """Logout the session"""
        self.status = "inactive"
        self.logged_out_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "admin_id": self.admin_id,
            "session_token": self.session_token,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "status": self.status,
            "is_active": self.is_active,
            "is_expired": self.is_expired,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None,
            "activity_count": self.activity_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "logged_out_at": self.logged_out_at.isoformat() if self.logged_out_at else None,
        }
    
    def __repr__(self) -> str:
        return f"<AdminSession(id={self.id}, admin_id={self.admin_id}, status={self.status})>"


# ==================== Admin Permission Model ====================
class AdminPermission(Base):
    """Admin permissions for granular access control"""
    
    __tablename__ = "admin_permissions"
    __table_args__ = (
        Index("idx_admin_permissions_admin", "admin_id"),
        Index("idx_admin_permissions_permission", "permission"),
        UniqueConstraint('admin_id', 'permission', name='uq_admin_permission'),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    permission: Mapped[str] = mapped_column(String(100), nullable=False)
    granted_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Metadata
    metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Relationships
    admin: Mapped["User"] = relationship("User")

    def revoke(self) -> None:
        """Revoke the permission"""
        self.is_active = False
        self.revoked_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "admin_id": self.admin_id,
            "permission": self.permission,
            "is_active": self.is_active,
            "granted_by": self.granted_by,
            "granted_at": self.granted_at.isoformat() if self.granted_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "metadata": self.metadata,
        }
    
    def __repr__(self) -> str:
        return f"<AdminPermission(id={self.id}, admin_id={self.admin_id}, permission={self.permission})>"


# ==================== Model Registration ====================
__all__ = [
    "AdminActionType",
    "AdminActionSeverity",
    "AdminActionStatus",
    "AdminLog",
    "AdminSession",
    "AdminPermission",
]
