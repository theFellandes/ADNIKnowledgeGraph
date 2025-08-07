"""
Elasticsearch Search Indexer for ADNI Knowledge Graph
Fixed version with proper connection handling for Elasticsearch 8.x
"""

from elasticsearch import Elasticsearch, helpers
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class SearchIndexer:
    """
    Manages Elasticsearch indexing and searching for medical images
    """

    def __init__(self, host: str = 'localhost', port: int = 9200,
                 username: Optional[str] = None, password: Optional[str] = None):
        """
        Initialize Elasticsearch connection

        Args:
            host: Elasticsearch host
            port: Elasticsearch port
            username: Optional username for authentication
            password: Optional password for authentication
        """
        try:
            # Configure connection for Elasticsearch 8.x
            self.es = Elasticsearch(
                hosts=[f"http://{host}:{port}"],
                verify_certs=False,
                ssl_show_warn=False,
                request_timeout=30,
                max_retries=3,
                retry_on_timeout=True
            )

            # Test connection
            if not self.es.ping():
                raise ConnectionError("Cannot connect to Elasticsearch")

            # Get cluster info
            info = self.es.info()
            logger.info(f"✅ Connected to Elasticsearch {info['version']['number']}")

            # Create indices if they don't exist
            self._create_indices()

        except Exception as e:
            logger.error(f"Failed to connect to Elasticsearch: {e}")
            # Don't raise, just set es to None so the app can continue without search
            self.es = None

    def _create_indices(self) -> None:
        """Create required indices with appropriate mappings"""

        if not self.es:
            return

        # Medical images index
        medical_images_mapping = {
            "settings": {
                "number_of_shards": 2,
                "number_of_replicas": 1,
                "analysis": {
                    "analyzer": {
                        "medical_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "stop", "snowball"]
                        }
                    }
                }
            },
            "mappings": {
                "properties": {
                    "image_id": {"type": "keyword"},
                    "patient_id": {"type": "keyword"},
                    "study_id": {"type": "keyword"},
                    "visit_id": {"type": "keyword"},
                    "modality": {"type": "keyword"},
                    "series_description": {
                        "type": "text",
                        "analyzer": "standard",
                        "fields": {
                            "keyword": {"type": "keyword"}
                        }
                    },
                    "anatomical_region": {"type": "keyword"},
                    "pet_tracer": {"type": "keyword"},
                    "acquisition_date": {"type": "date"},
                    "storage_path": {"type": "keyword"},
                    "preview_path": {"type": "keyword"},
                    "thumbnail_path": {"type": "keyword"},
                    "quality_metrics": {
                        "properties": {
                            "snr": {"type": "float"},
                            "entropy": {"type": "float"},
                            "contrast": {"type": "float"},
                            "sharpness": {"type": "float"}
                        }
                    },
                    "dimensions": {"type": "integer"},
                    "voxel_spacing": {"type": "float"},
                    "file_size_mb": {"type": "float"},
                    "checksum": {"type": "keyword"},
                    "tags": {"type": "keyword"},
                    "notes": {"type": "text"},
                    "timestamp": {"type": "date"},
                    "processing_status": {"type": "keyword"},
                    "quality_verified": {"type": "boolean"}
                }
            }
        }

        # DICOM metadata index
        dicom_metadata_mapping = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 1
            },
            "mappings": {
                "properties": {
                    "image_id": {"type": "keyword"},
                    "patient_id": {"type": "keyword"},
                    "study_instance_uid": {"type": "keyword"},
                    "series_instance_uid": {"type": "keyword"},
                    "sop_instance_uid": {"type": "keyword"},
                    "modality": {"type": "keyword"},
                    "manufacturer": {"type": "keyword"},
                    "manufacturer_model": {"type": "keyword"},
                    "magnetic_field_strength": {"type": "float"},
                    "slice_thickness": {"type": "float"},
                    "pixel_spacing": {"type": "float"},
                    "window_center": {"type": "float"},
                    "window_width": {"type": "float"},
                    "study_date": {"type": "date", "format": "yyyyMMdd||strict_date_optional_time"},
                    "series_date": {"type": "date", "format": "yyyyMMdd||strict_date_optional_time"},
                    "protocol_name": {"type": "text"},
                    "sequence_name": {"type": "text"},
                    "raw_metadata": {"type": "object", "enabled": False}
                }
            }
        }

        # Processing logs index
        processing_logs_mapping = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0
            },
            "mappings": {
                "properties": {
                    "task_id": {"type": "keyword"},
                    "pipeline_step": {"type": "keyword"},
                    "status": {"type": "keyword"},
                    "message": {"type": "text"},
                    "error": {"type": "text"},
                    "duration_seconds": {"type": "float"},
                    "timestamp": {"type": "date"},
                    "metadata": {"type": "object", "enabled": False}
                }
            }
        }

        # Create indices if they don't exist
        indices = {
            "medical_images": medical_images_mapping,
            "dicom_metadata": dicom_metadata_mapping,
            "processing_logs": processing_logs_mapping
        }

        for index_name, mapping in indices.items():
            try:
                if not self.es.indices.exists(index=index_name):
                    self.es.indices.create(index=index_name, body=mapping)
                    logger.info(f"Created index: {index_name}")
            except Exception as e:
                logger.warning(f"Could not create index {index_name}: {e}")

    def index_document(self, index: str, document: Dict[str, Any],
                       doc_id: Optional[str] = None) -> bool:
        """
        Index a single document

        Args:
            index: Index name
            document: Document to index
            doc_id: Optional document ID

        Returns:
            Success status
        """
        if not self.es:
            return False

        try:
            result = self.es.index(
                index=index,
                id=doc_id,
                body=document,
                refresh=True  # Make immediately searchable
            )
            return result['result'] in ['created', 'updated']
        except Exception as e:
            logger.error(f"Error indexing document: {e}")
            return False

    def bulk_index(self, index: str, documents: List[Dict[str, Any]],
                   id_field: Optional[str] = None) -> Tuple[int, List[str]]:
        """
        Bulk index multiple documents

        Args:
            index: Index name
            documents: List of documents to index
            id_field: Field to use as document ID

        Returns:
            Tuple of (success_count, list of failed IDs)
        """
        if not self.es:
            return 0, []

        actions = []
        for doc in documents:
            action = {
                "_index": index,
                "_source": doc
            }
            if id_field and id_field in doc:
                action["_id"] = doc[id_field]
            actions.append(action)

        try:
            success, failed = helpers.bulk(
                self.es,
                actions,
                raise_on_error=False,
                raise_on_exception=False
            )

            failed_ids = []
            for item in failed:
                if 'index' in item and '_id' in item['index']:
                    failed_ids.append(item['index']['_id'])

            logger.info(f"Bulk indexed {success} documents, {len(failed_ids)} failed")
            return success, failed_ids

        except Exception as e:
            logger.error(f"Bulk indexing error: {e}")
            return 0, []

    def search_images(self, query: str, filters: Optional[Dict[str, Any]] = None,
                      size: int = 10, from_: int = 0) -> Dict[str, Any]:
        """
        Search medical images

        Args:
            query: Search query string
            filters: Optional filters (e.g., {'modality': 'MRI'})
            size: Number of results to return
            from_: Offset for pagination

        Returns:
            Search results
        """
        if not self.es:
            return {"total": 0, "hits": []}

        # Build query
        must_clauses = []

        # Add text search if query provided
        if query:
            must_clauses.append({
                "multi_match": {
                    "query": query,
                    "fields": [
                        "series_description^2",
                        "anatomical_region",
                        "notes",
                        "tags"
                    ],
                    "type": "best_fields",
                    "fuzziness": "AUTO"
                }
            })

        # Add filters
        filter_clauses = []
        if filters:
            for field, value in filters.items():
                if isinstance(value, list):
                    filter_clauses.append({"terms": {field: value}})
                else:
                    filter_clauses.append({"term": {field: value}})

        # Construct final query
        if must_clauses or filter_clauses:
            body = {
                "query": {
                    "bool": {
                        "must": must_clauses,
                        "filter": filter_clauses
                    }
                },
                "size": size,
                "from": from_,
                "sort": [
                    {"_score": {"order": "desc"}},
                    {"timestamp": {"order": "desc"}}
                ],
                "highlight": {
                    "fields": {
                        "series_description": {},
                        "notes": {}
                    }
                }
            }
        else:
            # Match all if no query or filters
            body = {
                "query": {"match_all": {}},
                "size": size,
                "from": from_,
                "sort": [{"timestamp": {"order": "desc"}}]
            }

        try:
            result = self.es.search(index="medical_images", body=body)

            return {
                "total": result["hits"]["total"]["value"],
                "hits": [
                    {
                        "id": hit["_id"],
                        "score": hit["_score"],
                        "source": hit["_source"],
                        "highlight": hit.get("highlight", {})
                    }
                    for hit in result["hits"]["hits"]
                ]
            }

        except Exception as e:
            logger.error(f"Search error: {e}")
            return {"total": 0, "hits": []}

    def get_image_path(self, image_id: str, resolution: str = 'diagnostic') -> Optional[str]:
        """
        Get image path from Elasticsearch index

        Args:
            image_id: Image identifier
            resolution: Resolution type (diagnostic, preview, thumbnail)

        Returns:
            File path or None
        """
        if not self.es:
            return None

        try:
            result = self.es.get(index="medical_images", id=image_id)
            source = result["_source"]

            path_field = f"{resolution}_path"
            return source.get(path_field)

        except Exception as e:
            logger.error(f"Error retrieving image path for {image_id}: {e}")
            return None

    def close(self) -> None:
        """Close Elasticsearch connection"""
        if self.es:
            try:
                self.es.close()
                logger.info("Elasticsearch connection closed")
            except Exception as e:
                logger.error(f"Error closing Elasticsearch: {e}")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()