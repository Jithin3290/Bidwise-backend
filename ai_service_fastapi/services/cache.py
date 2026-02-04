# services/cache.py - In-Memory Cache Service

from cachetools import TTLCache
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


class CacheService:
    """TTL-based in-memory cache service"""
    
    def __init__(self, maxsize: int = 1000, ttl: int = 3600):
        """
        Initialize cache with max size and TTL
        
        Args:
            maxsize: Maximum number of items to cache
            ttl: Time-to-live in seconds
        """
        self._cache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._ttl = ttl
        logger.info(f"Initialized cache with maxsize={maxsize}, ttl={ttl}s")
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        value = self._cache.get(key)
        if value is not None:
            logger.debug(f"Cache HIT: {key}")
        else:
            logger.debug(f"Cache MISS: {key}")
        return value
    
    def set(self, key: str, value: Any) -> None:
        """Set value in cache"""
        self._cache[key] = value
        logger.debug(f"Cache SET: {key}")
    
    def delete(self, key: str) -> bool:
        """Delete value from cache"""
        try:
            del self._cache[key]
            logger.debug(f"Cache DELETE: {key}")
            return True
        except KeyError:
            return False
    
    def clear(self) -> None:
        """Clear all cached values"""
        self._cache.clear()
        logger.info("Cache cleared")
    
    def get_stats(self) -> dict:
        """Get cache statistics"""
        return {
            "size": len(self._cache),
            "maxsize": self._cache.maxsize,
            "ttl": self._ttl,
            "currsize": self._cache.currsize
        }


# Global cache instance
_cache: Optional[CacheService] = None


def get_cache(ttl: int = 3600) -> CacheService:
    """Get or create the global cache instance"""
    global _cache
    if _cache is None:
        _cache = CacheService(maxsize=1000, ttl=ttl)
    return _cache
