"""
Step 5: Optimized Image Processing with Batch Operations
Significantly faster Neo4j insertion using proper batching and indexing
"""

import logging
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import concurrent.futures
from dataclasses import dataclass, asdict

from models.entities import ImagingStudy, ImageNode
from utils.neo4j_connector import Neo4jConnector
from utils.batch_processor import BatchProcessor
from utils.elasticsearch_indexer import SearchIndexer

logger = logging.getLogger(__name__)


class OptimizedImageProcessor:
    """Optimized image processing with proper batching"""

    def __init__(self, connector: Neo4jConnector, base_path: str,
                 storage_path: str, es_host: str = 'localhost',
                 es_port: int = 9200, batch_size: int = 500,  # Increased batch size
                 max_workers: int = 8):
        self.connector = connector
        self.base_path = Path(base_path).resolve()
        self.storage_path = Path(storage_path).resolve()
        self.batch_size = batch_size
        self.max_workers = max_workers

        # Initialize components
        self.batch_processor = BatchProcessor(max_workers=max_workers)
        self.es_indexer = SearchIndexer(es_host, es_port) if es_host else None

        # Pre-create indexes for performance
        self._create_optimized_indexes()

        self.processing_stats = {
            'total_images': 0,
            'neo4j_inserted': 0,
            'es_indexed': 0,
            'time_taken': 0
        }

    def _create_optimized_indexes(self):
        """Create optimized indexes for fast insertion"""
        logger.info("Creating optimized indexes for fast image insertion...")

        # Create composite indexes for faster lookups
        queries = [
            "CREATE INDEX IF NOT EXISTS FOR (i:ImageNode) ON (i.patient_id, i.study_id)",
            "CREATE INDEX IF NOT EXISTS FOR (i:ImageNode) ON (i.image_hash)",
            "CREATE INDEX IF NOT EXISTS FOR (s:ImagingStudy) ON (s.patient_id, s.study_date)",
            "CREATE INDEX IF NOT EXISTS FOR (p:Patient) ON (p.ptid)"
        ]

        for query in queries:
            try:
                self.connector.execute_write_transaction(query)
            except:
                pass  # Index might already exist

    def execute(self) -> Dict[str, Any]:
        """Execute optimized image processing"""
        start_time = datetime.now()

        # Step 1: Load existing images (for deduplication)
        existing_hashes = self._get_existing_image_hashes()
        logger.info(f"Found {len(existing_hashes)} existing images")

        # Step 2: Process metadata files
        metadata_files = self._find_metadata_files()
        new_metadata = self._filter_new_metadata(metadata_files, existing_hashes)
        logger.info(f"Processing {len(new_metadata)} new images")

        if not new_metadata:
            return {
                'images_processed': 0,
                'time_taken': (datetime.now() - start_time).total_seconds()
            }

        # Step 3: Bulk create imaging studies (much faster)
        studies_created = self._bulk_create_imaging_studies(new_metadata)
        logger.info(f"Created {studies_created} imaging studies")

        # Step 4: Bulk create image nodes with relationships
        images_created = self._bulk_create_images_with_relationships(new_metadata)
        logger.info(f"Created {images_created} image nodes")

        # Step 5: Index to Elasticsearch (if available)
        if self.es_indexer:
            es_count = self._bulk_index_elasticsearch(new_metadata)
            self.processing_stats['es_indexed'] = es_count

        self.processing_stats['neo4j_inserted'] = images_created
        self.processing_stats['time_taken'] = (datetime.now() - start_time).total_seconds()

        logger.info(f"✅ Processed {images_created} images in {self.processing_stats['time_taken']:.2f} seconds")

        return self.processing_stats

    def _get_existing_image_hashes(self) -> set:
        """Get existing image hashes using optimized query"""
        query = """
        MATCH (i:ImageNode)
        WHERE i.image_hash IS NOT NULL
        RETURN i.image_hash as hash
        """

        # Use pagination for large datasets
        all_hashes = set()
        skip = 0
        limit = 10000

        while True:
            paginated_query = f"{query} SKIP {skip} LIMIT {limit}"
            results = self.connector.run_query(paginated_query)

            if not results:
                break

            for r in results:
                if r.get('hash'):
                    all_hashes.add(r['hash'])

            if len(results) < limit:
                break

            skip += limit

        return all_hashes

    def _find_metadata_files(self) -> List[Dict[str, Any]]:
        """Find and load metadata files"""
        metadata_files = []
        metadata_path = self.storage_path / "metadata"

        if metadata_path.exists():
            for json_file in metadata_path.rglob("*.json"):
                try:
                    with open(json_file, 'r') as f:
                        metadata = json.load(f)
                        metadata['_file_path'] = str(json_file)
                        metadata_files.append(metadata)
                except Exception as e:
                    logger.warning(f"Could not load {json_file}: {e}")

        return metadata_files

    def _filter_new_metadata(self, metadata_files: List[Dict], existing_hashes: set) -> List[Dict]:
        """Filter out already processed images"""
        new_metadata = []

        for metadata in metadata_files:
            # Generate hash
            hash_str = f"{metadata.get('patient_id', '')}_{metadata.get('study_date', '')}_{metadata.get('series_id', '')}"
            image_hash = hashlib.sha256(hash_str.encode()).hexdigest()[:32]
            metadata['image_hash'] = image_hash

            if image_hash not in existing_hashes:
                new_metadata.append(metadata)

        return new_metadata

    def _bulk_create_imaging_studies(self, metadata_list: List[Dict]) -> int:
        """Bulk create imaging studies using UNWIND for performance"""
        # Extract unique studies
        studies = {}
        for metadata in metadata_list:
            study_id = metadata.get('study_id', '')
            if study_id and study_id not in studies:
                studies[study_id] = {
                    'study_id': study_id,
                    'patient_id': metadata.get('patient_id', ''),
                    'modality': metadata.get('modality', 'UNKNOWN'),
                    'study_date': metadata.get('study_date', ''),
                    'created_at': datetime.now().isoformat()
                }

        if not studies:
            return 0

        # Bulk create with single query
        query = """
        UNWIND $studies as study
        MERGE (s:ImagingStudy {study_id: study.study_id})
        SET s += study
        WITH s, study
        MATCH (p:Patient {ptid: study.patient_id})
        MERGE (p)-[:HAS_IMAGING_STUDY]->(s)
        RETURN count(s) as count
        """

        # Process in chunks for very large datasets
        study_list = list(studies.values())
        total_created = 0

        for i in range(0, len(study_list), self.batch_size):
            batch = study_list[i:i + self.batch_size]
            result = self.connector.run_query(query, {'studies': batch})
            if result:
                total_created += result[0].get('count', 0)

        return total_created

    def _bulk_create_images_with_relationships(self, metadata_list: List[Dict]) -> int:
        """Bulk create images with all relationships in single query"""
        # Prepare image data
        images = []
        for metadata in metadata_list:
            # Ensure paths are absolute
            png_path = str(Path(metadata.get('png_path', '')).resolve()) if metadata.get('png_path') else ''
            thumbnail_path = str(Path(metadata.get('thumbnail_path', '')).resolve()) if metadata.get(
                'thumbnail_path') else ''
            dcm_path = str(Path(metadata.get('dcm_path', metadata.get('original_path', ''))).resolve()) if metadata.get(
                'dcm_path') or metadata.get('original_path') else ''

            image_data = {
                'image_hash': metadata['image_hash'],
                'image_id': metadata['image_hash'][:16],
                'study_id': metadata.get('study_id', ''),
                'patient_id': metadata.get('patient_id', ''),
                'series_id': metadata.get('series_id', ''),
                'series_description': metadata.get('series_description', ''),
                'modality': metadata.get('modality', 'UNKNOWN'),
                'dcm_path': dcm_path,
                'png_path': png_path,
                'thumbnail_path': thumbnail_path,
                'study_date': metadata.get('study_date', ''),
                'conversion_date': metadata.get('conversion_date', datetime.now().isoformat()),
                'naming_convention': metadata.get('naming_convention', ''),
                'processing_status': 'completed',
                'created_at': datetime.now().isoformat()
            }

            # Add resolution data if available
            if 'original_resolution' in metadata:
                res = metadata['original_resolution']
                if isinstance(res, list) and len(res) >= 2:
                    image_data['original_width'] = res[0]
                    image_data['original_height'] = res[1]

            images.append(image_data)

        # Optimized query that creates nodes and relationships together
        query = """
        UNWIND $images as img
        CREATE (i:ImageNode)
        SET i = img
        WITH i, img
        MATCH (s:ImagingStudy {study_id: img.study_id})
        CREATE (s)-[:HAS_IMAGE]->(i)
        WITH i, img
        MATCH (p:Patient {ptid: img.patient_id})
        CREATE (p)-[:HAS_IMAGE]->(i)
        RETURN count(i) as count
        """

        # Process in optimized chunks
        total_created = 0
        chunk_size = min(self.batch_size, 500)  # Optimal chunk size for images

        for i in range(0, len(images), chunk_size):
            batch = images[i:i + chunk_size]
            try:
                result = self.connector.run_query(query, {'images': batch})
                if result:
                    total_created += result[0].get('count', 0)

                # Log progress
                if i % (chunk_size * 10) == 0:
                    logger.info(f"Progress: {i}/{len(images)} images inserted")

            except Exception as e:
                logger.error(f"Failed to insert batch {i // chunk_size}: {e}")
                # Try smaller batch on failure
                for img in batch:
                    try:
                        result = self.connector.run_query(query, {'images': [img]})
                        if result:
                            total_created += result[0].get('count', 0)
                    except:
                        pass

        return total_created

    def _bulk_index_elasticsearch(self, metadata_list: List[Dict]) -> int:
        """Bulk index to Elasticsearch"""
        if not self.es_indexer:
            return 0

        es_documents = []
        for metadata in metadata_list:
            es_doc = {
                'image_hash': metadata.get('image_hash'),
                'patient_id': metadata.get('patient_id'),
                'study_id': metadata.get('study_id'),
                'modality': metadata.get('modality'),
                'study_date': metadata.get('study_date'),
                'png_path': str(Path(metadata.get('png_path', '')).resolve()) if metadata.get('png_path') else '',
                'thumbnail_path': str(Path(metadata.get('thumbnail_path', '')).resolve()) if metadata.get(
                    'thumbnail_path') else '',
                'indexed_date': datetime.now().isoformat()
            }
            es_documents.append(es_doc)

        success_count, _ = self.es_indexer.bulk_index_images(es_documents)
        return success_count


def execute_image_processing_optimized(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                                       base_path: str, storage_path: str,
                                       storage_config: Dict[str, Any] = None,
                                       max_workers: int = 8) -> Dict[str, Any]:
    """Optimized image processing execution"""
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        config = storage_config or {}
        batch_size = config.get('batch_size', 500)  # Larger batch size
        es_host = config.get('es_host', 'localhost')
        es_port = config.get('es_port', 9200)

        processor = OptimizedImageProcessor(
            connector=connector,
            base_path=base_path,
            storage_path=storage_path,
            es_host=es_host,
            es_port=es_port,
            batch_size=batch_size,
            max_workers=max_workers
        )

        results = processor.execute()
        results['processor'] = processor

        return results

    except Exception as e:
        logger.error(f"Image processing failed: {e}")
        raise
    finally:
        connector.close()