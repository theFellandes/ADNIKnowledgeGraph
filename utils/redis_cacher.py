"""
Redis Cache Manager for ADNI Knowledge Graph
Provides caching for image metadata and frequently accessed data
"""

import redis
import json
import pickle
import logging
from typing import Any, Optional, Dict, List
from datetime import datetime, timedelta
import hashlib

logger = logging.getLogger(__name__)


class CacheManager:
    """
    Manages Redis caching for medical image metadata and pipeline data
    """

    def __init__(self, host: str = 'localhost', port: int = 6379,
                 db: int = 0, password: Optional[str] = None):
        """
        Initialize Redis connection

        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            password: Redis password (if required)
        """
        try:
            self.redis_client = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=False,  # We'll handle encoding/decoding
                socket_keepalive=True,
                socket_keepalive_options={
                    1: 1,  # TCP_KEEPIDLE
                    2: 3,  # TCP_KEEPINTVL
                    3: 5,  # TCP_KEEPCNT
                }
            )

            # Test connection
            self.redis_client.ping()
            logger.info(f"✅ Connected to Redis at {host}:{port}")

            # Cache statistics
            self.stats = {
                'hits': 0,
                'misses': 0,
                'sets': 0
            }

        except redis.ConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    def set(self, key: str, value: Any, expire: Optional[int] = None,
            use_json: bool = True) -> bool:
        """
        Set a value in cache

        Args:
            key: Cache key
            value: Value to cache
            expire: Expiration time in seconds
            use_json: Use JSON serialization (faster) vs pickle (more flexible)

        Returns:
            Success status
        """
        try:
            # Serialize value
            if use_json:
                serialized = json.dumps(value, default=str).encode('utf-8')
            else:
                serialized = pickle.dumps(value)

            # Set in Redis
            if expire:
                result = self.redis_client.setex(key, expire, serialized)
            else:
                result = self.redis_client.set(key, serialized)

            self.stats['sets'] += 1
            return bool(result)

        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False

    def get(self, key: str, use_json: bool = True) -> Optional[Any]:
        """
        Get a value from cache

        Args:
            key: Cache key
            use_json: Use JSON deserialization vs pickle

        Returns:
            Cached value or None
        """
        try:
            value = self.redis_client.get(key)

            if value is None:
                self.stats['misses'] += 1
                return None

            # Deserialize
            if use_json:
                result = json.loads(value.decode('utf-8'))
            else:
                result = pickle.loads(value)

            self.stats['hits'] += 1
            return result

        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            self.stats['misses'] += 1
            return None

    def cache_image_metadata(self, image_id: str, metadata: Dict[str, Any],
                             expire_hours: int = 24) -> bool:
        """
        Cache image metadata

        Args:
            image_id: Image identifier
            metadata: Image metadata dictionary
            expire_hours: Cache expiration in hours

        Returns:
            Success status
        """
        key = f"image:metadata:{image_id}"
        return self.set(key, metadata, expire=expire_hours * 3600)

    def get_image_metadata(self, image_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached image metadata

        Args:
            image_id: Image identifier

        Returns:
            Metadata dictionary or None
        """
        key = f"image:metadata:{image_id}"
        return self.get(key)

    def cache_image_path(self, image_id: str, resolution: str,
                         path: str, expire_hours: int = 168) -> bool:
        """
        Cache image file path

        Args:
            image_id: Image identifier
            resolution: Resolution type (diagnostic, preview, thumbnail)
            path: File system path
            expire_hours: Cache expiration (default 1 week)

        Returns:
            Success status
        """
        key = f"image:path:{image_id}:{resolution}"
        return self.set(key, path, expire=expire_hours * 3600)

    def get_image_path(self, image_id: str, resolution: str) -> Optional[str]:
        """
        Get cached image path

        Args:
            image_id: Image identifier
            resolution: Resolution type

        Returns:
            File path or None
        """
        key = f"image:path:{image_id}:{resolution}"
        return self.get(key)

    def close(self) -> None:
        """Close Redis connection"""
        try:
            self.redis_client.close()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()