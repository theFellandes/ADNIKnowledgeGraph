"""
Neo4j database connector with connection pooling and batch operations
"""

import logging
from typing import List, Dict, Any, Optional
from contextlib import contextmanager
from neo4j import GraphDatabase, Session
from neo4j.exceptions import ServiceUnavailable, SessionExpired

logger = logging.getLogger(__name__)


class Neo4jConnector:
    """Neo4j database connector with connection pooling"""

    def __init__(self, uri: str, user: str, password: str, max_pool_size: int = 50):
        """
        Initialize Neo4j connection

        Args:
            uri: Neo4j URI (e.g., "bolt://localhost:7687")
            user: Username
            password: Password
            max_pool_size: Maximum connection pool size
        """
        self.uri = uri
        self.user = user
        self.password = password

        self.driver = GraphDatabase.driver(
            uri,
            auth=(user, password),
            max_connection_pool_size=max_pool_size,
            connection_acquisition_timeout=60,
            max_transaction_retry_time=30
        )

        logger.info(f"Neo4j connector initialized for {uri}")

    def close(self):
        """Close the database connection"""
        if self.driver:
            self.driver.close()
            logger.info("Neo4j connection closed")

    @contextmanager
    def get_session(self, database: str = None):
        """Get a database session with automatic cleanup"""
        session = None
        try:
            session = self.driver.session(database=database)
            yield session
        finally:
            if session:
                session.close()

    def verify_connection(self) -> bool:
        """Verify database connection is working"""
        try:
            with self.get_session() as session:
                result = session.run("RETURN 1 as test")
                return result.single()["test"] == 1
        except Exception as e:
            logger.error(f"Connection verification failed: {e}")
            return False

    def run_query(self, query: str, parameters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Run a single query and return results

        Args:
            query: Cypher query
            parameters: Query parameters

        Returns:
            List of result records as dictionaries
        """
        results = []
        with self.get_session() as session:
            result = session.run(query, parameters or {})
            results = [record.data() for record in result]
        return results

    def execute_write_transaction(self, query: str, parameters: Dict[str, Any] = None) -> None:
        """Execute a write transaction"""

        def _write(tx):
            tx.run(query, parameters or {})

        with self.get_session() as session:
            session.execute_write(_write)

    def batch_write(self, query: str, data_list: List[Dict[str, Any]],
                    batch_size: int = 1000) -> int:
        """
        Execute batch write operations

        Args:
            query: Cypher query with $batch parameter
            data_list: List of data dictionaries
            batch_size: Size of each batch

        Returns:
            Total number of records processed
        """
        total_processed = 0

        with self.get_session() as session:
            for i in range(0, len(data_list), batch_size):
                batch = data_list[i:i + batch_size]

                def _batch_write(tx):
                    result = tx.run(query, batch=batch)
                    return result.consume().counters

                try:
                    counters = session.execute_write(_batch_write)
                    total_processed += len(batch)

                    if i % (batch_size * 10) == 0:
                        logger.info(f"Processed {total_processed}/{len(data_list)} records")

                except Exception as e:
                    logger.error(f"Batch write failed at index {i}: {e}")
                    raise

        logger.info(f"Batch write completed: {total_processed} records")
        return total_processed

    def create_constraint(self, label: str, property: str) -> bool:
        """Create a uniqueness constraint"""
        try:
            query = f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{label}) REQUIRE n.{property} IS UNIQUE"
            self.execute_write_transaction(query)
            logger.info(f"Created constraint: {label}.{property}")
            return True
        except Exception as e:
            logger.error(f"Failed to create constraint {label}.{property}: {e}")
            return False

    def create_index(self, label: str, property: str) -> bool:
        """Create an index"""
        try:
            query = f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.{property})"
            self.execute_write_transaction(query)
            logger.info(f"Created index: {label}.{property}")
            return True
        except Exception as e:
            logger.error(f"Failed to create index {label}.{property}: {e}")
            return False

    def clear_database(self) -> bool:
        """Clear all nodes and relationships"""
        try:
            # Try APOC first for better performance
            try:
                query = """
                CALL apoc.periodic.iterate(
                    'MATCH (n) RETURN n',
                    'DETACH DELETE n',
                    {batchSize: 10000, parallel: false}
                )
                """
                self.execute_write_transaction(query)
                logger.info("Database cleared using APOC")
            except:
                # Fallback to standard deletion
                self.execute_write_transaction("MATCH (n) DETACH DELETE n")
                logger.info("Database cleared using standard deletion")

            return True
        except Exception as e:
            logger.error(f"Failed to clear database: {e}")
            return False

    def get_node_count(self, label: str = None) -> int:
        """Get count of nodes with optional label filter"""
        if label:
            query = f"MATCH (n:{label}) RETURN count(n) as count"
        else:
            query = "MATCH (n) RETURN count(n) as count"

        result = self.run_query(query)
        return result[0]["count"] if result else 0

    def get_relationship_count(self, relationship_type: str = None) -> int:
        """Get count of relationships with optional type filter"""
        if relationship_type:
            query = f"MATCH ()-[r:{relationship_type}]->() RETURN count(r) as count"
        else:
            query = "MATCH ()-[r]->() RETURN count(r) as count"

        result = self.run_query(query)
        return result[0]["count"] if result else 0