import json
import pickle
from typing import Optional, Any, Dict, List, Set, Union, Tuple
from datetime import datetime, timedelta
import redis.asyncio as redis
from redis.asyncio import Redis
from redis.exceptions import RedisError, ConnectionError, TimeoutError
from contextlib import asynccontextmanager
import logging
import asyncio
from functools import wraps

from src.core.config import settings

logger = logging.getLogger(__name__)


# ==================== Redis Manager ====================
class RedisManager:
    """
    Centralized Redis connection manager with caching, rate limiting,
    and session management capabilities.
    """
    
    def __init__(self):
        self._client: Optional[Redis] = None
        self._pubsub_client: Optional[Redis] = None
        self._initialized = False
        self._lock = asyncio.Lock()
        self._health_check_interval = 30  # seconds
        
    async def initialize(self) -> None:
        """
        Initialize Redis connection pool
        """
        if self._initialized:
            logger.warning("Redis already initialized")
            return
        
        async with self._lock:
            if self._initialized:
                return
            
            try:
                # Create main client with connection pool
                self._client = redis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    max_connections=20,
                    socket_timeout=5,
                    socket_connect_timeout=5,
                    retry_on_timeout=True,
                    health_check_interval=self._health_check_interval,
                )
                
                # Create pub/sub client (separate connection)
                self._pubsub_client = redis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    max_connections=5,
                    socket_timeout=5,
                    socket_connect_timeout=5,
                )
                
                # Test connection
                await self._test_connection()
                
                self._initialized = True
                logger.info(f"✅ Redis initialized: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
                
            except Exception as e:
                logger.error(f"❌ Failed to initialize Redis: {e}")
                raise

    async def _test_connection(self) -> None:
        """Test Redis connection"""
        try:
            await self._client.ping()
            logger.info("✅ Redis connection test successful")
        except Exception as e:
            logger.error(f"❌ Redis connection test failed: {e}")
            raise

    async def get_client(self) -> Redis:
        """
        Get Redis client instance
        Initializes if not already connected
        """
        if not self._initialized:
            await self.initialize()
        return self._client

    async def get_pubsub_client(self) -> Redis:
        """
        Get Redis pub/sub client instance
        """
        if not self._initialized:
            await self.initialize()
        return self._pubsub_client

    # ==================== Basic Operations ====================
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None,
        nx: bool = False,
        xx: bool = False
    ) -> bool:
        """
        Set value in Redis with optional TTL
        
        Args:
            key: Redis key
            value: Value to store (automatically serialized if needed)
            ttl: Time to live in seconds
            nx: Set only if key does not exist
            xx: Set only if key exists
        """
        client = await self.get_client()
        
        # Serialize if needed
        if isinstance(value, (dict, list, tuple, set)):
            value = json.dumps(value)
        elif isinstance(value, (datetime, timedelta)):
            value = value.isoformat()
        elif not isinstance(value, (str, int, float, bool)):
            # Fallback to pickle for complex objects
            value = pickle.dumps(value)
        
        try:
            if ttl:
                return await client.set(key, value, ex=ttl, nx=nx, xx=xx)
            return await client.set(key, value, nx=nx, xx=xx)
        except RedisError as e:
            logger.error(f"Redis set error for key {key}: {e}")
            return False

    async def get(self, key: str, deserialize: bool = True) -> Optional[Any]:
        """
        Get value from Redis
        
        Args:
            key: Redis key
            deserialize: Whether to deserialize JSON/pickle values
        """
        client = await self.get_client()
        
        try:
            value = await client.get(key)
            if value is None:
                return None
            
            if deserialize:
                # Try JSON first
                if isinstance(value, str):
                    try:
                        return json.loads(value)
                    except json.JSONDecodeError:
                        # Try pickle
                        try:
                            return pickle.loads(value.encode('latin1'))
                        except:
                            return value
            return value
            
        except RedisError as e:
            logger.error(f"Redis get error for key {key}: {e}")
            return None

    async def delete(self, *keys: str) -> int:
        """
        Delete one or more keys
        """
        client = await self.get_client()
        try:
            return await client.delete(*keys)
        except RedisError as e:
            logger.error(f"Redis delete error for keys {keys}: {e}")
            return 0

    async def exists(self, *keys: str) -> int:
        """
        Check if key(s) exist
        """
        client = await self.get_client()
        try:
            return await client.exists(*keys)
        except RedisError as e:
            logger.error(f"Redis exists error for keys {keys}: {e}")
            return 0

    async def expire(self, key: str, ttl: int) -> bool:
        """
        Set expiration on key
        """
        client = await self.get_client()
        try:
            return await client.expire(key, ttl)
        except RedisError as e:
            logger.error(f"Redis expire error for key {key}: {e}")
            return False

    async def ttl(self, key: str) -> int:
        """
        Get TTL of key
        """
        client = await self.get_client()
        try:
            return await client.ttl(key)
        except RedisError as e:
            logger.error(f"Redis ttl error for key {key}: {e}")
            return -2

    # ==================== Hash Operations ====================
    
    async def hset(
        self, 
        key: str, 
        field: str, 
        value: Any,
        ttl: Optional[int] = None
    ) -> int:
        """
        Set hash field
        """
        client = await self.get_client()
        
        if isinstance(value, (dict, list, tuple, set)):
            value = json.dumps(value)
        
        try:
            result = await client.hset(key, field, value)
            if ttl:
                await client.expire(key, ttl)
            return result
        except RedisError as e:
            logger.error(f"Redis hset error for key {key}: {e}")
            return 0

    async def hget(self, key: str, field: str) -> Optional[Any]:
        """
        Get hash field
        """
        client = await self.get_client()
        try:
            value = await client.hget(key, field)
            if value:
                try:
                    return json.loads(value)
                except:
                    return value
            return None
        except RedisError as e:
            logger.error(f"Redis hget error for key {key}: {e}")
            return None

    async def hgetall(self, key: str) -> Dict[str, Any]:
        """
        Get all hash fields
        """
        client = await self.get_client()
        try:
            data = await client.hgetall(key)
            # Deserialize JSON values
            result = {}
            for k, v in data.items():
                try:
                    result[k] = json.loads(v)
                except:
                    result[k] = v
            return result
        except RedisError as e:
            logger.error(f"Redis hgetall error for key {key}: {e}")
            return {}

    async def hdel(self, key: str, *fields: str) -> int:
        """
        Delete hash fields
        """
        client = await self.get_client()
        try:
            return await client.hdel(key, *fields)
        except RedisError as e:
            logger.error(f"Redis hdel error for key {key}: {e}")
            return 0

    async def hincrby(self, key: str, field: str, amount: int = 1) -> int:
        """
        Increment hash field
        """
        client = await self.get_client()
        try:
            return await client.hincrby(key, field, amount)
        except RedisError as e:
            logger.error(f"Redis hincrby error for key {key}: {e}")
            return 0

    # ==================== List Operations ====================
    
    async def lpush(self, key: str, *values: Any) -> int:
        """
        Push values to left of list
        """
        client = await self.get_client()
        try:
            # Serialize values
            serialized = []
            for v in values:
                if isinstance(v, (dict, list, tuple, set)):
                    serialized.append(json.dumps(v))
                else:
                    serialized.append(str(v))
            return await client.lpush(key, *serialized)
        except RedisError as e:
            logger.error(f"Redis lpush error for key {key}: {e}")
            return 0

    async def rpop(self, key: str) -> Optional[Any]:
        """
        Pop value from right of list
        """
        client = await self.get_client()
        try:
            value = await client.rpop(key)
            if value:
                try:
                    return json.loads(value)
                except:
                    return value
            return None
        except RedisError as e:
            logger.error(f"Redis rpop error for key {key}: {e}")
            return None

    async def lrange(self, key: str, start: int, end: int) -> List[Any]:
        """
        Get range from list
        """
        client = await self.get_client()
        try:
            values = await client.lrange(key, start, end)
            result = []
            for v in values:
                try:
                    result.append(json.loads(v))
                except:
                    result.append(v)
            return result
        except RedisError as e:
            logger.error(f"Redis lrange error for key {key}: {e}")
            return []

    # ==================== Set Operations ====================
    
    async def sadd(self, key: str, *values: Any) -> int:
        """
        Add values to set
        """
        client = await self.get_client()
        try:
            return await client.sadd(key, *[str(v) for v in values])
        except RedisError as e:
            logger.error(f"Redis sadd error for key {key}: {e}")
            return 0

    async def srem(self, key: str, *values: Any) -> int:
        """
        Remove values from set
        """
        client = await self.get_client()
        try:
            return await client.srem(key, *[str(v) for v in values])
        except RedisError as e:
            logger.error(f"Redis srem error for key {key}: {e}")
            return 0

    async def smembers(self, key: str) -> Set[str]:
        """
        Get all members of set
        """
        client = await self.get_client()
        try:
            return await client.smembers(key)
        except RedisError as e:
            logger.error(f"Redis smembers error for key {key}: {e}")
            return set()

    async def sismember(self, key: str, value: Any) -> bool:
        """
        Check if value is in set
        """
        client = await self.get_client()
        try:
            return await client.sismember(key, str(value))
        except RedisError as e:
            logger.error(f"Redis sismember error for key {key}: {e}")
            return False

    # ==================== Sorted Set Operations ====================
    
    async def zadd(self, key: str, mapping: Dict[str, float]) -> int:
        """
        Add members to sorted set with scores
        """
        client = await self.get_client()
        try:
            return await client.zadd(key, mapping)
        except RedisError as e:
            logger.error(f"Redis zadd error for key {key}: {e}")
            return 0

    async def zrange(
        self, 
        key: str, 
        start: int, 
        end: int, 
        withscores: bool = False
    ) -> Union[List[str], List[Tuple[str, float]]]:
        """
        Get range from sorted set
        """
        client = await self.get_client()
        try:
            return await client.zrange(key, start, end, withscores=withscores)
        except RedisError as e:
            logger.error(f"Redis zrange error for key {key}: {e}")
            return []

    async def zrevrange(
        self, 
        key: str, 
        start: int, 
        end: int, 
        withscores: bool = False
    ) -> Union[List[str], List[Tuple[str, float]]]:
        """
        Get reverse range from sorted set
        """
        client = await self.get_client()
        try:
            return await client.zrevrange(key, start, end, withscores=withscores)
        except RedisError as e:
            logger.error(f"Redis zrevrange error for key {key}: {e}")
            return []

    async def zincrby(self, key: str, increment: float, member: str) -> float:
        """
        Increment score of member in sorted set
        """
        client = await self.get_client()
        try:
            return await client.zincrby(key, increment, member)
        except RedisError as e:
            logger.error(f"Redis zincrby error for key {key}: {e}")
            return 0.0

    async def zscore(self, key: str, member: str) -> Optional[float]:
        """
        Get score of member in sorted set
        """
        client = await self.get_client()
        try:
            return await client.zscore(key, member)
        except RedisError as e:
            logger.error(f"Redis zscore error for key {key}: {e}")
            return None

    async def zrem(self, key: str, *members: str) -> int:
        """
        Remove members from sorted set
        """
        client = await self.get_client()
        try:
            return await client.zrem(key, *members)
        except RedisError as e:
            logger.error(f"Redis zrem error for key {key}: {e}")
            return 0

    # ==================== Atomic Operations ====================
    
    async def incr(self, key: str, amount: int = 1) -> int:
        """
        Increment key by amount
        """
        client = await self.get_client()
        try:
            return await client.incr(key, amount)
        except RedisError as e:
            logger.error(f"Redis incr error for key {key}: {e}")
            return 0

    async def decr(self, key: str, amount: int = 1) -> int:
        """
        Decrement key by amount
        """
        client = await self.get_client()
        try:
            return await client.decr(key, amount)
        except RedisError as e:
            logger.error(f"Redis decr error for key {key}: {e}")
            return 0

    # ==================== Lock Operations ====================
    
    async def acquire_lock(
        self, 
        lock_key: str, 
        timeout: int = 10, 
        blocking_timeout: Optional[int] = None
    ) -> bool:
        """
        Acquire a distributed lock
        
        Args:
            lock_key: Lock key
            timeout: Lock timeout in seconds
            blocking_timeout: Time to wait for lock
        """
        client = await self.get_client()
        try:
            # Use SET with NX and EX for atomic lock acquisition
            acquired = await client.set(
                lock_key, 
                "locked", 
                nx=True, 
                ex=timeout
            )
            
            if acquired or blocking_timeout is None:
                return bool(acquired)
            
            # Block until lock is acquired
            start_time = datetime.utcnow()
            while (datetime.utcnow() - start_time).seconds < blocking_timeout:
                acquired = await client.set(lock_key, "locked", nx=True, ex=timeout)
                if acquired:
                    return True
                await asyncio.sleep(0.1)
            
            return False
            
        except RedisError as e:
            logger.error(f"Redis acquire_lock error for key {lock_key}: {e}")
            return False

    async def release_lock(self, lock_key: str) -> bool:
        """
        Release a distributed lock
        """
        client = await self.get_client()
        try:
            return bool(await client.delete(lock_key))
        except RedisError as e:
            logger.error(f"Redis release_lock error for key {lock_key}: {e}")
            return False

    # ==================== Pub/Sub Operations ====================
    
    async def publish(self, channel: str, message: Any) -> int:
        """
        Publish message to channel
        """
        client = await self.get_client()
        try:
            if isinstance(message, (dict, list, tuple)):
                message = json.dumps(message)
            return await client.publish(channel, message)
        except RedisError as e:
            logger.error(f"Redis publish error for channel {channel}: {e}")
            return 0

    async def subscribe(self, *channels: str):
        """
        Subscribe to channels
        """
        client = await self.get_pubsub_client()
        return client.pubsub()

    # ==================== Pipeline Operations ====================
    
    @asynccontextmanager
    async def pipeline(self):
        """
        Execute multiple commands in a pipeline
        """
        client = await self.get_client()
        async with client.pipeline(transaction=True) as pipe:
            try:
                yield pipe
                await pipe.execute()
            except Exception as e:
                logger.error(f"Redis pipeline error: {e}")
                raise

    # ==================== Cache Operations ====================
    
    async def cache_get_or_set(
        self, 
        key: str, 
        callback, 
        ttl: Optional[int] = None,
        force_refresh: bool = False
    ) -> Any:
        """
        Get from cache or execute callback and cache result
        """
        if not force_refresh:
            cached = await self.get(key)
            if cached is not None:
                return cached
        
        # Execute callback to get value
        value = await callback()
        if value is not None:
            await self.set(key, value, ttl=ttl)
        return value

    async def cache_clear_pattern(self, pattern: str) -> int:
        """
        Clear all keys matching pattern
        """
        client = await self.get_client()
        try:
            keys = await client.keys(pattern)
            if keys:
                return await client.delete(*keys)
            return 0
        except RedisError as e:
            logger.error(f"Redis cache_clear_pattern error for pattern {pattern}: {e}")
            return 0

    # ==================== Health Check ====================
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform Redis health check
        """
        result = {
            "status": "healthy",
            "connected": False,
            "response_time": None,
            "info": {},
            "error": None
        }
        
        try:
            import time
            start_time = time.time()
            
            client = await self.get_client()
            await client.ping()
            
            result["connected"] = True
            result["response_time"] = (time.time() - start_time) * 1000  # ms
            
            # Get Redis info
            try:
                info = await client.info()
                result["info"] = {
                    "redis_version": info.get("redis_version"),
                    "uptime_seconds": info.get("uptime_in_seconds"),
                    "connected_clients": info.get("connected_clients"),
                    "used_memory_human": info.get("used_memory_human"),
                    "total_commands_processed": info.get("total_commands_processed"),
                }
            except:
                pass
            
        except Exception as e:
            result["status"] = "unhealthy"
            result["error"] = str(e)
            logger.error(f"Redis health check failed: {e}")
        
        return result

    # ==================== Cleanup ====================
    
    async def close(self) -> None:
        """
        Close Redis connections
        """
        if self._client:
            await self._client.close()
            logger.info("Redis client connection closed")
        
        if self._pubsub_client:
            await self._pubsub_client.close()
            logger.info("Redis pub/sub client connection closed")
        
        self._initialized = False


# ==================== Global Instance ====================
redis_manager = RedisManager()


# ==================== Decorators ====================

def cached(ttl: Optional[int] = None, key_prefix: str = ""):
    """
    Decorator for caching function results in Redis
    
    Usage:
        @cached(ttl=300)
        async def get_user_data(user_id: int):
            return await fetch_user_from_db(user_id)
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            key_parts = [key_prefix or func.__name__]
            
            # Add args and kwargs to key
            if args:
                key_parts.extend([str(arg) for arg in args])
            if kwargs:
                key_parts.extend([f"{k}:{v}" for k, v in sorted(kwargs.items())])
            
            cache_key = ":".join(key_parts)
            
            # Try to get from cache
            cached_value = await redis_manager.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Cache result
            if result is not None:
                await redis_manager.set(cache_key, result, ttl=ttl)
            
            return result
        return wrapper
    return decorator


def rate_limit(requests: int, period: int = 60):
    """
    Decorator for rate limiting
    
    Usage:
        @rate_limit(requests=30, period=60)
        async def handle_request(user_id: int):
            # Process request
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get user_id from args or kwargs
            user_id = None
            if args and len(args) > 0:
                user_id = args[0]
            elif "user_id" in kwargs:
                user_id = kwargs["user_id"]
            
            if user_id is None:
                return await func(*args, **kwargs)
            
            # Rate limit key
            rate_key = f"rate_limit:{func.__name__}:{user_id}"
            
            # Get current count
            client = await redis_manager.get_client()
            current = await client.incr(rate_key)
            
            if current == 1:
                await client.expire(rate_key, period)
            
            if current > requests:
                logger.warning(f"Rate limit exceeded for user {user_id} on {func.__name__}")
                raise Exception(f"Rate limit exceeded. Try again in {period} seconds.")
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def lock(lock_ttl: int = 10):
    """
    Decorator for distributed locking
    
    Usage:
        @lock(lock_ttl=5)
        async def process_transaction(user_id: int):
            # Process transaction
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate lock key
            lock_key = f"lock:{func.__name__}"
            
            # Add user_id to lock key if available
            user_id = None
            if args and len(args) > 0:
                user_id = args[0]
            elif "user_id" in kwargs:
                user_id = kwargs["user_id"]
            
            if user_id:
                lock_key = f"{lock_key}:{user_id}"
            
            # Acquire lock
            acquired = await redis_manager.acquire_lock(
                lock_key, 
                timeout=lock_ttl, 
                blocking_timeout=lock_ttl
            )
            
            if not acquired:
                raise Exception("Could not acquire lock. Operation in progress.")
            
            try:
                return await func(*args, **kwargs)
            finally:
                await redis_manager.release_lock(lock_key)
        return wrapper
    return decorator


# ==================== Convenience Functions ====================

async def get_redis_client() -> Redis:
    """Get Redis client instance"""
    return await redis_manager.get_client()


async def clear_cache(pattern: str = "*") -> int:
    """Clear cache by pattern"""
    return await redis_manager.cache_clear_pattern(pattern)


async def redis_health_check() -> Dict[str, Any]:
    """Health check for Redis"""
    return await redis_manager.health_check()


# ==================== Startup/Shutdown ====================

async def startup_redis():
    """Initialize Redis on startup"""
    await redis_manager.initialize()
    logger.info("✅ Redis startup complete")


async def shutdown_redis():
    """Close Redis on shutdown"""
    await redis_manager.close()
    logger.info("✅ Redis shutdown complete")


# ==================== Testing Helpers ====================

class TestRedis:
    """
    Helper for testing with Redis
    """
    
    def __init__(self):
        self.original_url = settings.REDIS_URL
    
    async def setup_test_redis(self):
        """Setup test Redis with clean state"""
        # Use a test database
        test_url = self.original_url.replace("/0", "/1")
        settings.REDIS_URL = test_url
        
        await redis_manager.initialize()
        
        # Clear test database
        await redis_manager.cache_clear_pattern("*")
        
        logger.info("✅ Test Redis setup complete")
    
    async def teardown_test_redis(self):
        """Teardown test Redis"""
        await redis_manager.close()
        settings.REDIS_URL = self.original_url
        logger.info("✅ Test Redis teardown complete")


# ==================== Usage Example ====================
if __name__ == "__main__":
    import asyncio
    
    async def example():
        # Initialize Redis
        await redis_manager.initialize()
        
        # Set/get values
        await redis_manager.set("test_key", {"name": "GamePulse", "version": "1.0"}, ttl=60)
        value = await redis_manager.get("test_key")
        print(f"Value: {value}")
        
        # Hash operations
        await redis_manager.hset("user:1", "name", "John")
        await redis_manager.hset("user:1", "score", 100)
        user_data = await redis_manager.hgetall("user:1")
        print(f"User: {user_data}")
        
        # Health check
        health = await redis_manager.health_check()
        print(f"Health: {health}")
        
        # Close connection
        await redis_manager.close()
    
    asyncio.run(example())
