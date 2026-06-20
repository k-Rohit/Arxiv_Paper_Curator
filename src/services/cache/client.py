"""Redis-based exact-match cache for RAG queries."""

import hashlib
import json
import logging
from typing import Optional

import redis

from src.config import RedisSettings
from src.schemas.api.ask import AskRequest, AskResponse

logger = logging.getLogger(__name__)


class CacheClient:
    """Redis-based exact-match cache for RAG queries."""

    def __init__(self, redis_client: redis.Redis, settings: RedisSettings) -> None:
        self.redis    = redis_client
        self.settings = settings
        self.ttl_seconds = settings.ttl_hours * 3600

    def _generate_cache_key(self, request: AskRequest) -> str:
        """Generate exact cache key based on request parameters."""
        key_data = {
            "query":      request.query.strip().lower(),
            "top_k":      request.top_k,
            "use_hybrid": request.use_hybrid,
            "categories": sorted(request.categories) if request.categories else [],
        }
        key_string = json.dumps(key_data, sort_keys=True)
        key_hash   = hashlib.sha256(key_string.encode()).hexdigest()[:16]
        return f"exact_cache:{key_hash}"

    async def find_cached_response(self, request: AskRequest) -> Optional[AskResponse]:
        """Return cached response if present, else None."""
        try:
            cache_key       = self._generate_cache_key(request)
            cached_response = self.redis.get(cache_key)

            if not cached_response:
                return None

            try:
                response_data = json.loads(cached_response)
                logger.info(f"Cache HIT  ({cache_key})")
                return AskResponse(**response_data)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to deserialize cached response: {e}")
                return None

        except Exception as e:
            logger.error(f"Error checking cache: {e}")
            return None

    async def store_response(self, request: AskRequest, response: AskResponse) -> bool:
        """Store response for exact query matching."""
        try:
            cache_key = self._generate_cache_key(request)
            success   = self.redis.set(
                cache_key,
                response.model_dump_json(),
                ex=self.ttl_seconds,
            )
            if success:
                logger.info(f"Cache STORE ({cache_key})")
                return True
            logger.warning("Failed to store response in cache")
            return False

        except Exception as e:
            logger.error(f"Error storing in cache: {e}")
            return False
