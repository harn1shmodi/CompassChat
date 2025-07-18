import redis
import json
import hashlib
from typing import Optional, List, Dict, Any
from core.config import settings
import logging

logger = logging.getLogger(__name__)

class EmbeddingCache:
    """Redis-based cache for embeddings and summaries"""
    
    def __init__(self):
        try:
            self.redis_client = redis.Redis(
                host=getattr(settings, 'redis_host', 'localhost'),
                port=getattr(settings, 'redis_port', 6379),
                db=getattr(settings, 'redis_db', 0),
                decode_responses=True
            )
            # Test connection
            self.redis_client.ping()
            self.cache_enabled = True
            logger.info("Redis cache initialized successfully")
        except Exception as e:
            logger.warning(f"Redis cache not available: {e}")
            self.cache_enabled = False
    
    def _get_cache_key(self, text: str, prefix: str) -> str:
        """Generate cache key for text"""
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return f"{prefix}:{text_hash}"
    
    def get_embedding(self, text: str) -> Optional[List[float]]:
        """Get cached embedding"""
        if not self.cache_enabled:
            return None
        
        try:
            key = self._get_cache_key(text, "embedding")
            cached = self.redis_client.get(key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Error retrieving cached embedding: {e}")
        
        return None
    
    def set_embedding(self, text: str, embedding: List[float], ttl: int = 86400):
        """Cache embedding with TTL (default 24 hours)"""
        if not self.cache_enabled:
            return
        
        try:
            key = self._get_cache_key(text, "embedding")
            self.redis_client.setex(key, ttl, json.dumps(embedding))
        except Exception as e:
            logger.warning(f"Error caching embedding: {e}")
    
    def get_summary(self, content: str) -> Optional[str]:
        """Get cached summary"""
        if not self.cache_enabled:
            return None
        
        try:
            key = self._get_cache_key(content, "summary")
            return self.redis_client.get(key)
        except Exception as e:
            logger.warning(f"Error retrieving cached summary: {e}")
        
        return None
    
    def set_summary(self, content: str, summary: str, ttl: int = 604800):
        """Cache summary with TTL (default 7 days)"""
        if not self.cache_enabled:
            return
        
        try:
            key = self._get_cache_key(content, "summary")
            self.redis_client.setex(key, ttl, summary)
        except Exception as e:
            logger.warning(f"Error caching summary: {e}")

# Global cache instance
embedding_cache = EmbeddingCache()
