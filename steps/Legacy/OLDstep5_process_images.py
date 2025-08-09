"""
Step 5: Process Medical Images (FIXED for Elasticsearch 8.x)
Processes converted PNG images with external storage and Elasticsearch indexing
Fixed: Updated all Elasticsearch API calls for version 8.x compatibility
Fixed: Added robust error handling for file permissions and invalid metadata
"""

import logging
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import concurrent.futures
from dataclasses import dataclass, asdict

from models.entities import ImagingStudy, ImageNode
from utils.neo4j_connector import Neo4jConnector
from utils.batch_processor import BatchProcessor
from elasticsearch import Elasticsearch, helpers

logger = logging.getLogger(__name__)


@dataclass
class ImageMetadataExtended:
    """Extended metadata for images"""
    image_id: str
    patient_id: str
    study_id: str
    series_id: str
    modality: str
    original_path: str
    converted_path: str
    thumbnail_path: str
    original_resolution: Tuple[int, int]
    converted_resolution: Tuple[int, int]
    thumbnail_resolution: Tuple[int, int]
    conversion_date: str
    study_date: str
    series_description: str
    dicom_metadata: Dict[str, Any]
    file_hash: str
    naming_convention: str
    processing_status: str = "completed"
    quality_verified: bool = True
    indexed_date: str = ""


class ElasticsearchImageIndexer:
    """Handle Elasticsearch indexing for images - Fixed for Elasticsearch 8.x"""

    def __init__(self, host: str = 'localhost', port: int = 9200):
        """Initialize Elasticsearch connection"""
        try:
            # Configure for Elasticsearch 8.x with security disabled
            # Force compatibility with version 8
            from elasticsearch import __version__ as es_version
            logger.info(f"Using elasticsearch-py version: {es_version}")

            self.es = Elasticsearch(
                [f"http://{host}:{port}"],
                verify_certs=False,
                ssl_show_warn=False,
                request_timeout=30,
                max_retries=3,
                retry_on_timeout=True,
                # Add basic auth bypass for unsecured ES
                basic_auth=None
            )

            # Test connection with a simple info request
            try:
                info = self.es.info()
                logger.info(f"Connected to Elasticsearch {info['version']['number']}")
                self._create_index_if_not_exists()

            except Exception as conn_error:
                logger.warning(f"Cannot connect to Elasticsearch: {conn_error}. Will skip indexing.")
                self.es = None

        except Exception as e:
            logger.warning(f"Elasticsearch not available: {e}. Will skip indexing.")
            self.es = None

    def _create_index_if_not_exists(self):
        """Create image index with appropriate mappings - Fixed for ES 8.x"""
        if not self.es:
            return

        index_name = "adni_images"

        try:
            if not self.es.indices.exists(index=index_name):
                # For Elasticsearch 8.x, pass settings and mappings as separate parameters
                settings = {
                    "number_of_shards": 2,
                    "number_of_replicas": 1
                }

                mappings = {
                    "properties": {
                        "image_id": {"type": "keyword"},
                        "patient_id": {"type": "keyword"},
                        "study_id": {"type": "keyword"},
                        "series_id": {"type": "keyword"},
                        "modality": {"type": "keyword"},
                        "original_path": {"type": "keyword"},
                        "converted_path": {"type": "keyword"},
                        "thumbnail_path": {"type": "keyword"},
                        "original_resolution": {
                            "properties": {
                                "width": {"type": "integer"},
                                "height": {"type": "integer"}
                            }
                        },
                        "converted_resolution": {
                            "properties": {
                                "width": {"type": "integer"},
                                "height": {"type": "integer"}
                            }
                        },
                        "thumbnail_resolution": {
                            "properties": {
                                "width": {"type": "integer"},
                                "height": {"type": "integer"}
                            }
                        },
                        "conversion_date": {"type": "date"},
                        "study_date": {"type": "date", "format": "yyyyMMdd"},
                        "series_description": {"type": "text"},
                        "file_hash": {"type": "keyword"},
                        "naming_convention": {"type": "keyword"},
                        "processing_status": {"type": "keyword"},
                        "quality_verified": {"type": "boolean"},
                        "indexed_date": {"type": "date"},
                        "dicom_metadata": {"type": "object", "enabled": False}
                    }
                }

                # Elasticsearch 8.x API - pass settings and mappings as keyword arguments
                self.es.indices.create(
                    index=index_name,
                    settings=settings,
                    mappings=mappings
                )
                logger.info(f"Created Elasticsearch index: {index_name}")

        except Exception as e:
            logger.warning(f"Could not create index {index_name}: {e}")

    def index_image(self, metadata: ImageMetadataExtended) -> bool:
        """Index single image metadata - Fixed for ES 8.x"""
        if not self.es:
            return True  # Return True to not block pipeline

        try:
            # Convert resolution tuples to dict
            doc = asdict(metadata)
            doc['original_resolution'] = {
                'width': metadata.original_resolution[0],
                'height': metadata.original_resolution[1]
            }
            doc['converted_resolution'] = {
                'width': metadata.converted_resolution[0],
                'height': metadata.converted_resolution[1]
            }
            doc['thumbnail_resolution'] = {
                'width': metadata.thumbnail_resolution[0],
                'height': metadata.thumbnail_resolution[1]
            }
            doc['indexed_date'] = datetime.now().isoformat()

            # Elasticsearch 8.x API - use document parameter instead of body
            self.es.index(
                index="adni_images",
                id=metadata.image_id,
                document=doc
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to index image {metadata.image_id}: {e}")
            return False

    def bulk_index_images(self, metadata_list: List[ImageMetadataExtended]) -> int:
        """Bulk index multiple images - Fixed for ES 8.x"""
        if not self.es:
            return len(metadata_list)  # Return success count to not block pipeline

        actions = []

        for metadata in metadata_list:
            doc = asdict(metadata)
            doc['original_resolution'] = {
                'width': metadata.original_resolution[0],
                'height': metadata.original_resolution[1]
            }
            doc['converted_resolution'] = {
                'width': metadata.converted_resolution[0],
                'height': metadata.converted_resolution[1]
            }
            doc['thumbnail_resolution'] = {
                'width': metadata.thumbnail_resolution[0],
                'height': metadata.thumbnail_resolution[1]
            }
            doc['indexed_date'] = datetime.now().isoformat()

            actions.append({
                "_index": "adni_images",
                "_id": metadata.image_id,
                "_source": doc
            })

        try:
            success, _ = helpers.bulk(self.es, actions)
            logger.info(f"Bulk indexed {success} images to Elasticsearch")
            return success
        except Exception as e:
            logger.warning(f"Bulk indexing failed: {e}")
            return 0

    def search_images(self, patient_id: Optional[str] = None,
                     modality: Optional[str] = None,
                     date_range: Optional[Dict[str, str]] = None) -> List[Dict]:
        """Search for images - Fixed for ES 8.x"""
        if not self.es:
            return []

        query = {"bool": {"must": []}}

        if patient_id:
            query["bool"]["must"].append({"term": {"patient_id": patient_id}})

        if modality:
            query["bool"]["must"].append({"term": {"modality": modality}})

        if date_range:
            query["bool"]["must"].append({
                "range": {
                    "study_date": {
                        "gte": date_range.get("from", "19000101"),
                        "lte": date_range.get("to", "30000101")
                    }
                }
            })

        if not query["bool"]["must"]:
            query = {"match_all": {}}

        try:
            # Elasticsearch 8.x API - query structure is the same, but internal handling is different
            result = self.es.search(
                index="adni_images",
                query=query,
                size=10000
            )

            return [hit["_source"] for hit in result["hits"]["hits"]]
        except Exception as e:
            logger.warning(f"Search failed: {e}")
            return []


class FixedImageProcessingPipeline:
    """Fixed image processing pipeline with external storage and Elasticsearch 8.x support"""

    def __init__(self, connector: Neo4jConnector, base_path: str,
                 storage_path: str, es_host: str = 'localhost',
                 es_port: int = 9200, batch_size: int = 100,
                 max_workers: int = 8):
        """
        Initialize fixed image processing pipeline

        Args:
            connector: Neo4j connector
            base_path: Base path for ADNI data
            storage_path: Path to converted images
            es_host: Elasticsearch host
            es_port: Elasticsearch port
            batch_size: Batch size for processing
            max_workers: Maximum parallel workers
        """
        self.connector = connector
        self.base_path = Path(base_path)
        self.storage_path = Path(storage_path)
        self.batch_size = batch_size
        self.max_workers = max_workers

        # Initialize components
        self.batch_processor = BatchProcessor(max_workers=max_workers)
        self.es_indexer = ElasticsearchImageIndexer(es_host, es_port)

        # Storage for processed data
        self.imaging_studies = {}
        self.image_nodes = []
        self.image_metadata = []
        self.processing_stats = {
            'total_found': 0,
            'processed': 0,
            'skipped': 0,
            'failed': 0,
            'indexed': 0,
            'neo4j_created': 0
        }

    def execute(self) -> Dict[str, Any]:
        """
        Execute image processing pipeline with batching and timing

        Returns:
            Dictionary with processing results
        """
        start_time = datetime.now()

        results = {
            'images_processed': 0,
            'studies_created': 0,
            'images_indexed': 0,
            'processing_time': 0,
            'batch_stats': [],
            'errors': []
        }

        try:
            # Step 1: Scan for metadata files
            logger.info("Scanning for converted image metadata...")
            metadata_files = self._scan_metadata_files()
            self.processing_stats['total_found'] = len(metadata_files)
            logger.info(f"Found {len(metadata_files)} metadata files")

            if not metadata_files:
                logger.warning("No metadata files found. Run dcm2png conversion first.")
                return results

            # Step 2: Process in batches
            logger.info(f"Processing images in batches of {self.batch_size}...")
            for batch_num, i in enumerate(range(0, len(metadata_files), self.batch_size)):
                batch = metadata_files[i:i + self.batch_size]
                batch_start = datetime.now()

                logger.info(f"Processing batch {batch_num + 1}/{(len(metadata_files) + self.batch_size - 1) // self.batch_size}")
                batch_results = self._process_batch(batch)

                batch_time = (datetime.now() - batch_start).total_seconds()
                results['batch_stats'].append({
                    'batch_num': batch_num + 1,
                    'size': len(batch),
                    'processed': batch_results['processed'],
                    'time_seconds': batch_time
                })

                logger.info(f"Batch {batch_num + 1} completed in {batch_time:.2f} seconds")

            # Step 3: Create Neo4j nodes
            logger.info("Creating Neo4j nodes...")
            neo4j_results = self._create_neo4j_nodes()
            results['studies_created'] = neo4j_results['studies']
            results['images_processed'] = neo4j_results['images']

            # Step 4: Index to Elasticsearch (if available)
            if self.es_indexer.es:
                logger.info("Indexing to Elasticsearch...")
                results['images_indexed'] = self._index_to_elasticsearch()
            else:
                logger.info("Skipping Elasticsearch indexing (not available)")
                results['images_indexed'] = 0

            # Calculate total time
            total_time = (datetime.now() - start_time).total_seconds()
            results['processing_time'] = total_time

            # Add statistics
            results['statistics'] = self.processing_stats

            # Log summary
            self._log_summary(results)

        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            results['errors'].append(str(e))
            raise

        return results

    def _scan_metadata_files(self) -> List[Path]:
        """Scan for metadata JSON files from converted images"""
        # Look for metadata in the correct location
        # Expected structure: outputs/converted_images/metadata/patient_id/image_metadata.json

        possible_paths = [
            self.storage_path / "metadata",  # Expected: outputs/converted_images/metadata
            self.storage_path,  # Check storage path itself
            self.base_path / "outputs" / "converted_images" / "metadata",  # Absolute path
        ]

        metadata_files = []
        for metadata_root in possible_paths:
            if not metadata_root.exists():
                continue

            logger.info(f"Scanning for metadata in: {metadata_root}")

            # Look for JSON files in patient subdirectories
            # Expected structure: metadata/patient_id/*.json
            for json_file in metadata_root.rglob("*.json"):
                # Skip files in schema_documentation or similar directories
                path_parts = json_file.parts
                skip_dirs = ['schema_documentation', 'schema', 'documentation', 'config',
                            'settings', 'templates', 'examples']

                if any(skip_dir in path_parts for skip_dir in skip_dirs):
                    logger.debug(f"Skipping documentation file: {json_file}")
                    continue

                # Skip files that are obviously not image metadata
                filename_lower = json_file.name.lower()
                skip_patterns = ['schema', 'config', 'settings', 'template', 'example',
                                'readme', 'index', 'manifest']

                if any(pattern in filename_lower for pattern in skip_patterns):
                    logger.debug(f"Skipping non-metadata file: {json_file}")
                    continue

                # Check if file contains image metadata by looking for key fields
                try:
                    with open(json_file, 'r') as f:
                        # Quick check of first 1000 chars to see if it's image metadata
                        content = f.read(1000)
                        # Look for image metadata indicators
                        if any(key in content for key in ['"patient_id"', '"modality"',
                                                          '"series_description"', '"file_hash"',
                                                          '"converted_path"', '"original_path"']):
                            metadata_files.append(json_file)
                            logger.debug(f"Found image metadata: {json_file.relative_to(metadata_root)}")
                except Exception as e:
                    logger.debug(f"Could not read {json_file}: {e}")
                    continue

        if not metadata_files:
            logger.warning(f"No image metadata files found in: {[str(p) for p in possible_paths]}")
            logger.info("Image metadata should be in: outputs/converted_images/metadata/")
            logger.info("Structure should be: metadata/PATIENT_ID/image_001_metadata.json")
        else:
            logger.info(f"Found {len(metadata_files)} image metadata files")
            # Log sample paths to show what was found
            for i, f in enumerate(metadata_files[:3]):
                logger.debug(f"  Sample {i+1}: {f.name}")

        return metadata_files

    def _process_batch(self, metadata_files: List[Path]) -> Dict[str, Any]:
        """Process a batch of metadata files"""
        batch_results = {
            'processed': 0,
            'skipped': 0,
            'failed': 0
        }

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []

            for metadata_file in metadata_files:
                future = executor.submit(self._process_single_metadata, metadata_file)
                futures.append(future)

            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result(timeout=30)
                    if result['success']:
                        if result.get('skipped'):
                            batch_results['skipped'] += 1
                        else:
                            batch_results['processed'] += 1
                    else:
                        batch_results['failed'] += 1
                except Exception as e:
                    logger.error(f"Processing failed: {e}")
                    batch_results['failed'] += 1

        # Update global stats
        self.processing_stats['processed'] += batch_results['processed']
        self.processing_stats['skipped'] += batch_results['skipped']
        self.processing_stats['failed'] += batch_results['failed']

        return batch_results

    def _process_single_metadata(self, metadata_file: Path) -> Dict[str, Any]:
        """Process single metadata file"""
        try:
            with open(metadata_file, 'r') as f:
                metadata_dict = json.load(f)

            # Validate required fields and provide defaults
            patient_id = metadata_dict.get('patient_id', '')
            if not patient_id:
                logger.warning(f"Missing patient_id in {metadata_file}, skipping")
                return {'success': False, 'error': 'Missing patient_id', 'skipped': True}

            # Handle resolution data carefully
            def safe_resolution(res_data):
                if isinstance(res_data, (list, tuple)) and len(res_data) >= 2:
                    return tuple(res_data[:2])
                return (0, 0)

            # Create extended metadata with validation
            metadata = ImageMetadataExtended(
                image_id=(metadata_dict.get('file_hash', '') or hashlib.md5(str(metadata_file).encode()).hexdigest())[:16],
                patient_id=patient_id,
                study_id=f"study_{patient_id}_{metadata_dict.get('study_date', 'unknown')}",
                series_id=metadata_dict.get('series_description', 'unknown'),
                modality=metadata_dict.get('modality', 'UNKNOWN'),
                original_path=metadata_dict.get('original_path', ''),
                converted_path=metadata_dict.get('converted_path', ''),
                thumbnail_path=metadata_dict.get('thumbnail_path', ''),
                original_resolution=safe_resolution(metadata_dict.get('original_resolution', [0, 0])),
                converted_resolution=safe_resolution(metadata_dict.get('converted_resolution', [0, 0])),
                thumbnail_resolution=safe_resolution(metadata_dict.get('thumbnail_resolution', [0, 0])),
                conversion_date=metadata_dict.get('conversion_date', datetime.now().isoformat()),
                study_date=metadata_dict.get('study_date', ''),
                series_description=metadata_dict.get('series_description', ''),
                dicom_metadata=metadata_dict.get('dicom_metadata', {}),
                file_hash=metadata_dict.get('file_hash', ''),
                naming_convention=metadata_dict.get('naming_convention', '')
            )

            # Store for later processing
            self.image_metadata.append(metadata)

            # Create image node
            image_node = self._create_image_node(metadata)
            if image_node:
                self.image_nodes.append(image_node)

                # Update or create imaging study
                self._update_imaging_study(image_node)

            return {'success': True, 'metadata': metadata}

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in metadata file {metadata_file}: {e}")
            return {'success': False, 'error': f'Invalid JSON: {e}'}
        except Exception as e:
            logger.error(f"Failed to process metadata {metadata_file}: {e}")
            return {'success': False, 'error': str(e)}

    def _create_image_node(self, metadata: ImageMetadataExtended) -> Optional[ImageNode]:
        """Create image node from metadata"""
        try:
            # Read thumbnail for Neo4j storage
            thumbnail_blob = None
            if metadata.thumbnail_path and metadata.thumbnail_path != '.':
                thumb_path = Path(metadata.thumbnail_path)
                if thumb_path.exists() and thumb_path.is_file():
                    try:
                        with open(thumb_path, 'rb') as f:
                            thumbnail_blob = f.read()
                    except (PermissionError, OSError) as e:
                        logger.warning(f"Could not read thumbnail {thumb_path}: {e}")
                        thumbnail_blob = None

            image_node = ImageNode(
                image_id=metadata.image_id,
                study_id=metadata.study_id,
                patient_id=metadata.patient_id,
                visit_id=f"{metadata.patient_id}_bl",  # Default to baseline
                series_description=metadata.series_description,
                image_type='CONVERTED_PNG',
                anatomical_region=self._infer_anatomical_region(metadata.series_description),
                pet_tracer=self._infer_pet_tracer(metadata.series_description) if metadata.modality == 'PET' else None,
                file_path=metadata.converted_path,
                thumbnail_blob=thumbnail_blob,  # Store thumbnail in Neo4j
                acquisition_parameters={
                    'original_resolution': metadata.original_resolution,
                    'converted_resolution': metadata.converted_resolution,
                    'study_date': metadata.study_date
                }
            )

            return image_node

        except Exception as e:
            logger.error(f"Failed to create image node: {e}")
            return None

    def _update_imaging_study(self, image_node: ImageNode) -> None:
        """Create or update imaging study"""
        study_id = image_node.study_id

        if study_id not in self.imaging_studies:
            study = ImagingStudy(
                study_id=study_id,
                patient_id=image_node.patient_id,
                visit_id=image_node.visit_id,
                modality=self._extract_modality_from_study_id(study_id),
                study_date=image_node.acquisition_parameters.get('study_date', ''),
                study_description=image_node.series_description
            )
            self.imaging_studies[study_id] = study

    def _create_neo4j_nodes(self) -> Dict[str, int]:
        """Create nodes in Neo4j"""
        results = {'studies': 0, 'images': 0}

        # Create imaging studies
        if self.imaging_studies:
            study_query = """
            UNWIND $batch as study
            MERGE (s:ImagingStudy {study_id: study.study_id})
            SET s.patient_id = study.patient_id,
                s.visit_id = study.visit_id,
                s.modality = study.modality,
                s.study_date = study.study_date,
                s.study_description = study.study_description,
                s.created_at = study.created_at
            WITH s, study
            MATCH (p:Patient {ptid: study.patient_id})
            MERGE (p)-[:HAS_IMAGING_STUDY]->(s)
            """

            study_data = [s.to_dict() for s in self.imaging_studies.values()]
            results['studies'] = self.connector.batch_write(
                study_query, study_data, batch_size=100
            )
            logger.info(f"Created {results['studies']} imaging studies in Neo4j")

        # Create image nodes
        if self.image_nodes:
            image_query = """
            UNWIND $batch as image
            MERGE (i:ImageNode {image_id: image.image_id})
            SET i.study_id = image.study_id,
                i.patient_id = image.patient_id,
                i.visit_id = image.visit_id,
                i.series_description = image.series_description,
                i.image_type = image.image_type,
                i.anatomical_region = image.anatomical_region,
                i.pet_tracer = image.pet_tracer,
                i.file_path = image.file_path,
                i.thumbnail_blob = image.thumbnail_blob,
                i.acquisition_parameters = image.acquisition_parameters,
                i.created_at = image.created_at
            WITH i, image
            MATCH (s:ImagingStudy {study_id: image.study_id})
            MERGE (s)-[:HAS_IMAGE]->(i)
            """

            # Process in smaller batches due to potential blob data
            batch_size = 50
            for i in range(0, len(self.image_nodes), batch_size):
                batch = self.image_nodes[i:i + batch_size]
                image_data = []

                for img in batch:
                    data = img.to_dict()
                    # Convert thumbnail blob to base64 for Neo4j
                    if img.thumbnail_blob:
                        import base64
                        data['thumbnail_blob'] = base64.b64encode(img.thumbnail_blob).decode('utf-8')
                    image_data.append(data)

                count = self.connector.batch_write(image_query, image_data, batch_size=batch_size)
                results['images'] += count

            logger.info(f"Created {results['images']} image nodes in Neo4j")

        self.processing_stats['neo4j_created'] = results['studies'] + results['images']
        return results

    def _index_to_elasticsearch(self) -> int:
        """Index metadata to Elasticsearch"""
        if not self.image_metadata or not self.es_indexer.es:
            return 0

        count = self.es_indexer.bulk_index_images(self.image_metadata)
        self.processing_stats['indexed'] = count
        return count

    def _log_summary(self, results: Dict[str, Any]) -> None:
        """Log processing summary"""
        logger.info("\n" + "="*60)
        logger.info("IMAGE PROCESSING SUMMARY")
        logger.info("="*60)
        logger.info(f"Total files found: {self.processing_stats['total_found']}")
        logger.info(f"Successfully processed: {self.processing_stats['processed']}")
        logger.info(f"Skipped: {self.processing_stats['skipped']}")
        logger.info(f"Failed: {self.processing_stats['failed']}")

        if self.es_indexer.es:
            logger.info(f"Indexed to Elasticsearch: {self.processing_stats['indexed']}")
        else:
            logger.info("Elasticsearch indexing: Skipped (not available)")

        logger.info(f"Created in Neo4j: {self.processing_stats['neo4j_created']}")
        logger.info(f"Total processing time: {results['processing_time']:.2f} seconds")

        if results['batch_stats']:
            logger.info("\nBatch Processing Statistics:")
            for batch in results['batch_stats']:
                logger.info(f"  Batch {batch['batch_num']}: {batch['processed']} items in {batch['time_seconds']:.2f}s")

        logger.info("="*60)

    def _infer_anatomical_region(self, description: str) -> str:
        """Infer anatomical region from description"""
        desc_lower = description.lower()

        if 'hippo' in desc_lower:
            return 'hippocampus'
        elif 'frontal' in desc_lower:
            return 'frontal_lobe'
        elif 'temporal' in desc_lower:
            return 'temporal_lobe'
        elif 'parietal' in desc_lower:
            return 'parietal_lobe'
        elif 'occipital' in desc_lower:
            return 'occipital_lobe'
        else:
            return 'whole_brain'

    def _infer_pet_tracer(self, description: str) -> Optional[str]:
        """Infer PET tracer from description"""
        desc_upper = description.upper()

        if 'FDG' in desc_upper:
            return 'FDG'
        elif 'AV45' in desc_upper or 'FLORBETAPIR' in desc_upper:
            return 'AV45'
        elif 'TAU' in desc_upper or 'AV1451' in desc_upper:
            return 'AV1451'
        elif 'PIB' in desc_upper:
            return 'PIB'

        return None

    def _extract_modality_from_study_id(self, study_id: str) -> str:
        """Extract modality from study ID"""
        if 'PET' in study_id.upper():
            return 'PET'
        elif 'MRI' in study_id.upper():
            return 'MRI'
        else:
            return 'UNKNOWN'


def execute_image_processing_external(neo4j_uri: str, neo4j_user: str, neo4j_password: str,
                                     base_path: str, storage_path: str,
                                     storage_config: Dict[str, Any] = None,
                                     max_workers: int = 8) -> Dict[str, Any]:
    """
    Main execution function for fixed image processing with Elasticsearch 8.x support

    Args:
        neo4j_uri: Neo4j connection URI
        neo4j_user: Username
        neo4j_password: Password
        base_path: Base path containing ADNI data
        storage_path: Path to converted images
        storage_config: Additional storage configuration
        max_workers: Maximum number of parallel workers

    Returns:
        Processing results
    """
    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        # Extract configuration
        config = storage_config or {}
        batch_size = config.get('batch_size', 100)
        es_host = config.get('es_host', 'localhost')
        es_port = config.get('es_port', 9200)

        processor = FixedImageProcessingPipeline(
            connector=connector,
            base_path=base_path,
            storage_path=storage_path,
            es_host=es_host,
            es_port=es_port,
            batch_size=batch_size,
            max_workers=max_workers
        )

        results = processor.execute()

        # Store processor for next steps
        results['processor'] = processor

        logger.info(f"✅ Processed {results['images_processed']} images")
        logger.info(f"   Created {results['studies_created']} studies")

        if results['images_indexed'] > 0:
            logger.info(f"   Indexed {results['images_indexed']} images to Elasticsearch")

        logger.info(f"   Total time: {results['processing_time']:.2f} seconds")

        return results

    except Exception as e:
        logger.error(f"Image processing failed: {e}")
        raise
    finally:
        connector.close()


if __name__ == "__main__":
    # Test execution
    results = execute_image_processing_external(
        neo4j_uri="bolt://localhost:7687",
        neo4j_user="neo4j",
        neo4j_password="your_password",
        base_path="inputs",
        storage_path="outputs/converted_images",
        storage_config={
            'batch_size': 100,
            'es_host': 'localhost',
            'es_port': 9200
        },
        max_workers=4
    )

    print(f"Results: {results}")