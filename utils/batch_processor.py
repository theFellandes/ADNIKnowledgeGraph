from __future__ import annotations

"""
Optimized batch processing utilities for parallel execution and memory management
Enhanced for ADNI Knowledge Graph Pipeline
"""

import logging
import concurrent.futures
from typing import List, Callable, Any, Dict, Optional, Generator, Tuple
from tqdm import tqdm
import psutil
import gc
import time
import numpy as np
from collections import defaultdict
import threading
from queue import Queue

logger = logging.getLogger(__name__)


class OptimizedBatchProcessor:
    """Enhanced batch processor with improved performance and memory management"""

    def __init__(
        self,
        max_workers: int = 8,
        batch_size: int = 1000,
        memory_threshold: float = 0.8,
        enable_profiling: bool = False,
    ):
        """
        Initialize optimized batch processor

        Args:
            max_workers: Maximum number of parallel workers
            batch_size: Default batch size
            memory_threshold: Memory usage threshold (0-1) for triggering GC
            enable_profiling: Enable performance profiling
        """
        self.max_workers = max_workers
        self.batch_size = batch_size
        self.memory_threshold = memory_threshold
        self.enable_profiling = enable_profiling

        # Performance metrics
        self.metrics: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._lock = threading.Lock()

    def process_parallel(
        self,
        items: List[Any],
        process_func: Callable[[Any], Any],
        desc: str = "Processing",
        show_progress: bool = True,
        chunk_size: Optional[int] = None,
    ) -> List[Any]:
        """
        Optimized parallel processing with better memory management

        Args:
            items: List of items to process
            process_func: Function to apply to each item
            desc: Description for progress bar
            show_progress: Whether to show progress bar
            chunk_size: Size of chunks for batch processing

        Returns:
            List of results
        """
        if not items:
            return []

        # Determine optimal chunk size
        if chunk_size is None:
            chunk_size = max(1, len(items) // (self.max_workers * 4))
            chunk_size = min(chunk_size, 100)  # Cap at 100 for memory efficiency

        results: List[Any] = []
        failed_items: List[Any] = []

        # Split items into chunks for better memory management
        chunks = [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]

        start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_chunk = {
                executor.submit(self._process_chunk, chunk, process_func): chunk for chunk in chunks
            }

            iterator = concurrent.futures.as_completed(future_to_chunk)
            if show_progress:
                iterator = tqdm(iterator, total=len(chunks), desc=desc)

            for future in iterator:
                chunk = future_to_chunk[future]
                try:
                    # 5 minute timeout per chunk
                    chunk_results = future.result(timeout=300)
                    results.extend(chunk_results)
                except Exception as e:
                    logger.error(f"Failed to process chunk: {e}")
                    failed_items.extend(chunk)

                # Periodic memory check
                self._check_memory_aggressive()

        # Record metrics
        if self.enable_profiling:
            elapsed = time.time() - start_time
            self.metrics["parallel_processing"].append(
                {
                    "items": len(items),
                    "duration": elapsed,
                    "rate": len(items) / elapsed if elapsed > 0 else 0,
                    "failed": len(failed_items),
                }
            )

        if failed_items:
            logger.warning(f"Failed to process {len(failed_items)} items")

        return results

    def _process_chunk(self, chunk: List[Any], process_func: Callable[[Any], Any]) -> List[Any]:
        """Process a chunk of items"""
        results: List[Any] = []
        for item in chunk:
            try:
                result = process_func(item)
                if result is not None:
                    results.append(result)
            except Exception as e:
                logger.error(f"Error processing item in chunk: {e}")
        return results

    def process_in_batches(
        self,
        items: List[Any],
        batch_func: Callable[[List[Any]], Any],
        batch_size: Optional[int] = None,
        desc: str = "Processing batches",
    ) -> int:
        """
        Process items in batches (wrapper for adaptive method)

        Args:
            items: List of items to process
            batch_func: Function to process a batch
            batch_size: Size of each batch (uses default if None)
            desc: Description for progress

        Returns:
            Total number of items processed
        """
        return self.process_in_adaptive_batches(
            items, batch_func, batch_size, desc, adaptive=False
        )

    def process_in_adaptive_batches(
        self,
        items: List[Any],
        batch_func: Callable[[List[Any]], Any],
        initial_batch_size: Optional[int] = None,
        desc: str = "Processing batches",
        adaptive: bool = True,
    ) -> int:
        """
        Process items in batches with adaptive batch sizing

        Args:
            items: List of items to process
            batch_func: Function to process a batch
            initial_batch_size: Initial size of each batch
            desc: Description for progress
            adaptive: Whether to adapt batch size based on performance

        Returns:
            Total number of items processed
        """
        if not items:
            return 0

        if initial_batch_size is None:
            initial_batch_size = self.batch_size

        batch_size = max(1, int(initial_batch_size))
        total_processed = 0
        current_index = 0

        # Adaptive batch sizing parameters
        batch_times: List[float] = []
        target_batch_time = 1.0  # Target ~1 second per batch

        pbar = tqdm(total=len(items), desc=desc) if desc else None

        while current_index < len(items):
            # Get current batch
            batch_end = min(current_index + batch_size, len(items))
            batch = items[current_index:batch_end]

            # Process batch with timing
            batch_start = time.time()
            try:
                batch_func(batch)
                processed_now = len(batch)
                total_processed += processed_now

                if pbar:
                    pbar.update(processed_now)

            except Exception as e:
                logger.error(f"Batch processing failed at index {current_index}: {e}")
                # Try smaller batch size on error
                if batch_size > 10:
                    batch_size = batch_size // 2
                    logger.info(f"Reducing batch size to {batch_size} after error")
                    # retry same window with smaller batch size
                    continue
                else:
                    # Re-raise after repeated failures at minimal batch size
                    raise

            batch_time = time.time() - batch_start
            batch_times.append(batch_time)

            # Adaptive batch sizing
            if adaptive and len(batch_times) >= 3:
                avg_time = float(np.mean(batch_times[-3:]))

                if avg_time < target_batch_time * 0.5:
                    # Processing is fast, increase batch size (up to 4× initial)
                    batch_size = min(batch_size * 2, initial_batch_size * 4)
                elif avg_time > target_batch_time * 2:
                    # Processing is slow, decrease batch size (down to floor 10)
                    batch_size = max(batch_size // 2, 10)

            current_index = batch_end

            # Memory check after each batch
            self._check_memory_aggressive()

        if pbar:
            pbar.close()

        return total_processed

    def chunked_reader(self, file_path: str, chunk_size: int = 10000) -> Generator[List[Dict], None, None]:
        """
        Read large CSV file in chunks

        Args:
            file_path: Path to CSV file
            chunk_size: Number of rows per chunk

        Yields:
            List of dictionaries for each chunk
        """
        import pandas as pd  # local import to avoid global dependency at module load

        for chunk_df in pd.read_csv(
            file_path,
            chunksize=chunk_size,
            low_memory=False,
            na_values=["", "NA", "NaN", "NULL", "null"],
        ):
            yield chunk_df.to_dict("records")
            self._check_memory_aggressive()

    def parallel_file_processing(
        self, file_paths: List[str], file_processor: Callable[[str], Any], desc: str = "Processing files"
    ) -> Dict[str, Any]:
        """
        Process multiple files in parallel

        Args:
            file_paths: List of file paths
            file_processor: Function to process each file
            desc: Description for progress

        Returns:
            Dictionary mapping file paths to results
        """
        results: Dict[str, Any] = {}

        with concurrent.futures.ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {executor.submit(file_processor, fp): fp for fp in file_paths}

            for future in tqdm(concurrent.futures.as_completed(future_to_file), total=len(file_paths), desc=desc):
                file_path = future_to_file[future]
                try:
                    result = future.result()
                    results[file_path] = result
                except Exception as e:
                    logger.error(f"Failed to process file {file_path}: {e}")
                    results[file_path] = {"error": str(e)}

        return results

    @staticmethod
    def partition_data(data: List[Any], partitions: int) -> List[List[Any]]:
        """
        Partition data into roughly equal chunks

        Args:
            data: List to partition
            partitions: Number of partitions

        Returns:
            List of partitions
        """
        if partitions <= 0:
            return [data]
        chunk_size = (len(data) + partitions - 1) // partitions
        return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]

    def parallel_dataframe_processing(
        self, df: "pd.DataFrame", process_func: Callable[["pd.DataFrame"], "pd.DataFrame"], desc: str = "Processing DataFrame"
    ) -> "pd.DataFrame":
        """
        Process DataFrame in parallel with optimized chunking

        Args:
            df: DataFrame to process
            process_func: Function to apply to each chunk
            desc: Description for progress

        Returns:
            Processed DataFrame
        """
        import pandas as pd  # local import

        # Determine optimal chunk size based on DataFrame size
        n_rows = len(df)
        if n_rows == 0:
            return pd.DataFrame()

        chunk_size = max(1000, n_rows // (self.max_workers * 4))
        chunk_size = min(chunk_size, 10000)  # Cap for memory

        # Split DataFrame into chunks
        chunks = [df.iloc[i : i + chunk_size] for i in range(0, n_rows, chunk_size)]

        # Process chunks in parallel
        with concurrent.futures.ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(process_func, chunk) for chunk in chunks]

            results: List[pd.DataFrame] = []
            for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc=desc):
                try:
                    result = future.result()
                    if result is not None:
                        results.append(result)
                except Exception as e:
                    logger.error(f"Chunk processing failed: {e}")

        # Combine results
        if results:
            return pd.concat(results, ignore_index=True)
        return pd.DataFrame()

    def streaming_file_processor(
        self,
        file_path: str,
        process_func: Callable[[Any], Any],
        chunk_size: int = 10000,
        file_type: str = "csv",
    ) -> Generator[Any, None, None]:
        """
        Stream process large files with minimal memory footprint

        Args:
            file_path: Path to file
            process_func: Function to process each chunk
            chunk_size: Number of rows per chunk
            file_type: Type of file (csv, json, parquet)

        Yields:
            Processed chunks
        """
        import pandas as pd  # local import

        if file_type == "csv":
            reader = pd.read_csv(
                file_path, chunksize=chunk_size, low_memory=False, na_values=["", "NA", "NaN", "NULL", "null"]
            )
        elif file_type == "json":
            reader = pd.read_json(file_path, lines=True, chunksize=chunk_size)
        elif file_type == "parquet":
            # Note: for true streaming parquet processing, use pyarrow dataset scanner.
            df = pd.read_parquet(file_path)
            reader = (df.iloc[i : i + chunk_size] for i in range(0, len(df), chunk_size))
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

        for chunk in reader:
            processed = process_func(chunk)
            self._check_memory_aggressive()
            yield processed

    def _check_memory_aggressive(self) -> None:
        """Aggressive memory management with forced garbage collection"""
        memory = psutil.virtual_memory()
        memory_percent = memory.percent / 100.0

        if memory_percent > self.memory_threshold:
            logger.warning(f"Memory usage high ({memory_percent:.1%}), triggering aggressive GC")

            # Force garbage collection (full collection)
            gc.collect(2)

            # If still high, try to free more memory (Windows working set trim)
            try:
                import ctypes  # local import (only when needed)

                if hasattr(ctypes, "windll"):
                    # Empty working set on Windows to encourage OS to reclaim pages
                    try:
                        handle = ctypes.windll.kernel32.GetCurrentProcess()
                        # psapi.EmptyWorkingSet returns BOOL; ignore return code
                        ctypes.windll.psapi.EmptyWorkingSet(handle)
                    except Exception:
                        # Fallback: ignore if psapi not available
                        pass
            except Exception:
                pass

            # Another round of GC
            gc.collect(2)

            new_memory_percent = psutil.virtual_memory().percent / 100.0
            logger.info(f"Memory after aggressive GC: {new_memory_percent:.1%}")

    def create_neo4j_batch_queue(self, max_queue_size: int = 10000) -> "Neo4jBatchQueue":
        """Create a queue for efficient Neo4j batch operations"""
        return Neo4jBatchQueue(max_queue_size)

    def get_performance_report(self) -> Dict[str, Any]:
        """Get performance metrics report"""
        if not self.enable_profiling:
            return {"message": "Profiling not enabled"}

        report: Dict[str, Any] = {}
        for metric_name, metric_data in self.metrics.items():
            if metric_data:
                report[metric_name] = {
                    "count": len(metric_data),
                    "avg_duration": float(np.mean([m["duration"] for m in metric_data])),
                    "avg_rate": float(np.mean([m.get("rate", 0.0) for m in metric_data])),
                    "total_failed": int(sum([m.get("failed", 0) for m in metric_data])),
                }

        return report


class Neo4jBatchQueue:
    """Queue for accumulating Neo4j operations for batch execution"""

    def __init__(self, max_size: int = 10000):
        self.max_size = max_size
        self.queue: Queue = Queue(maxsize=max_size)
        self.buffer: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def add(self, item: Dict[str, Any]) -> None:
        """Add item to queue"""
        with self._lock:
            self.buffer.append(item)
            if len(self.buffer) >= self.max_size:
                self.flush()

    def flush(self) -> List[Dict[str, Any]]:
        """Flush and return buffer contents"""
        with self._lock:
            items = self.buffer.copy()
            self.buffer.clear()
            return items

    def size(self) -> int:
        """Get current buffer size"""
        with self._lock:
            return len(self.buffer)


class DataValidator:
    """Enhanced data validation with caching"""

    # Cache for validation results
    _validation_cache: Dict[str, bool] = {}
    _cache_lock = threading.Lock()

    # ADNI Data Quality Advisory (March 2026): 78 participants with site
    # prefix 381_S_ were flagged for serious data quality concerns in
    # clinically acquired cognitive and functional assessment data.
    # ADNI leadership strongly advises these PTIDs not be used in any analysis.
    EXCLUDED_SITE_PREFIXES = frozenset({"381_S_"})

    @classmethod
    def validate_patient_id(cls, patient_id: str) -> bool:
        """Validate patient ID format with caching.

        Rejects PTIDs from sites flagged by ADNI data quality advisories
        (currently: 381_S_ — 78 participants removed from IDA).
        """
        if not patient_id or not isinstance(patient_id, str):
            return False

        # Check cache
        with cls._cache_lock:
            if patient_id in cls._validation_cache:
                return cls._validation_cache[patient_id]

        # ADNI patient ID pattern (e.g., "011_S_0002")
        import re
        pattern = r"^\d{3}_S_\d{4}$"
        result = bool(re.match(pattern, patient_id))

        # Exclude PTIDs from flagged sites (ADNI data quality advisory)
        if result:
            for prefix in cls.EXCLUDED_SITE_PREFIXES:
                if patient_id.startswith(prefix):
                    result = False
                    break

        # Cache result
        with cls._cache_lock:
            cls._validation_cache[patient_id] = result

        return result

    @staticmethod
    def validate_visit_code(viscode: str) -> bool:
        """Validate visit code format"""
        if not viscode or not isinstance(viscode, str):
            return False

        valid_patterns = [
            "bl",
            "sc",  # baseline, screening
            # months
            "m03",
            "m06",
            "m12",
            "m18",
            "m24",
            "m36",
            "m48",
            "m60",
            "m72",
            # years
            "y1",
            "y2",
            "y3",
            "y4",
            "y5",
            "y6",
            "y7",
            "y8",
        ]

        viscode_lower = viscode.lower()
        return viscode_lower in valid_patterns or viscode_lower.startswith("m")

    @staticmethod
    def validate_image_blob(blob: bytes, max_size_mb: float = 10) -> bool:
        """Validate image blob size"""
        if not blob or not isinstance(blob, bytes):
            return False

        size_mb = len(blob) / (1024 * 1024)
        return size_mb <= max_size_mb

    @staticmethod
    def clean_string(value: Any, max_length: int = 10000) -> str:
        """Clean string values for Neo4j"""
        if value is None:
            return ""

        # Convert to string and strip
        str_value = str(value).strip()

        # Remove null bytes and other problematic characters
        str_value = str_value.replace("\x00", "")
        str_value = "".join(char for char in str_value if ord(char) < 65536)

        # Limit length
        if len(str_value) > max_length:
            str_value = str_value[:max_length] + "..."

        return str_value

    @staticmethod
    def clean_numeric(value: Any) -> Optional[float]:
        """Clean numeric values with better error handling"""
        if value is None or value == "":
            return None

        if isinstance(value, (int, float)):
            if np.isnan(value) or np.isinf(value):
                return None
            return float(value)

        # Handle string values
        str_value = str(value).strip().upper()
        if str_value in ["NA", "NAN", "NULL", "NONE", "N/A", ".", "-"]:
            return None

        try:
            # Remove common non-numeric characters
            cleaned = str_value.replace(",", "").replace("$", "").replace("%", "")
            result = float(cleaned)

            # Check for valid range
            if np.isnan(result) or np.isinf(result):
                return None

            return result
        except (ValueError, TypeError):
            return None

    @staticmethod
    def validate_batch(batch: List[Dict[str, Any]], required_fields: List[str]) -> Tuple[List[Dict], List[Dict]]:
        """
        Validate a batch of records

        Returns:
            Tuple of (valid_records, invalid_records)
        """
        valid: List[Dict[str, Any]] = []
        invalid: List[Dict[str, Any]] = []

        for record in batch:
            is_valid = True
            for field in required_fields:
                if field not in record or record[field] is None:
                    is_valid = False
                    break

            if is_valid:
                valid.append(record)
            else:
                invalid.append(record)

        return valid, invalid


# Maintain backward compatibility - Both names point to the same class
BatchProcessor = OptimizedBatchProcessor

# For imports that expect the old name
__all__ = ["BatchProcessor", "OptimizedBatchProcessor", "DataValidator", "Neo4jBatchQueue"]
