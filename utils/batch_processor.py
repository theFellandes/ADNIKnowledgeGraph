"""
Batch processing utilities for parallel execution and memory management
"""

import logging
import concurrent.futures
from typing import List, Callable, Any, Dict, Optional, Generator
from functools import partial
from tqdm import tqdm
import psutil
import gc

logger = logging.getLogger(__name__)


class BatchProcessor:
    """Handle batch processing with memory management and parallelization"""

    def __init__(self, max_workers: int = 8, batch_size: int = 1000,
                 memory_threshold: float = 0.8):
        """
        Initialize batch processor

        Args:
            max_workers: Maximum number of parallel workers
            batch_size: Default batch size
            memory_threshold: Memory usage threshold (0-1) for triggering GC
        """
        self.max_workers = max_workers
        self.batch_size = batch_size
        self.memory_threshold = memory_threshold

    def process_parallel(self, items: List[Any],
                         process_func: Callable,
                         desc: str = "Processing",
                         show_progress: bool = True) -> List[Any]:
        """
        Process items in parallel using ThreadPoolExecutor

        Args:
            items: List of items to process
            process_func: Function to apply to each item
            desc: Description for progress bar
            show_progress: Whether to show progress bar

        Returns:
            List of results
        """
        results = []
        failed_items = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_item = {
                executor.submit(process_func, item): item
                for item in items
            }

            # Process completed tasks
            iterator = concurrent.futures.as_completed(future_to_item)
            if show_progress:
                iterator = tqdm(iterator, total=len(items), desc=desc)

            for future in iterator:
                item = future_to_item[future]
                try:
                    result = future.result(timeout=60)
                    if result is not None:
                        results.append(result)
                except Exception as e:
                    logger.error(f"Failed to process item: {e}")
                    failed_items.append(item)

                # Check memory usage
                self._check_memory()

        if failed_items:
            logger.warning(f"Failed to process {len(failed_items)} items")

        return results

    def process_in_batches(self, items: List[Any],
                           batch_func: Callable,
                           batch_size: Optional[int] = None,
                           desc: str = "Processing batches") -> int:
        """
        Process items in batches

        Args:
            items: List of items to process
            batch_func: Function to process a batch
            batch_size: Size of each batch (uses default if None)
            desc: Description for progress

        Returns:
            Total number of items processed
        """
        if batch_size is None:
            batch_size = self.batch_size

        total_processed = 0
        num_batches = (len(items) + batch_size - 1) // batch_size

        for i in tqdm(range(0, len(items), batch_size),
                      total=num_batches, desc=desc):
            batch = items[i:i + batch_size]

            try:
                batch_func(batch)
                total_processed += len(batch)
            except Exception as e:
                logger.error(f"Batch processing failed at index {i}: {e}")
                raise

            # Check memory after each batch
            self._check_memory()

        return total_processed

    def chunked_reader(self, file_path: str,
                       chunk_size: int = 10000) -> Generator[List[Dict], None, None]:
        """
        Read large CSV file in chunks

        Args:
            file_path: Path to CSV file
            chunk_size: Number of rows per chunk

        Yields:
            List of dictionaries for each chunk
        """
        import pandas as pd

        for chunk_df in pd.read_csv(file_path, chunksize=chunk_size):
            yield chunk_df.to_dict('records')
            self._check_memory()

    def parallel_file_processing(self, file_paths: List[str],
                                 file_processor: Callable,
                                 desc: str = "Processing files") -> Dict[str, Any]:
        """
        Process multiple files in parallel

        Args:
            file_paths: List of file paths
            file_processor: Function to process each file
            desc: Description for progress

        Returns:
            Dictionary mapping file paths to results
        """
        results = {}

        with concurrent.futures.ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_file = {
                executor.submit(file_processor, fp): fp
                for fp in file_paths
            }

            for future in tqdm(concurrent.futures.as_completed(future_to_file),
                               total=len(file_paths), desc=desc):
                file_path = future_to_file[future]
                try:
                    result = future.result()
                    results[file_path] = result
                except Exception as e:
                    logger.error(f"Failed to process file {file_path}: {e}")
                    results[file_path] = {'error': str(e)}

        return results

    def _check_memory(self):
        """Check memory usage and trigger garbage collection if needed"""
        memory_percent = psutil.virtual_memory().percent / 100

        if memory_percent > self.memory_threshold:
            logger.warning(f"Memory usage high ({memory_percent:.1%}), triggering garbage collection")
            gc.collect()

            # Check again after GC
            new_memory_percent = psutil.virtual_memory().percent / 100
            logger.info(f"Memory usage after GC: {new_memory_percent:.1%}")

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
        chunk_size = (len(data) + partitions - 1) // partitions
        return [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]


class DataValidator:
    """Validate data before insertion"""

    @staticmethod
    def validate_patient_id(patient_id: str) -> bool:
        """Validate patient ID format"""
        if not patient_id or not isinstance(patient_id, str):
            return False

        # ADNI patient ID pattern (e.g., "011_S_0002")
        import re
        pattern = r'^\d{3}_S_\d{4}$'
        return bool(re.match(pattern, patient_id))

    @staticmethod
    def validate_visit_code(viscode: str) -> bool:
        """Validate visit code format"""
        if not viscode or not isinstance(viscode, str):
            return False

        valid_patterns = [
            'bl', 'sc',  # baseline, screening
            'm03', 'm06', 'm12', 'm18', 'm24', 'm36', 'm48',  # months
            'y1', 'y2', 'y3', 'y4', 'y5'  # years
        ]

        return viscode.lower() in valid_patterns or viscode.lower().startswith('m')

    @staticmethod
    def validate_image_blob(blob: bytes, max_size_mb: float = 10) -> bool:
        """Validate image blob size"""
        if not blob or not isinstance(blob, bytes):
            return False

        size_mb = len(blob) / (1024 * 1024)
        return size_mb <= max_size_mb

    @staticmethod
    def clean_string(value: Any) -> str:
        """Clean string values for Neo4j"""
        if value is None:
            return ""

        # Convert to string and strip
        str_value = str(value).strip()

        # Remove null bytes
        str_value = str_value.replace('\x00', '')

        # Limit length
        max_length = 10000
        if len(str_value) > max_length:
            str_value = str_value[:max_length] + "..."

        return str_value

    @staticmethod
    def clean_numeric(value: Any) -> Optional[float]:
        """Clean numeric values"""
        if value is None or value == '' or str(value).upper() in ['NA', 'NAN', 'NULL']:
            return None

        try:
            return float(value)
        except (ValueError, TypeError):
            return None