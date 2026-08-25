from typing import AsyncGenerator, Optional, Dict, Any, TypeVar, Generic
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
    AsyncEngine,
    AsyncConnection
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.pool import NullPool, AsyncAdaptedQueuePool
from contextlib import asynccontextmanager
from datetime import datetime
import logging
from pathlib import Path

from src.core.config import settings

# Setup logger
logger = logging.getLogger(__name__)

# ==================== Naming Convention ====================
# SQLAlchemy naming convention for constraints
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# ==================== Base Model ====================
metadata = MetaData(naming_convention=convention)
Base = declarative_base(metadata=metadata)


# ==================== Mixins ====================
class TimestampMixin:
    """Mixin for timestamp fields"""
    created_at: datetime
    updated_at: datetime


class SoftDeleteMixin:
    """Mixin for soft delete functionality"""
    deleted_at: Optional[datetime]
    is_deleted: bool


# ==================== Database Manager ====================
class DatabaseManager:
    """
    Centralized database connection manager with async support
    Handles connection pooling, session management, and lifecycle
    """
    
    def __init__(self):
        self._engine: Optional[AsyncEngine] = None
        self._session_factory: Optional[async_sessionmaker] = None
        self._sync_engine = None
        self._initialized = False
        self._health_check_interval = 60  # seconds
        
    async def initialize(self) -> None:
        """
        Initialize database connection pool
        Creates async engine and session factory
        """
        if self._initialized:
            logger.warning("Database already initialized")
            return
        
        try:
            # Create async engine with connection pooling
            self._engine = create_async_engine(
                settings.DATABASE_URL,
                echo=settings.DB_ECHO,
                pool_size=settings.DB_POOL_SIZE,
                max_overflow=settings.DB_MAX_OVERFLOW,
                pool_pre_ping=settings.DB_POOL_PRE_PING,
                pool_recycle=settings.DB_POOL_RECYCLE,
                pool_timeout=30,
                pool_class=AsyncAdaptedQueuePool,
                connect_args={
                    "timeout": 10,
                    "command_timeout": 60,
                    "server_settings": {
                        "application_name": "gamepulse_bot",
                        "timezone": "UTC",
                    }
                }
            )
            
            # Create session factory
            self._session_factory = async_sessionmaker(
                self._engine,
                expire_on_commit=False,
                class_=AsyncSession,
                autocommit=False,
                autoflush=False,
            )
            
            # Create sync engine for migrations and administrative tasks
            sync_url = settings.DATABASE_URL.replace("+asyncpg", "").replace("postgresql", "postgresql")
            self._sync_engine = create_engine(
                sync_url,
                echo=settings.DB_ECHO,
                pool_size=5,
                max_overflow=10,
            )
            
            self._initialized = True
            logger.info(f"✅ Database initialized: {settings.POSTGRES_DB} on {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}")
            
            # Test connection
            await self._test_connection()
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize database: {e}")
            raise

    async def _test_connection(self) -> None:
        """Test database connection"""
        try:
            async with self._engine.connect() as conn:
                result = await conn.execute(text("SELECT 1"))
                await conn.commit()
                logger.info("✅ Database connection test successful")
        except Exception as e:
            logger.error(f"❌ Database connection test failed: {e}")
            raise

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a database session with automatic commit/rollback
        Usage: async with db.get_session() as session:
            # use session
        """
        if not self._initialized:
            await self.initialize()
        
        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()

    async def get_session_direct(self) -> AsyncSession:
        """
        Get a session directly without context manager
        Caller must handle commit/rollback/close
        """
        if not self._initialized:
            await self.initialize()
        return self._session_factory()

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[AsyncConnection, None]:
        """
        Get a raw database connection
        Useful for transactions and raw SQL
        """
        if not self._initialized:
            await self.initialize()
        
        async with self._engine.connect() as conn:
            try:
                yield conn
            except Exception as e:
                await conn.rollback()
                raise
            finally:
                await conn.close()

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform a health check on the database
        Returns status and performance metrics
        """
        result = {
            "status": "healthy",
            "connected": False,
            "response_time": None,
            "error": None
        }
        
        try:
            import time
            start_time = time.time()
            
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                await conn.commit()
            
            result["connected"] = True
            result["response_time"] = (time.time() - start_time) * 1000  # ms
            
        except Exception as e:
            result["status"] = "unhealthy"
            result["error"] = str(e)
            logger.error(f"Database health check failed: {e}")
        
        return result

    async def get_db_stats(self) -> Dict[str, Any]:
        """
        Get database statistics
        """
        stats = {
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_recycle": settings.DB_POOL_RECYCLE,
            "active_connections": 0,
            "total_connections": 0,
        }
        
        try:
            # Get connection pool stats
            if self._engine:
                pool = self._engine.pool
                stats["active_connections"] = pool.checkedin()
                stats["total_connections"] = pool.size()
        except Exception as e:
            logger.warning(f"Could not get pool stats: {e}")
        
        return stats

    async def run_migrations(self) -> None:
        """
        Run database migrations programmatically
        Uses alembic for migration management
        """
        try:
            from alembic.config import Config
            from alembic import command
            
            alembic_cfg = Config("alembic.ini")
            command.upgrade(alembic_cfg, "head")
            logger.info("✅ Migrations completed successfully")
            
        except ImportError:
            logger.warning("Alembic not installed, skipping migrations")
        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            raise

    async def create_tables(self, drop_first: bool = False) -> None:
        """
        Create all tables (for testing/development)
        """
        if drop_first:
            logger.warning("Dropping all tables...")
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
        
        logger.info("Creating tables...")
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("✅ Tables created successfully")

    async def close(self) -> None:
        """
        Close database connections and cleanup
        """
        if self._engine:
            await self._engine.dispose()
            logger.info("Database connections closed")
        
        if self._sync_engine:
            self._sync_engine.dispose()
        
        self._initialized = False

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# ==================== Global Instance ====================
db = DatabaseManager()


# ==================== Session Dependency ====================
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for getting database session
    """
    async with db.get_session() as session:
        yield session


# ==================== Transaction Utilities ====================
class TransactionManager:
    """
    Transaction manager for handling complex transactions
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self._savepoints = []
    
    async def begin(self) -> None:
        """Begin a transaction"""
        await self.session.begin()
    
    async def commit(self) -> None:
        """Commit the transaction"""
        await self.session.commit()
    
    async def rollback(self) -> None:
        """Rollback the transaction"""
        await self.session.rollback()
    
    async def begin_nested(self) -> None:
        """
        Begin a nested transaction (savepoint)
        """
        savepoint = await self.session.begin_nested()
        self._savepoints.append(savepoint)
        return savepoint
    
    async def rollback_nested(self) -> None:
        """
        Rollback the most recent savepoint
        """
        if self._savepoints:
            savepoint = self._savepoints.pop()
            await savepoint.rollback()


# ==================== Query Utilities ====================
class QueryHelper:
    """
    Helper class for common database operations
    """
    
    @staticmethod
    def paginate(query, page: int = 1, per_page: int = 20):
        """Add pagination to a query"""
        offset = (page - 1) * per_page
        return query.offset(offset).limit(per_page)
    
    @staticmethod
    def order_by_field(query, field, descending: bool = False):
        """Add order by to a query"""
        if descending:
            return query.order_by(field.desc())
        return query.order_by(field.asc())
    
    @staticmethod
    async def count_query(session: AsyncSession, query) -> int:
        """Get count from a query"""
        from sqlalchemy import func
        count_query = query.statement.with_only_columns(func.count()).order_by(None)
        result = await session.execute(count_query)
        return result.scalar()


# ==================== Migration Helper ====================
class MigrationHelper:
    """
    Helper for database migrations and schema management
    """
    
    @staticmethod
    async def get_current_version() -> Optional[str]:
        """Get current migration version"""
        try:
            from alembic.config import Config
            from alembic import command
            
            alembic_cfg = Config("alembic.ini")
            from alembic.runtime.migration import MigrationContext
            from sqlalchemy import create_engine
            
            sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
            engine = create_engine(sync_url)
            
            with engine.connect() as conn:
                context = MigrationContext.configure(conn)
                return context.get_current_revision()
                
        except Exception as e:
            logger.error(f"Could not get migration version: {e}")
            return None
    
    @staticmethod
    async def get_migration_history() -> list:
        """Get migration history"""
        try:
            from alembic.config import Config
            from alembic import command
            from io import StringIO
            
            alembic_cfg = Config("alembic.ini")
            output = StringIO()
            command.history(alembic_cfg, indicate_current=True, verbose=True)
            return output.getvalue().split('\n')
            
        except Exception as e:
            logger.error(f"Could not get migration history: {e}")
            return []


# ==================== Bulk Operations ====================
class BulkOperations:
    """
    Helper for bulk database operations
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def bulk_insert(self, model_class, data: list) -> None:
        """
        Bulk insert records
        """
        if not data:
            return
        
        self.session.add_all([model_class(**item) for item in data])
        await self.session.flush()
    
    async def bulk_update(self, model_class, updates: list) -> None:
        """
        Bulk update records
        """
        if not updates:
            return
        
        # Using bulk_update_mappings for efficiency
        await self.session.bulk_update_mappings(model_class, updates)
        await self.session.flush()


# ==================== Initialization ====================
async def init_database():
    """
    Initialize database and run migrations
    Call this during application startup
    """
    try:
        # Initialize database connection
        await db.initialize()
        
        # Run migrations
        await db.run_migrations()
        
        logger.info("✅ Database initialization complete")
        
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        raise


# ==================== Health Check Endpoint ====================
async def database_health_check() -> Dict[str, Any]:
    """
    FastAPI health check endpoint for database
    """
    return await db.health_check()


# ==================== Session Context Manager ====================
@asynccontextmanager
async def session_context():
    """
    Context manager for database sessions
    Usage: async with session_context() as session:
        # use session
    """
    async with db.get_session() as session:
        yield session


# ==================== Database Listener ====================
class DatabaseEventListener:
    """
    Database event listeners for auditing and logging
    """
    
    @staticmethod
    def register_listeners():
        """Register SQLAlchemy event listeners"""
        from sqlalchemy import event
        
        # Listen for before/after insert
        @event.listens_for(Base, 'before_insert', propagate=True)
        def before_insert(mapper, connection, target):
            if hasattr(target, 'created_at'):
                target.created_at = datetime.utcnow()
            if hasattr(target, 'updated_at'):
                target.updated_at = datetime.utcnow()
        
        # Listen for before/after update
        @event.listens_for(Base, 'before_update', propagate=True)
        def before_update(mapper, connection, target):
            if hasattr(target, 'updated_at'):
                target.updated_at = datetime.utcnow()
        
        logger.info("Database event listeners registered")


# ==================== Initialize Event Listeners ====================
DatabaseEventListener.register_listeners()


# ==================== Convenience Functions ====================
def get_base():
    """Get the declarative base"""
    return Base


def get_metadata():
    """Get the metadata object"""
    return metadata


async def ensure_db_initialized():
    """
    Ensure database is initialized before use
    """
    if not db._initialized:
        await db.initialize()


# ==================== Startup/Shutdown ====================
async def startup():
    """Application startup hook"""
    await init_database()


async def shutdown():
    """Application shutdown hook"""
    await db.close()


# ==================== Testing Helpers ====================
class TestDatabase:
    """
    Helper for testing with a test database
    """
    
    def __init__(self):
        self.original_url = settings.DATABASE_URL
    
    async def setup_test_db(self):
        """Setup test database with fresh schema"""
        # Use a test database
        test_url = self.original_url.replace("/gamepulse", "/gamepulse_test")
        settings.DATABASE_URL = test_url
        
        await db.initialize()
        await db.create_tables(drop_first=True)
        
        logger.info("✅ Test database setup complete")
    
    async def teardown_test_db(self):
        """Teardown test database"""
        await db.close()
        settings.DATABASE_URL = self.original_url
        logger.info("✅ Test database teardown complete")


# ==================== Usage Example ====================
if __name__ == "__main__":
    import asyncio
    
    async def example():
        # Initialize database
        await db.initialize()
        
        # Get a session
        async with db.get_session() as session:
            # Your database operations here
            result = await session.execute(text("SELECT version()"))
            version = result.scalar()
            print(f"PostgreSQL version: {version}")
        
        # Health check
        health = await db.health_check()
        print(f"Health check: {health}")
        
        # Get stats
        stats = await db.get_db_stats()
        print(f"Database stats: {stats}")
        
        # Close connection
        await db.close()
    
    asyncio.run(example())
