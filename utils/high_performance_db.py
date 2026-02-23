"""
High-performance database operations for ADNI pipeline
Provides enhanced batching, multithreading, and optimized Neo4j operations
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Any, Optional, Callable
from queue import Queue
import uuid
from dataclasses import dataclass

from .neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


@dataclass
class BatchOperation:
    """Represents a batch database operation"""
    operation_id: str
    query: str
    data: List[Dict[str, Any]]
    batch_size: int
    param_name: str = "batch"
    priority: int = 0  # Higher priority operations execute first


class HighPerformanceDBManager:
    """High-performance database manager with batching and threading"""
    
    def __init__(self, neo4j_connector: Neo4jConnector, max_workers: int = 4):
        """
        Initialize high-performance database manager
        
        Args:
            neo4j_connector: Neo4j connector instance
            max_workers: Maximum number of worker threads
        """
        self.neo4j = neo4j_connector
        self.max_workers = max_workers
        self.operation_queue = Queue()
        self.results = {}
        self.stats = {
            'operations_completed': 0,
            'total_records_processed': 0,
            'total_time_seconds': 0,
            'errors': []
        }
        
    def add_batch_operation(self, operation_id: str, query: str, data: List[Dict[str, Any]], 
                           batch_size: int = 1000, param_name: str = "batch", priority: int = 0) -> str:
        """
        Add a batch operation to the queue
        
        Args:
            operation_id: Unique identifier for the operation
            query: Cypher query to execute
            data: List of data dictionaries
            batch_size: Size of each batch
            param_name: Parameter name for the batch in the query
            priority: Operation priority (higher = executed first)
            
        Returns:
            Operation ID
        """
        if not operation_id:
            operation_id = f"op_{uuid.uuid4().hex[:8]}"
            
        operation = BatchOperation(
            operation_id=operation_id,
            query=query,
            data=data,
            batch_size=batch_size,
            param_name=param_name,
            priority=priority
        )
        
        self.operation_queue.put(operation)
        logger.info(f"Added batch operation '{operation_id}' with {len(data)} records")
        return operation_id
    
    def execute_all_operations(self, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """
        Execute all queued operations using multithreading
        
        Args:
            progress_callback: Optional callback function for progress updates
            
        Returns:
            Dictionary with execution results and statistics
        """
        start_time = time.time()
        operations = []
        
        # Collect all operations from queue
        while not self.operation_queue.empty():
            operations.append(self.operation_queue.get())
        
        if not operations:
            logger.warning("No operations to execute")
            return self.stats
        
        # Sort by priority (higher priority first)
        operations.sort(key=lambda x: x.priority, reverse=True)
        
        logger.info(f"Executing {len(operations)} batch operations with {self.max_workers} workers")
        
        # Execute operations in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all operations
            future_to_operation = {
                executor.submit(self._execute_single_operation, op): op 
                for op in operations
            }
            
            completed = 0
            for future in as_completed(future_to_operation):
                operation = future_to_operation[future]
                
                try:
                    result = future.result()
                    self.results[operation.operation_id] = result
                    self.stats['operations_completed'] += 1
                    self.stats['total_records_processed'] += len(operation.data)
                    
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, len(operations), operation.operation_id)
                        
                    logger.info(f"✅ Completed operation '{operation.operation_id}' "
                              f"({completed}/{len(operations)})")
                    
                except Exception as e:
                    error_msg = f"Operation '{operation.operation_id}' failed: {e}"
                    logger.error(error_msg)
                    self.stats['errors'].append(error_msg)
                    self.results[operation.operation_id] = {'error': str(e)}
        
        self.stats['total_time_seconds'] = time.time() - start_time
        
        # Log final statistics
        self._log_execution_stats()
        
        return {
            'stats': self.stats,
            'results': self.results
        }
    
    def _execute_single_operation(self, operation: BatchOperation) -> Dict[str, Any]:
        """Execute a single batch operation"""
        start_time = time.time()
        
        try:
            # Execute the batch operation
            records_processed = self.neo4j.batch_write(
                query=operation.query,
                data_list=operation.data,
                batch_size=operation.batch_size,
                param_name=operation.param_name
            )
            
            duration = time.time() - start_time
            
            return {
                'operation_id': operation.operation_id,
                'records_processed': records_processed,
                'duration_seconds': duration,
                'records_per_second': records_processed / duration if duration > 0 else 0,
                'status': 'success'
            }
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Batch operation '{operation.operation_id}' failed after {duration:.2f}s: {e}")
            
            return {
                'operation_id': operation.operation_id,
                'records_processed': 0,
                'duration_seconds': duration,
                'error': str(e),
                'status': 'failed'
            }
    
    def _log_execution_stats(self):
        """Log execution statistics"""
        stats = self.stats
        
        logger.info("=" * 60)
        logger.info("HIGH-PERFORMANCE DB EXECUTION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Operations completed: {stats['operations_completed']}")
        logger.info(f"Total records processed: {stats['total_records_processed']:,}")
        logger.info(f"Total execution time: {stats['total_time_seconds']:.2f} seconds")
        
        if stats['total_time_seconds'] > 0:
            records_per_second = stats['total_records_processed'] / stats['total_time_seconds']
            logger.info(f"Average throughput: {records_per_second:,.0f} records/second")
        
        if stats['errors']:
            logger.warning(f"Errors encountered: {len(stats['errors'])}")
            for error in stats['errors'][:5]:  # Show first 5 errors
                logger.warning(f"  - {error}")
            if len(stats['errors']) > 5:
                logger.warning(f"  ... and {len(stats['errors']) - 5} more errors")
        
        logger.info("=" * 60)


class OptimizedFamilyExtractor:
    """Optimized family extractor with high-performance database operations"""
    
    def __init__(self, neo4j_connector: Neo4jConnector, max_workers: int = 4):
        """
        Initialize optimized family extractor
        
        Args:
            neo4j_connector: Neo4j connector instance
            max_workers: Maximum number of worker threads
        """
        self.neo4j = neo4j_connector
        self.db_manager = HighPerformanceDBManager(neo4j_connector, max_workers)
        
    def batch_create_family_members(self, family_members: List[Dict[str, Any]]) -> str:
        """
        Queue family member creation for batch processing
        
        Args:
            family_members: List of family member data
            
        Returns:
            Operation ID
        """
        query = """
        UNWIND $batch as member
        MERGE (fm:FamilyMember {member_id: member.member_id})
        SET fm += member,
            fm.patient_id = member.patient_id,
            fm.relationship_type = member.relationship_type,
            fm.gender = member.gender,
            fm.has_dementia = member.has_dementia,
            fm.dementia_type = member.dementia_type,
            fm.age_at_onset = member.age_at_onset,
            fm.created_at = datetime(),
            fm.updated_at = datetime()
        """
        
        return self.db_manager.add_batch_operation(
            operation_id="create_family_members",
            query=query,
            data=family_members,
            batch_size=1000,
            priority=10  # High priority
        )
    
    def batch_create_relationships(self, relationships: List[Dict[str, Any]], 
                                 relationship_type: str) -> str:
        """
        Queue relationship creation for batch processing
        
        Args:
            relationships: List of relationship data
            relationship_type: Type of relationship (HAS_PARENT, HAS_SIBLING, etc.)
            
        Returns:
            Operation ID
        """
        # Different queries for different relationship types
        if relationship_type == "HAS_PARENT":
            query = """
            UNWIND $batch as rel
            MATCH (p:Patient {ptid: rel.patient_id})
            MATCH (fm:FamilyMember {member_id: rel.parent_id})
            MERGE (p)-[r:HAS_PARENT]->(fm)
            SET r.parent_type = rel.parent_type,
                r.has_dementia = rel.has_dementia,
                r.dementia_type = rel.dementia_type,
                r.age_at_onset = rel.age_at_onset,
                r.created_at = datetime()
            """
        elif relationship_type == "HAS_CHILD":
            query = """
            UNWIND $batch as rel
            MATCH (fm:FamilyMember {member_id: rel.parent_id})
            MATCH (p:Patient {ptid: rel.patient_id})
            MERGE (fm)-[r:HAS_CHILD]->(p)
            SET r.child_gender = rel.child_gender,
                r.is_affected = rel.is_affected,
                r.created_at = datetime()
            """
        elif relationship_type == "HAS_SIBLING":
            query = """
            UNWIND $batch as rel
            CALL {
                WITH rel
                MATCH (from) WHERE 
                    (from:Patient AND from.ptid = rel.from_id AND rel.from_type = 'Patient') OR
                    (from:FamilyMember AND from.member_id = rel.from_id AND rel.from_type = 'FamilyMember')
                MATCH (to) WHERE 
                    (to:Patient AND to.ptid = rel.to_id AND rel.to_type = 'Patient') OR
                    (to:FamilyMember AND to.member_id = rel.to_id AND rel.to_type = 'FamilyMember')
                MERGE (from)-[r:HAS_SIBLING]->(to)
                SET r.sibling_gender = rel.sibling_gender,
                    r.has_dementia = rel.has_dementia,
                    r.dementia_type = rel.dementia_type,
                    r.age_at_onset = rel.age_at_onset,
                    r.created_at = datetime()
            }
            """
        else:
            query = """
            UNWIND $batch as rel
            MATCH (p:Patient {ptid: rel.patient_id})
            MATCH (fm:FamilyMember {member_id: rel.member_id})
            MERGE (p)-[r:HAS_FAMILY_MEMBER]->(fm)
            SET r.relationship_type = rel.relationship_type,
                r.has_dementia = rel.has_dementia,
                r.created_at = datetime()
            """
        
        return self.db_manager.add_batch_operation(
            operation_id=f"create_{relationship_type.lower()}_relationships",
            query=query,
            data=relationships,
            batch_size=500,  # Smaller batches for complex relationship queries
            priority=5  # Medium priority
        )
    
    def execute_all_operations(self) -> Dict[str, Any]:
        """Execute all queued database operations"""
        def progress_callback(completed: int, total: int, operation_id: str):
            percentage = (completed / total) * 100
            logger.info(f"Progress: {percentage:.1f}% ({completed}/{total}) - "
                       f"Completed: {operation_id}")
        
        return self.db_manager.execute_all_operations(progress_callback)