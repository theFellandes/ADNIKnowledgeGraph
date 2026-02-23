"""
Redis Cache Manager for ADNI Knowledge Graph
Provides intelligent caching for images, metadata, and search results with performance monitoring
"""

import redis
import json
import pickle
import logging
import hashlib
import time
import threading
import psutil
import statistics
from typing import Any, Optional, Dict, List, Union, Tuple, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from pathlib import Path
from collections import deque, defaultdict
import os

logger = logging.getLogger(__name__)


@dataclass
class CacheStats:
    """Enhanced cache performance statistics with monitoring"""
    hits: int = 0
    misses: int = 0
    sets: int = 0
    evictions: int = 0
    memory_usage: int = 0
    hit_rate: float = 0.0
    
    # Enhanced monitoring fields
    response_times: deque = field(default_factory=lambda: deque(maxlen=1000))
    memory_history: deque = field(default_factory=lambda: deque(maxlen=100))
    hit_rate_history: deque = field(default_factory=lambda: deque(maxlen=100))
    key_access_patterns: Dict[str, int] = field(default_factory=dict)
    operation_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    error_counts: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    # Performance thresholds
    memory_warning_threshold: float = 0.8  # 80% of max memory
    memory_critical_threshold: float = 0.95  # 95% of max memory
    hit_rate_warning_threshold: float = 70.0  # 70% hit rate
    response_time_warning_threshold: float = 0.1  # 100ms
    
    def update_hit_rate(self):
        """Update hit rate calculation and history"""
        total = self.hits + self.misses
        self.hit_rate = (self.hits / total * 100) if total > 0 else 0.0
        self.hit_rate_history.append((datetime.utcnow(), self.hit_rate))
    
    def add_response_time(self, response_time: float):
        """Add response time measurement"""
        self.response_times.append((datetime.utcnow(), response_time))
    
    def add_memory_usage(self, memory_bytes: int):
        """Add memory usage measurement"""
        self.memory_usage = memory_bytes
        self.memory_history.append((datetime.utcnow(), memory_bytes))
    
    def get_avg_response_time(self, minutes: int = 5) -> float:
        """Get average response time for last N minutes"""
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        recent_times = [rt for ts, rt in self.response_times if ts > cutoff]
        return statistics.mean(recent_times) if recent_times else 0.0
    
    def get_memory_trend(self, minutes: int = 10) -> str:
        """Get memory usage trend (increasing/decreasing/stable)"""
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        recent_memory = [mem for ts, mem in self.memory_history if ts > cutoff]
        
        if len(recent_memory) < 2:
            return "insufficient_data"
        
        # Calculate trend using linear regression slope
        x_vals = list(range(len(recent_memory)))
        y_vals = recent_memory
        
        n = len(recent_memory)
        sum_x = sum(x_vals)
        sum_y = sum(y_vals)
        sum_xy = sum(x * y for x, y in zip(x_vals, y_vals))
        sum_x2 = sum(x * x for x in x_vals)
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
        
        if slope > 1000000:  # 1MB increase per measurement
            return "increasing"
        elif slope < -1000000:  # 1MB decrease per measurement
            return "decreasing"
        else:
            return "stable"


@dataclass
class CacheConfig:
    """Enhanced cache configuration settings with monitoring options"""
    max_memory: int = 2 * 1024 * 1024 * 1024  # 2GB default
    default_ttl: int = 24 * 3600  # 24 hours
    thumbnail_ttl: int = 7 * 24 * 3600  # 1 week
    search_ttl: int = 3600  # 1 hour
    patient_ttl: int = 24 * 3600  # 24 hours
    biomarker_ttl: int = 12 * 3600  # 12 hours
    family_ttl: int = 24 * 3600  # 24 hours
    eviction_policy: str = "allkeys-lru"
    enable_monitoring: bool = True
    
    # Enhanced monitoring configuration
    monitoring_interval: int = 60  # seconds between monitoring updates
    performance_log_interval: int = 300  # seconds between performance logs
    alert_callback: Optional[Callable] = None  # callback for alerts
    enable_auto_optimization: bool = True
    optimization_interval: int = 3600  # seconds between optimization runs
    
    # Performance thresholds for alerting
    memory_warning_threshold: float = 0.8
    memory_critical_threshold: float = 0.95
    hit_rate_warning_threshold: float = 70.0
    response_time_warning_threshold: float = 0.1
    
    # Auto-optimization settings
    auto_adjust_ttl: bool = True
    min_ttl_adjustment: float = 0.5  # minimum TTL multiplier
    max_ttl_adjustment: float = 2.0  # maximum TTL multiplier


class EnhancedCacheManager:
    """
    Enhanced Redis cache manager with intelligent caching, performance monitoring,
    and LRU eviction for ADNI Knowledge Graph
    """

    def __init__(self, host: str = 'localhost', port: int = 6379,
                 db: int = 0, password: Optional[str] = None,
                 config: Optional[CacheConfig] = None):
        """
        Initialize Redis connection with enhanced configuration

        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            password: Redis password (if required)
            config: Cache configuration settings
        """
        self.config = config or CacheConfig()
        self.stats = CacheStats()
        self._lock = threading.Lock()
        self._monitoring_enabled = self.config.enable_monitoring
        
        try:
            self.redis_client = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=False,
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

            # Configure Redis for LRU eviction
            self._configure_redis()
            
            # Initialize monitoring
            if self._monitoring_enabled:
                self._start_monitoring()

        except redis.ConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

    def _configure_redis(self):
        """Configure Redis settings for optimal performance"""
        try:
            # Set memory limit and eviction policy
            self.redis_client.config_set('maxmemory', str(self.config.max_memory))
            self.redis_client.config_set('maxmemory-policy', self.config.eviction_policy)
            
            logger.info(f"Redis configured: max_memory={self.config.max_memory}, "
                       f"eviction_policy={self.config.eviction_policy}")
        except Exception as e:
            logger.warning(f"Could not configure Redis settings: {e}")

    def _start_monitoring(self):
        """Start enhanced background monitoring with performance tracking and alerting"""
        def monitor():
            last_performance_log = time.time()
            last_optimization = time.time()
            
            while self._monitoring_enabled:
                try:
                    current_time = time.time()
                    
                    # Update memory and performance stats
                    self._update_memory_stats()
                    self._update_performance_metrics()
                    self._check_alerts()
                    
                    # Log performance metrics periodically
                    if current_time - last_performance_log >= self.config.performance_log_interval:
                        self.log_performance_metrics()
                        last_performance_log = current_time
                    
                    # Run auto-optimization periodically
                    if (self.config.enable_auto_optimization and 
                        current_time - last_optimization >= self.config.optimization_interval):
                        self._auto_optimize_cache()
                        last_optimization = current_time
                    
                    time.sleep(self.config.monitoring_interval)
                    
                except Exception as e:
                    logger.error(f"Enhanced monitoring error: {e}")
                    time.sleep(60)  # Fallback to 1-minute interval on error
                    
        monitor_thread = threading.Thread(target=monitor, daemon=True)
        monitor_thread.start()
        logger.info("Enhanced cache monitoring started")

    def _update_memory_stats(self):
        """Update comprehensive memory usage statistics"""
        try:
            info = self.redis_client.info('memory')
            memory_used = info.get('used_memory', 0)
            
            with self._lock:
                self.stats.add_memory_usage(memory_used)
                self.stats.update_hit_rate()
                
                # Update eviction count from Redis stats
                redis_stats = self.redis_client.info('stats')
                self.stats.evictions = redis_stats.get('evicted_keys', 0)
                
        except Exception as e:
            logger.error(f"Failed to update memory stats: {e}")
            with self._lock:
                self.stats.error_counts['memory_update'] += 1
    
    def _update_performance_metrics(self):
        """Update performance metrics and access patterns"""
        try:
            # Get Redis performance stats
            redis_info = self.redis_client.info()
            
            with self._lock:
                # Update operation counts from Redis
                self.stats.operation_counts['total_commands'] = redis_info.get('total_commands_processed', 0)
                self.stats.operation_counts['keyspace_hits'] = redis_info.get('keyspace_hits', 0)
                self.stats.operation_counts['keyspace_misses'] = redis_info.get('keyspace_misses', 0)
                
                # Calculate system-level hit rate from Redis
                redis_hits = redis_info.get('keyspace_hits', 0)
                redis_misses = redis_info.get('keyspace_misses', 0)
                total_redis_ops = redis_hits + redis_misses
                
                if total_redis_ops > 0:
                    redis_hit_rate = (redis_hits / total_redis_ops) * 100
                    self.stats.hit_rate_history.append((datetime.utcnow(), redis_hit_rate))
                
        except Exception as e:
            logger.error(f"Failed to update performance metrics: {e}")
            with self._lock:
                self.stats.error_counts['performance_update'] += 1
    
    def _check_alerts(self):
        """Check performance thresholds and trigger alerts"""
        try:
            memory_ratio = self.stats.memory_usage / self.config.max_memory
            avg_response_time = self.stats.get_avg_response_time()
            
            alerts = []
            
            # Memory usage alerts
            if memory_ratio >= self.config.memory_critical_threshold:
                alerts.append({
                    'type': 'CRITICAL',
                    'category': 'memory',
                    'message': f'Cache memory usage critical: {memory_ratio:.1%} of max capacity',
                    'value': memory_ratio,
                    'threshold': self.config.memory_critical_threshold
                })
            elif memory_ratio >= self.config.memory_warning_threshold:
                alerts.append({
                    'type': 'WARNING',
                    'category': 'memory',
                    'message': f'Cache memory usage high: {memory_ratio:.1%} of max capacity',
                    'value': memory_ratio,
                    'threshold': self.config.memory_warning_threshold
                })
            
            # Hit rate alerts
            if self.stats.hit_rate < self.config.hit_rate_warning_threshold:
                alerts.append({
                    'type': 'WARNING',
                    'category': 'hit_rate',
                    'message': f'Cache hit rate low: {self.stats.hit_rate:.1f}%',
                    'value': self.stats.hit_rate,
                    'threshold': self.config.hit_rate_warning_threshold
                })
            
            # Response time alerts
            if avg_response_time > self.config.response_time_warning_threshold:
                alerts.append({
                    'type': 'WARNING',
                    'category': 'response_time',
                    'message': f'Average response time high: {avg_response_time:.3f}s',
                    'value': avg_response_time,
                    'threshold': self.config.response_time_warning_threshold
                })
            
            # Process alerts
            for alert in alerts:
                self._handle_alert(alert)
                
        except Exception as e:
            logger.error(f"Failed to check alerts: {e}")
            with self._lock:
                self.stats.error_counts['alert_check'] += 1
    
    def _handle_alert(self, alert: Dict[str, Any]):
        """Handle performance alerts"""
        # Log the alert
        log_level = logging.CRITICAL if alert['type'] == 'CRITICAL' else logging.WARNING
        logger.log(log_level, f"Cache Alert [{alert['type']}]: {alert['message']}")
        
        # Call custom alert callback if configured
        if self.config.alert_callback:
            try:
                self.config.alert_callback(alert)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")
        
        # Store alert in stats for dashboard
        with self._lock:
            if 'alerts' not in self.stats.operation_counts:
                self.stats.operation_counts['alerts'] = []
            self.stats.operation_counts['alerts'].append({
                'timestamp': datetime.utcnow().isoformat(),
                'alert': alert
            })
            
            # Keep only last 50 alerts
            if len(self.stats.operation_counts['alerts']) > 50:
                self.stats.operation_counts['alerts'] = self.stats.operation_counts['alerts'][-50:]
    
    def _auto_optimize_cache(self):
        """Automatically optimize cache performance based on usage patterns"""
        try:
            logger.info("Running automatic cache optimization...")
            
            optimizations = []
            
            # Analyze key access patterns
            key_distribution = self.get_key_distribution()
            total_keys = sum(key_distribution.values())
            
            if total_keys == 0:
                logger.info("No keys in cache, skipping optimization")
                return
            
            # Memory-based optimizations
            memory_ratio = self.stats.memory_usage / self.config.max_memory
            
            if memory_ratio > 0.9:  # High memory usage
                # Reduce TTL for less frequently accessed data
                self._optimize_ttl_for_memory_pressure()
                optimizations.append("Reduced TTL for memory pressure")
            
            # Hit rate optimizations
            if self.stats.hit_rate < 60:  # Low hit rate
                # Increase TTL for frequently accessed data
                self._optimize_ttl_for_hit_rate()
                optimizations.append("Increased TTL for better hit rate")
            
            # Clean up expired keys manually (Redis does this automatically, but helps with memory)
            expired_cleaned = self.cleanup_expired_searches()
            if expired_cleaned > 0:
                optimizations.append(f"Cleaned {expired_cleaned} expired search results")
            
            # Log optimization results
            if optimizations:
                logger.info(f"Cache optimizations applied: {', '.join(optimizations)}")
            else:
                logger.info("No optimizations needed")
                
        except Exception as e:
            logger.error(f"Auto-optimization failed: {e}")
            with self._lock:
                self.stats.error_counts['auto_optimization'] += 1
    
    def _optimize_ttl_for_memory_pressure(self):
        """Reduce TTL for keys when memory pressure is high"""
        try:
            # Get sample of keys and their TTL
            search_keys = self.redis_client.keys("search:*")
            
            # Reduce TTL for search results by 50%
            pipe = self.redis_client.pipeline()
            updated_count = 0
            
            for key in search_keys[:100]:  # Limit to avoid performance impact
                current_ttl = self.redis_client.ttl(key)
                if current_ttl > 300:  # Only reduce if TTL > 5 minutes
                    new_ttl = max(300, int(current_ttl * 0.5))
                    pipe.expire(key, new_ttl)
                    updated_count += 1
            
            if updated_count > 0:
                pipe.execute()
                logger.info(f"Reduced TTL for {updated_count} search results due to memory pressure")
                
        except Exception as e:
            logger.error(f"TTL optimization for memory pressure failed: {e}")
    
    def _optimize_ttl_for_hit_rate(self):
        """Increase TTL for frequently accessed keys to improve hit rate"""
        try:
            # This is a simplified implementation
            # In a real system, you'd track access frequency per key
            
            # Increase TTL for patient and biomarker data (frequently accessed)
            patient_keys = self.redis_client.keys("patient:*")
            biomarker_keys = self.redis_client.keys("biomarker:*")
            
            pipe = self.redis_client.pipeline()
            updated_count = 0
            
            for key in (list(patient_keys) + list(biomarker_keys))[:50]:
                current_ttl = self.redis_client.ttl(key)
                if 0 < current_ttl < 86400:  # If TTL is between 0 and 24 hours
                    new_ttl = min(86400, int(current_ttl * 1.5))  # Increase by 50%, max 24h
                    pipe.expire(key, new_ttl)
                    updated_count += 1
            
            if updated_count > 0:
                pipe.execute()
                logger.info(f"Increased TTL for {updated_count} frequently accessed keys")
                
        except Exception as e:
            logger.error(f"TTL optimization for hit rate failed: {e}")

    def set(self, key: str, value: Any, expire: Optional[int] = None,
            use_json: bool = True, compress: bool = False) -> bool:
        """
        Set a value in cache with enhanced options and performance monitoring

        Args:
            key: Cache key
            value: Value to cache
            expire: Expiration time in seconds
            use_json: Use JSON serialization (faster) vs pickle (more flexible)
            compress: Compress large values

        Returns:
            Success status
        """
        start_time = time.time()
        
        try:
            # Serialize value
            if use_json:
                serialized = json.dumps(value, default=str).encode('utf-8')
            else:
                serialized = pickle.dumps(value)

            # Compress if requested and data is large
            if compress and len(serialized) > 1024:  # Compress if > 1KB
                import gzip
                serialized = gzip.compress(serialized)
                key = f"compressed:{key}"

            # Set in Redis
            if expire:
                result = self.redis_client.setex(key, expire, serialized)
            else:
                result = self.redis_client.set(key, serialized)

            # Update performance metrics
            response_time = time.time() - start_time
            with self._lock:
                self.stats.sets += 1
                self.stats.add_response_time(response_time)
                self.stats.operation_counts['set'] += 1
                
                # Track key access patterns
                key_prefix = key.split(':')[0] if ':' in key else 'other'
                self.stats.key_access_patterns[key_prefix] = self.stats.key_access_patterns.get(key_prefix, 0) + 1
            
            return bool(result)

        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            with self._lock:
                self.stats.error_counts['set'] += 1
            return False

    def get(self, key: str, use_json: bool = True) -> Optional[Any]:
        """
        Get a value from cache with decompression support and performance monitoring

        Args:
            key: Cache key
            use_json: Use JSON deserialization vs pickle

        Returns:
            Cached value or None
        """
        start_time = time.time()
        
        try:
            # Try compressed version first
            compressed_key = f"compressed:{key}"
            value = self.redis_client.get(compressed_key)
            is_compressed = value is not None
            
            if value is None:
                value = self.redis_client.get(key)

            response_time = time.time() - start_time

            if value is None:
                with self._lock:
                    self.stats.misses += 1
                    self.stats.add_response_time(response_time)
                    self.stats.operation_counts['get_miss'] += 1
                return None

            # Decompress if needed
            if is_compressed:
                import gzip
                value = gzip.decompress(value)

            # Deserialize
            if use_json:
                result = json.loads(value.decode('utf-8'))
            else:
                result = pickle.loads(value)

            with self._lock:
                self.stats.hits += 1
                self.stats.add_response_time(response_time)
                self.stats.operation_counts['get_hit'] += 1
                
                # Track key access patterns
                key_prefix = key.split(':')[0] if ':' in key else 'other'
                self.stats.key_access_patterns[key_prefix] = self.stats.key_access_patterns.get(key_prefix, 0) + 1
            
            return result

        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            with self._lock:
                self.stats.misses += 1
                self.stats.error_counts['get'] += 1
            return None

    # ==================== IMAGE CACHING METHODS ====================
    
    def cache_thumbnail(self, image_hash: str, thumbnail_data: bytes) -> bool:
        """
        Cache thumbnail binary data with optimized storage
        
        Args:
            image_hash: Unique image identifier
            thumbnail_data: Binary thumbnail data
            
        Returns:
            Success status
        """
        key = f"image:{image_hash}:thumbnail"
        try:
            result = self.redis_client.setex(
                key, 
                self.config.thumbnail_ttl, 
                thumbnail_data
            )
            with self._lock:
                self.stats.sets += 1
            return bool(result)
        except Exception as e:
            logger.error(f"Failed to cache thumbnail for {image_hash}: {e}")
            return False

    def get_thumbnail(self, image_hash: str) -> Optional[bytes]:
        """
        Retrieve cached thumbnail data
        
        Args:
            image_hash: Unique image identifier
            
        Returns:
            Binary thumbnail data or None
        """
        key = f"image:{image_hash}:thumbnail"
        try:
            data = self.redis_client.get(key)
            if data is None:
                with self._lock:
                    self.stats.misses += 1
                return None
            
            with self._lock:
                self.stats.hits += 1
            return data
        except Exception as e:
            logger.error(f"Failed to get thumbnail for {image_hash}: {e}")
            with self._lock:
                self.stats.misses += 1
            return None

    def cache_image_metadata(self, image_hash: str, metadata: Dict[str, Any]) -> bool:
        """
        Cache comprehensive image metadata with JSON serialization
        
        Args:
            image_hash: Unique image identifier
            metadata: Complete image metadata including DICOM fields
            
        Returns:
            Success status
        """
        key = f"image:{image_hash}:metadata"
        return self.set(key, metadata, expire=self.config.default_ttl, compress=True)

    def get_image_metadata(self, image_hash: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached image metadata
        
        Args:
            image_hash: Unique image identifier
            
        Returns:
            Metadata dictionary or None
        """
        key = f"image:{image_hash}:metadata"
        return self.get(key)

    def cache_image_paths(self, image_hash: str, file_paths: Dict[str, str]) -> bool:
        """
        Cache all file paths for an image (DICOM, PNG, thumbnail)
        
        Args:
            image_hash: Unique image identifier
            file_paths: Dictionary with keys: dicom, png, thumbnail
            
        Returns:
            Success status
        """
        key = f"image:{image_hash}:paths"
        return self.set(key, file_paths, expire=self.config.thumbnail_ttl)

    def get_image_paths(self, image_hash: str) -> Optional[Dict[str, str]]:
        """
        Get all cached file paths for an image
        
        Args:
            image_hash: Unique image identifier
            
        Returns:
            File paths dictionary or None
        """
        key = f"image:{image_hash}:paths"
        return self.get(key)

    def warm_image_cache(self, patient_ids: List[str], image_processor=None) -> int:
        """
        Warm cache with frequently accessed patient images
        
        Args:
            patient_ids: List of patient IDs to preload
            image_processor: Optional image processor for thumbnail generation
            
        Returns:
            Number of images cached
        """
        cached_count = 0
        logger.info(f"Starting cache warming for {len(patient_ids)} patients")
        
        for patient_id in patient_ids:
            try:
                # This would typically query the database for patient images
                # For now, we'll implement a placeholder
                patient_images = self._get_patient_images(patient_id)
                
                for image_info in patient_images:
                    image_hash = image_info.get('image_hash')
                    if image_hash and not self.get_thumbnail(image_hash):
                        # Generate and cache thumbnail if not exists
                        if image_processor and 'thumbnail_path' in image_info:
                            try:
                                with open(image_info['thumbnail_path'], 'rb') as f:
                                    thumbnail_data = f.read()
                                if self.cache_thumbnail(image_hash, thumbnail_data):
                                    cached_count += 1
                            except Exception as e:
                                logger.warning(f"Failed to cache thumbnail for {image_hash}: {e}")
                                
            except Exception as e:
                logger.error(f"Cache warming failed for patient {patient_id}: {e}")
                
        logger.info(f"Cache warming completed: {cached_count} images cached")
        return cached_count

    def _get_patient_images(self, patient_id: str) -> List[Dict[str, Any]]:
        """
        Placeholder method to get patient images from database
        This should be implemented to query Neo4j or other data source
        
        Args:
            patient_id: Patient identifier
            
        Returns:
            List of image information dictionaries
        """
        # Placeholder implementation
        return []

    def close(self) -> None:
        """Close Redis connection and stop monitoring"""
        try:
            self._monitoring_enabled = False
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


    # ==================== PATIENT DATA CACHING METHODS ====================
    
    def cache_patient_summary(self, patient_id: str, summary: Dict[str, Any]) -> bool:
        """
        Cache comprehensive patient summary with demographics and clinical data
        
        Args:
            patient_id: Patient identifier
            summary: Complete patient summary including demographics, diagnoses, etc.
            
        Returns:
            Success status
        """
        key = f"patient:{patient_id}:summary"
        return self.set(key, summary, expire=self.config.patient_ttl, compress=True)

    def get_patient_summary(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached patient summary
        
        Args:
            patient_id: Patient identifier
            
        Returns:
            Patient summary dictionary or None
        """
        key = f"patient:{patient_id}:summary"
        return self.get(key)

    def cache_biomarker_timeline(self, patient_id: str, biomarkers: List[Dict[str, Any]]) -> bool:
        """
        Cache patient biomarker timeline for quick access
        
        Args:
            patient_id: Patient identifier
            biomarkers: List of biomarker measurements with timestamps
            
        Returns:
            Success status
        """
        key = f"biomarker:{patient_id}:timeline"
        return self.set(key, biomarkers, expire=self.config.biomarker_ttl, compress=True)

    def get_biomarker_timeline(self, patient_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieve cached biomarker timeline
        
        Args:
            patient_id: Patient identifier
            
        Returns:
            List of biomarker measurements or None
        """
        key = f"biomarker:{patient_id}:timeline"
        return self.get(key)

    def cache_latest_biomarkers(self, patient_id: str, latest_values: Dict[str, Any]) -> bool:
        """
        Cache latest biomarker values for quick access
        
        Args:
            patient_id: Patient identifier
            latest_values: Dictionary of latest biomarker values
            
        Returns:
            Success status
        """
        key = f"biomarker:{patient_id}:latest"
        return self.set(key, latest_values, expire=self.config.biomarker_ttl)

    def get_latest_biomarkers(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached latest biomarker values
        
        Args:
            patient_id: Patient identifier
            
        Returns:
            Latest biomarker values or None
        """
        key = f"biomarker:{patient_id}:latest"
        return self.get(key)

    def cache_family_tree(self, patient_id: str, family_data: Dict[str, Any]) -> bool:
        """
        Cache family relationship tree for relationship queries
        
        Args:
            patient_id: Patient identifier
            family_data: Complete family tree with relationships and AD status
            
        Returns:
            Success status
        """
        key = f"family:{patient_id}:tree"
        return self.set(key, family_data, expire=self.config.family_ttl, compress=True)

    def get_family_tree(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached family relationship tree
        
        Args:
            patient_id: Patient identifier
            
        Returns:
            Family tree data or None
        """
        key = f"family:{patient_id}:tree"
        return self.get(key)

    def invalidate_patient_cache(self, patient_id: str) -> int:
        """
        Invalidate all cached data for a patient when data is updated
        
        Args:
            patient_id: Patient identifier
            
        Returns:
            Number of keys deleted
        """
        patterns = [
            f"patient:{patient_id}:*",
            f"biomarker:{patient_id}:*",
            f"family:{patient_id}:*"
        ]
        
        deleted_count = 0
        for pattern in patterns:
            try:
                keys = self.redis_client.keys(pattern)
                if keys:
                    deleted_count += self.redis_client.delete(*keys)
            except Exception as e:
                logger.error(f"Failed to invalidate cache pattern {pattern}: {e}")
                
        logger.info(f"Invalidated {deleted_count} cache entries for patient {patient_id}")
        return deleted_count

    def batch_cache_patients(self, patient_data: Dict[str, Dict[str, Any]]) -> int:
        """
        Efficiently cache multiple patients using pipeline
        
        Args:
            patient_data: Dictionary mapping patient_id to patient summary data
            
        Returns:
            Number of patients successfully cached
        """
        pipe = self.redis_client.pipeline()
        cached_count = 0
        
        try:
            for patient_id, data in patient_data.items():
                key = f"patient:{patient_id}:summary"
                serialized = json.dumps(data, default=str).encode('utf-8')
                pipe.setex(key, self.config.patient_ttl, serialized)
                cached_count += 1
                
            pipe.execute()
            
            with self._lock:
                self.stats.sets += cached_count
                
            logger.info(f"Batch cached {cached_count} patients")
            return cached_count
            
        except Exception as e:
            logger.error(f"Batch caching failed: {e}")
            return 0   
 # ==================== SEARCH RESULT CACHING METHODS ====================
    
    def _generate_query_hash(self, query: Union[str, Dict[str, Any]]) -> str:
        """
        Generate consistent hash for search queries
        
        Args:
            query: Search query string or dictionary
            
        Returns:
            SHA256 hash of the query
        """
        if isinstance(query, dict):
            # Sort dictionary for consistent hashing
            query_str = json.dumps(query, sort_keys=True, default=str)
        else:
            query_str = str(query)
            
        return hashlib.sha256(query_str.encode('utf-8')).hexdigest()[:16]

    def cache_search_results(self, query: Union[str, Dict[str, Any]], 
                           results: Dict[str, Any], 
                           ttl: Optional[int] = None) -> bool:
        """
        Cache search query results with hash-based keys
        
        Args:
            query: Original search query
            results: Search results to cache
            ttl: Time to live in seconds (defaults to search_ttl)
            
        Returns:
            Success status
        """
        query_hash = self._generate_query_hash(query)
        key = f"search:{query_hash}"
        
        # Add metadata to cached results
        cached_data = {
            'query': query,
            'results': results,
            'cached_at': datetime.utcnow().isoformat(),
            'result_count': len(results.get('items', []))
        }
        
        expire_time = ttl or self.config.search_ttl
        return self.set(key, cached_data, expire=expire_time, compress=True)

    def get_search_results(self, query: Union[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached search results
        
        Args:
            query: Search query to look up
            
        Returns:
            Cached search results or None
        """
        query_hash = self._generate_query_hash(query)
        key = f"search:{query_hash}"
        
        cached_data = self.get(key)
        if cached_data:
            # Return just the results, not the metadata
            return cached_data.get('results')
        return None

    def cache_common_searches(self, common_queries: List[Tuple[Union[str, Dict], Dict]]) -> int:
        """
        Preload cache with common search patterns
        
        Args:
            common_queries: List of (query, results) tuples
            
        Returns:
            Number of queries successfully cached
        """
        cached_count = 0
        logger.info(f"Preloading {len(common_queries)} common search patterns")
        
        for query, results in common_queries:
            try:
                if self.cache_search_results(query, results):
                    cached_count += 1
            except Exception as e:
                logger.error(f"Failed to cache common search: {e}")
                
        logger.info(f"Preloaded {cached_count} search patterns")
        return cached_count

    def get_search_cache_stats(self) -> Dict[str, Any]:
        """
        Get statistics about search cache usage
        
        Returns:
            Dictionary with search cache statistics
        """
        try:
            search_keys = self.redis_client.keys("search:*")
            total_searches = len(search_keys)
            
            # Sample some keys to get average size
            sample_size = min(10, total_searches)
            total_size = 0
            
            if sample_size > 0:
                sample_keys = search_keys[:sample_size]
                for key in sample_keys:
                    try:
                        size = self.redis_client.memory_usage(key)
                        if size:
                            total_size += size
                    except:
                        pass
                        
                avg_size = total_size / sample_size if sample_size > 0 else 0
            else:
                avg_size = 0
                
            return {
                'total_cached_searches': total_searches,
                'estimated_total_size': avg_size * total_searches,
                'average_result_size': avg_size
            }
            
        except Exception as e:
            logger.error(f"Failed to get search cache stats: {e}")
            return {'error': str(e)}

    def cleanup_expired_searches(self) -> int:
        """
        Manually cleanup expired search results (Redis handles this automatically,
        but this can be used for maintenance)
        
        Returns:
            Number of expired entries cleaned up
        """
        try:
            search_keys = self.redis_client.keys("search:*")
            expired_count = 0
            
            for key in search_keys:
                ttl = self.redis_client.ttl(key)
                if ttl == -2:  # Key doesn't exist (expired)
                    expired_count += 1
                elif ttl == -1:  # Key exists but has no expiration
                    # Set expiration for keys without TTL
                    self.redis_client.expire(key, self.config.search_ttl)
                    
            return expired_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired searches: {e}")
            return 0   
 # ==================== PERFORMANCE MONITORING METHODS ====================
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive cache performance statistics
        
        Returns:
            Dictionary with cache performance metrics
        """
        with self._lock:
            stats_dict = asdict(self.stats)
            
        try:
            # Get Redis info
            redis_info = self.redis_client.info()
            memory_info = self.redis_client.info('memory')
            
            # Calculate additional metrics
            total_requests = self.stats.hits + self.stats.misses
            hit_rate = (self.stats.hits / total_requests * 100) if total_requests > 0 else 0
            
            stats_dict.update({
                'hit_rate_percent': round(hit_rate, 2),
                'total_requests': total_requests,
                'redis_memory_used': memory_info.get('used_memory', 0),
                'redis_memory_human': memory_info.get('used_memory_human', '0B'),
                'redis_memory_peak': memory_info.get('used_memory_peak', 0),
                'redis_connected_clients': redis_info.get('connected_clients', 0),
                'redis_total_commands': redis_info.get('total_commands_processed', 0),
                'redis_keyspace_hits': redis_info.get('keyspace_hits', 0),
                'redis_keyspace_misses': redis_info.get('keyspace_misses', 0),
                'cache_efficiency': self._calculate_cache_efficiency()
            })
            
        except Exception as e:
            logger.error(f"Failed to get Redis stats: {e}")
            stats_dict['redis_error'] = str(e)
            
        return stats_dict

    def _calculate_cache_efficiency(self) -> float:
        """
        Calculate cache efficiency score based on hit rate and memory usage
        
        Returns:
            Efficiency score between 0 and 100
        """
        try:
            memory_info = self.redis_client.info('memory')
            used_memory = memory_info.get('used_memory', 0)
            max_memory = self.config.max_memory
            
            memory_efficiency = max(0, 100 - (used_memory / max_memory * 100))
            hit_rate_efficiency = self.stats.hit_rate
            
            # Weighted average: 70% hit rate, 30% memory efficiency
            efficiency = (hit_rate_efficiency * 0.7) + (memory_efficiency * 0.3)
            return round(efficiency, 2)
            
        except Exception:
            return 0.0

    def log_performance_metrics(self) -> None:
        """
        Log current performance metrics for monitoring
        """
        stats = self.get_cache_stats()
        
        logger.info(f"Cache Performance Metrics:")
        logger.info(f"  Hit Rate: {stats.get('hit_rate_percent', 0)}%")
        logger.info(f"  Total Requests: {stats.get('total_requests', 0)}")
        logger.info(f"  Memory Used: {stats.get('redis_memory_human', '0B')}")
        logger.info(f"  Cache Efficiency: {stats.get('cache_efficiency', 0)}%")
        logger.info(f"  Connected Clients: {stats.get('redis_connected_clients', 0)}")

    def get_key_distribution(self) -> Dict[str, int]:
        """
        Analyze distribution of cached keys by type
        
        Returns:
            Dictionary with key type counts
        """
        try:
            all_keys = self.redis_client.keys("*")
            distribution = {
                'patient': 0,
                'image': 0,
                'biomarker': 0,
                'family': 0,
                'search': 0,
                'other': 0
            }
            
            for key in all_keys:
                key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)
                
                if key_str.startswith('patient:'):
                    distribution['patient'] += 1
                elif key_str.startswith('image:'):
                    distribution['image'] += 1
                elif key_str.startswith('biomarker:'):
                    distribution['biomarker'] += 1
                elif key_str.startswith('family:'):
                    distribution['family'] += 1
                elif key_str.startswith('search:'):
                    distribution['search'] += 1
                else:
                    distribution['other'] += 1
                    
            return distribution
            
        except Exception as e:
            logger.error(f"Failed to get key distribution: {e}")
            return {}

    # ==================== ENHANCED PERFORMANCE MONITORING METHODS ====================
    
    def get_performance_dashboard_data(self) -> Dict[str, Any]:
        """
        Generate comprehensive performance data for dashboard visualization
        
        Returns:
            Dictionary with all performance metrics formatted for dashboard display
        """
        try:
            with self._lock:
                stats_snapshot = asdict(self.stats)
            
            # Get Redis system info
            redis_info = self.redis_client.info()
            memory_info = self.redis_client.info('memory')
            
            # Calculate derived metrics
            total_requests = self.stats.hits + self.stats.misses
            hit_rate = (self.stats.hits / total_requests * 100) if total_requests > 0 else 0
            memory_ratio = self.stats.memory_usage / self.config.max_memory
            
            # Prepare time series data for charts
            hit_rate_series = [
                {'timestamp': ts.isoformat(), 'value': rate}
                for ts, rate in list(self.stats.hit_rate_history)[-50:]  # Last 50 measurements
            ]
            
            memory_series = [
                {'timestamp': ts.isoformat(), 'value': mem}
                for ts, mem in list(self.stats.memory_history)[-50:]  # Last 50 measurements
            ]
            
            response_time_series = [
                {'timestamp': ts.isoformat(), 'value': rt * 1000}  # Convert to milliseconds
                for ts, rt in list(self.stats.response_times)[-100:]  # Last 100 measurements
            ]
            
            # Get recent alerts
            recent_alerts = []
            if 'alerts' in self.stats.operation_counts:
                recent_alerts = self.stats.operation_counts['alerts'][-10:]  # Last 10 alerts
            
            dashboard_data = {
                # Current metrics
                'current_metrics': {
                    'hit_rate': round(hit_rate, 2),
                    'total_requests': total_requests,
                    'memory_usage_bytes': self.stats.memory_usage,
                    'memory_usage_mb': round(self.stats.memory_usage / (1024 * 1024), 2),
                    'memory_usage_percent': round(memory_ratio * 100, 2),
                    'avg_response_time_ms': round(self.stats.get_avg_response_time() * 1000, 2),
                    'cache_efficiency': self._calculate_cache_efficiency(),
                    'connected_clients': redis_info.get('connected_clients', 0),
                    'total_keys': len(self.redis_client.keys("*")),
                    'evicted_keys': self.stats.evictions
                },
                
                # Time series data for charts
                'time_series': {
                    'hit_rate': hit_rate_series,
                    'memory_usage': memory_series,
                    'response_times': response_time_series
                },
                
                # Key distribution and access patterns
                'key_patterns': {
                    'distribution': self.get_key_distribution(),
                    'access_patterns': dict(self.stats.key_access_patterns),
                    'top_accessed_prefixes': sorted(
                        self.stats.key_access_patterns.items(),
                        key=lambda x: x[1],
                        reverse=True
                    )[:10]
                },
                
                # Operation statistics
                'operations': {
                    'hits': self.stats.hits,
                    'misses': self.stats.misses,
                    'sets': self.stats.sets,
                    'evictions': self.stats.evictions,
                    'operation_counts': dict(self.stats.operation_counts),
                    'error_counts': dict(self.stats.error_counts)
                },
                
                # Performance trends
                'trends': {
                    'memory_trend': self.stats.get_memory_trend(),
                    'hit_rate_trend': self._get_hit_rate_trend(),
                    'response_time_trend': self._get_response_time_trend()
                },
                
                # Health indicators
                'health': {
                    'status': self._get_overall_health_status(),
                    'alerts': recent_alerts,
                    'recommendations': self._get_performance_recommendations()
                },
                
                # Configuration info
                'config': {
                    'max_memory_mb': round(self.config.max_memory / (1024 * 1024), 2),
                    'eviction_policy': self.config.eviction_policy,
                    'monitoring_enabled': self._monitoring_enabled,
                    'auto_optimization_enabled': self.config.enable_auto_optimization
                },
                
                # Timestamp
                'generated_at': datetime.utcnow().isoformat()
            }
            
            return dashboard_data
            
        except Exception as e:
            logger.error(f"Failed to generate dashboard data: {e}")
            return {'error': str(e), 'generated_at': datetime.utcnow().isoformat()}
    
    def _get_hit_rate_trend(self) -> str:
        """Calculate hit rate trend over recent history"""
        try:
            if len(self.stats.hit_rate_history) < 5:
                return "insufficient_data"
            
            recent_rates = [rate for _, rate in list(self.stats.hit_rate_history)[-10:]]
            
            # Simple trend calculation
            first_half = statistics.mean(recent_rates[:len(recent_rates)//2])
            second_half = statistics.mean(recent_rates[len(recent_rates)//2:])
            
            if second_half > first_half + 5:  # 5% improvement
                return "improving"
            elif second_half < first_half - 5:  # 5% degradation
                return "declining"
            else:
                return "stable"
                
        except Exception:
            return "unknown"
    
    def _get_response_time_trend(self) -> str:
        """Calculate response time trend over recent history"""
        try:
            if len(self.stats.response_times) < 10:
                return "insufficient_data"
            
            recent_times = [rt for _, rt in list(self.stats.response_times)[-20:]]
            
            # Simple trend calculation
            first_half = statistics.mean(recent_times[:len(recent_times)//2])
            second_half = statistics.mean(recent_times[len(recent_times)//2:])
            
            if second_half > first_half * 1.2:  # 20% slower
                return "degrading"
            elif second_half < first_half * 0.8:  # 20% faster
                return "improving"
            else:
                return "stable"
                
        except Exception:
            return "unknown"
    
    def _get_overall_health_status(self) -> str:
        """Calculate overall cache health status"""
        try:
            memory_ratio = self.stats.memory_usage / self.config.max_memory
            avg_response_time = self.stats.get_avg_response_time()
            
            # Critical conditions
            if memory_ratio >= self.config.memory_critical_threshold:
                return "critical"
            
            # Warning conditions
            warning_conditions = [
                memory_ratio >= self.config.memory_warning_threshold,
                self.stats.hit_rate < self.config.hit_rate_warning_threshold,
                avg_response_time > self.config.response_time_warning_threshold
            ]
            
            if any(warning_conditions):
                return "warning"
            
            # Good conditions
            if (self.stats.hit_rate > 80 and 
                memory_ratio < 0.7 and 
                avg_response_time < 0.05):
                return "excellent"
            
            return "good"
            
        except Exception:
            return "unknown"
    
    def _get_performance_recommendations(self) -> List[str]:
        """Generate performance improvement recommendations"""
        recommendations = []
        
        try:
            memory_ratio = self.stats.memory_usage / self.config.max_memory
            avg_response_time = self.stats.get_avg_response_time()
            
            # Memory recommendations
            if memory_ratio > 0.9:
                recommendations.append("Consider increasing max memory limit or reducing TTL values")
            elif memory_ratio > 0.8:
                recommendations.append("Monitor memory usage closely, consider cache cleanup")
            
            # Hit rate recommendations
            if self.stats.hit_rate < 60:
                recommendations.append("Low hit rate detected, consider increasing TTL for frequently accessed data")
            elif self.stats.hit_rate < 80:
                recommendations.append("Hit rate could be improved by optimizing cache keys and TTL values")
            
            # Response time recommendations
            if avg_response_time > 0.1:
                recommendations.append("High response times detected, check Redis server performance")
            
            # Key distribution recommendations
            key_dist = self.get_key_distribution()
            total_keys = sum(key_dist.values())
            
            if total_keys > 100000:
                recommendations.append("Large number of keys detected, consider implementing key expiration policies")
            
            # Error rate recommendations
            total_errors = sum(self.stats.error_counts.values())
            if total_errors > 100:
                recommendations.append("High error rate detected, check Redis connectivity and configuration")
            
            if not recommendations:
                recommendations.append("Cache performance is optimal")
                
        except Exception as e:
            recommendations.append(f"Unable to generate recommendations: {e}")
        
        return recommendations
    
    def export_performance_report(self, filepath: Optional[str] = None) -> str:
        """
        Export comprehensive performance report to JSON file
        
        Args:
            filepath: Optional file path, defaults to timestamped file
            
        Returns:
            Path to exported file
        """
        try:
            if filepath is None:
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                filepath = f"cache_performance_report_{timestamp}.json"
            
            dashboard_data = self.get_performance_dashboard_data()
            
            # Add additional detailed information for report
            report_data = {
                **dashboard_data,
                'detailed_stats': {
                    'redis_info': self.redis_client.info(),
                    'memory_info': self.redis_client.info('memory'),
                    'stats_info': self.redis_client.info('stats'),
                    'config_info': self.redis_client.config_get('*')
                }
            }
            
            with open(filepath, 'w') as f:
                json.dump(report_data, f, indent=2, default=str)
            
            logger.info(f"Performance report exported to {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Failed to export performance report: {e}")
            raise
    
    def reset_performance_stats(self):
        """Reset performance statistics (useful for testing or after maintenance)"""
        with self._lock:
            self.stats.hits = 0
            self.stats.misses = 0
            self.stats.sets = 0
            self.stats.evictions = 0
            self.stats.response_times.clear()
            self.stats.memory_history.clear()
            self.stats.hit_rate_history.clear()
            self.stats.key_access_patterns.clear()
            self.stats.operation_counts.clear()
            self.stats.error_counts.clear()
            
        logger.info("Performance statistics reset")
    
    def get_memory_usage_breakdown(self) -> Dict[str, Any]:
        """
        Get detailed memory usage breakdown by key type
        
        Returns:
            Dictionary with memory usage by key prefix
        """
        try:
            breakdown = {}
            key_dist = self.get_key_distribution()
            
            for key_type, count in key_dist.items():
                if count == 0:
                    continue
                    
                # Sample some keys of this type to estimate memory usage
                pattern = f"{key_type}:*" if key_type != 'other' else "*"
                sample_keys = self.redis_client.keys(pattern)[:min(10, count)]
                
                total_size = 0
                for key in sample_keys:
                    try:
                        size = self.redis_client.memory_usage(key)
                        if size:
                            total_size += size
                    except:
                        pass
                
                avg_size = total_size / len(sample_keys) if sample_keys else 0
                estimated_total = avg_size * count
                
                breakdown[key_type] = {
                    'key_count': count,
                    'avg_size_bytes': round(avg_size, 2),
                    'estimated_total_bytes': round(estimated_total, 2),
                    'estimated_total_mb': round(estimated_total / (1024 * 1024), 2)
                }
            
            return breakdown
            
        except Exception as e:
            logger.error(f"Failed to get memory breakdown: {e}")
            return {}


# Backward compatibility alias
CacheManager = EnhancedCacheManager