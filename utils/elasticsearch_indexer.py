"""
Elasticsearch Indexer for Medical Images - Focused on Image Metadata Only
Neo4j remains the primary database, ES is used only for fast image retrieval
"""

from elasticsearch import Elasticsearch, helpers
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
import json

logger = logging.getLogger(__name__)


class SearchIndexer:
    """
    Elasticsearch indexer focused on medical image metadata
    Stores minimal data for fast image search and retrieval
    """

    def __init__(self, host: str = 'localhost', port: int = 9200):
        """Initialize Elasticsearch connection"""
        try:
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

            info = self.es.info()
            logger.info(f"✅ Connected to Elasticsearch {info['version']['number']}")

            # Create image index if not exists
            self._create_image_index()

        except Exception as e:
            logger.error(f"Failed to connect to Elasticsearch: {e}")
            self.es = None

    def _create_image_index(self) -> None:
        """Create optimized index for medical images"""
        if not self.es:
            return

        index_name = "medical_images"

        try:
            if not self.es.indices.exists(index=index_name):
                settings = {
                    "number_of_shards": 2,
                    "number_of_replicas": 1,
                    "analysis": {
                        "analyzer": {
                            "path_analyzer": {
                                "type": "custom",
                                "tokenizer": "path_hierarchy"
                            }
                        }
                    }
                }

                mappings = {
                    "properties": {
                        # Unique identifier
                        "image_hash": {"type": "keyword"},

                        # Patient and study identifiers
                        "patient_id": {"type": "keyword"},
                        "study_id": {"type": "keyword"},
                        "series_id": {"type": "keyword"},

                        # Image properties
                        "modality": {"type": "keyword"},
                        "study_date": {"type": "date", "format": "yyyyMMdd||yyyy-MM-dd||epoch_millis"},
                        "series_description": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},

                        # File paths
                        "dcm_path": {"type": "keyword", "fields": {"path": {"type": "text", "analyzer": "path_analyzer"}}},
                        "png_path": {"type": "keyword", "fields": {"path": {"type": "text", "analyzer": "path_analyzer"}}},
                        "thumbnail_path": {"type": "keyword"},

                        # Image dimensions
                        "original_resolution": {
                            "properties": {
                                "width": {"type": "integer"},
                                "height": {"type": "integer"}
                            }
                        },
                        "png_resolution": {
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

                        # Processing metadata
                        "conversion_date": {"type": "date"},
                        "indexed_date": {"type": "date"},
                        "naming_convention": {"type": "keyword"},

                        # Search optimization fields
                        "search_text": {"type": "text"},  # Concatenated searchable text
                        "tags": {"type": "keyword"}  # For filtering
                    }
                }

                self.es.indices.create(
                    index=index_name,
                    settings=settings,
                    mappings=mappings
                )
                logger.info(f"Created Elasticsearch index: {index_name}")

        except Exception as e:
            logger.warning(f"Could not create index {index_name}: {e}")

    def get_all_image_hashes(self) -> List[str]:
        """Get all existing image hashes for deduplication"""
        if not self.es:
            return []

        try:
            # Use scroll API for large result sets
            hashes = []

            # Initial search
            response = self.es.search(
                index="medical_images",
                body={
                    "query": {"match_all": {}},
                    "_source": ["image_hash"],
                    "size": 10000
                },
                scroll='2m'
            )

            scroll_id = response['_scroll_id']
            hits = response['hits']['hits']

            # Extract hashes
            for hit in hits:
                if 'image_hash' in hit['_source']:
                    hashes.append(hit['_source']['image_hash'])

            # Continue scrolling if more results
            while len(hits) > 0:
                response = self.es.scroll(scroll_id=scroll_id, scroll='2m')
                hits = response['hits']['hits']
                for hit in hits:
                    if 'image_hash' in hit['_source']:
                        hashes.append(hit['_source']['image_hash'])

            # Clear scroll
            self.es.clear_scroll(scroll_id=scroll_id)

            return hashes

        except Exception as e:
            logger.error(f"Error getting image hashes: {e}")
            return []

    def check_image_exists(self, image_hash: str) -> bool:
        """Check if an image already exists in the index"""
        if not self.es:
            return False

        try:
            response = self.es.exists(
                index="medical_images",
                id=image_hash
            )
            return response
        except Exception as e:
            logger.error(f"Error checking image existence: {e}")
            return False

    def index_image(self, image_data: Dict[str, Any]) -> bool:
        """Index a single image with deduplication check"""
        if not self.es:
            return False

        try:
            image_hash = image_data.get('image_hash')
            if not image_hash:
                logger.error("Image data missing image_hash")
                return False

            # Check if already exists
            if self.check_image_exists(image_hash):
                logger.debug(f"Image {image_hash} already exists, skipping")
                return True

            # Add search optimization fields
            search_text = f"{image_data.get('patient_id', '')} {image_data.get('modality', '')} {image_data.get('series_description', '')}"
            image_data['search_text'] = search_text

            # Index the document
            response = self.es.index(
                index="medical_images",
                id=image_hash,
                document=image_data,
                refresh=False  # Don't refresh immediately for better performance
            )

            return response['result'] in ['created', 'updated']

        except Exception as e:
            logger.error(f"Error indexing image {image_data.get('image_hash', 'unknown')}: {e}")
            return False

    def _validate_date_format(self, date_str: str) -> Optional[str]:
        """Validate and format date string for Elasticsearch"""
        if not date_str:
            return None

        # Try to parse common DICOM date formats
        date_formats = [
            '%Y%m%d',  # DICOM format: YYYYMMDD
            '%Y-%m-%d',  # ISO format
            '%Y/%m/%d'
        ]

        for fmt in date_formats:
            try:
                parsed_date = datetime.strptime(str(date_str)[:10], fmt)
                # Return in ISO format
                return parsed_date.strftime('%Y-%m-%d')
            except:
                continue

        # If no format works, return None
        logger.warning(f"Could not parse date: {date_str}")
        return None

    def bulk_index_images(self, images: List[Dict[str, Any]]) -> Tuple[int, List[str]]:
        """Bulk index images with deduplication"""
        if not self.es:
            return 0, []

        # Get existing hashes for deduplication
        existing_hashes = set(self.get_all_image_hashes())

        actions = []
        skipped = []

        for img_data in images:
            image_hash = img_data.get('image_hash')
            if not image_hash:
                continue

            # Skip if already exists
            if image_hash in existing_hashes:
                skipped.append(image_hash)
                continue

            # Add search optimization fields
            search_text = f"{img_data.get('patient_id', '')} {img_data.get('modality', '')} {img_data.get('series_description', '')}"
            img_data['search_text'] = search_text

            # Validate and format date fields
            if 'study_date' in img_data:
                validated_date = self._validate_date_format(img_data['study_date'])
                if validated_date:
                    img_data['study_date'] = validated_date
                else:
                    # Remove invalid date
                    del img_data['study_date']

            if 'conversion_date' in img_data and not isinstance(img_data['conversion_date'], str):
                img_data['conversion_date'] = datetime.now().isoformat()

            # Ensure indexed_date is present
            if 'indexed_date' not in img_data:
                img_data['indexed_date'] = datetime.now().isoformat()

            # Prepare bulk action
            actions.append({
                "_index": "medical_images",
                "_id": image_hash,
                "_source": img_data
            })

        if not actions:
            logger.info(f"All {len(images)} images already exist, skipping bulk index")
            return 0, []

        try:
            # Perform bulk indexing
            success_count = 0
            failed_items = []

            for success, info in helpers.streaming_bulk(
                self.es,
                actions,
                raise_on_error=False,
                raise_on_exception=False,
                refresh=True
            ):
                if not success:
                    failed_items.append(info)
                else:
                    success_count += 1

            failed_ids = []
            if failed_items:
                for item in failed_items:
                    # Extract error details
                    if 'index' in item:
                        error_detail = item['index'].get('error', {})
                        doc_id = item['index'].get('_id', 'unknown')
                        error_type = error_detail.get('type', 'unknown')
                        error_reason = error_detail.get('reason', 'unknown')

                        logger.error(f"Failed to index {doc_id}: {error_type} - {error_reason}")
                        failed_ids.append(doc_id)

            logger.info(f"Bulk indexed {success_count} images, skipped {len(skipped)}, failed {len(failed_ids)}")

            return success_count, failed_ids

        except Exception as e:
            logger.error(f"Bulk indexing error: {e}")
            return 0, [img.get('image_hash', '') for img in images]

    def search_images(self, query: str = "", filters: Optional[Dict[str, Any]] = None,
                     size: int = 100, from_: int = 0) -> Dict[str, Any]:
        """Search for images with filters"""
        if not self.es:
            return {"total": 0, "hits": []}

        # Build query
        must_clauses = []

        # Add text search if query provided
        if query:
            must_clauses.append({
                "multi_match": {
                    "query": query,
                    "fields": ["patient_id^3", "series_description^2", "search_text"],
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
                elif isinstance(value, dict) and 'range' in value:
                    filter_clauses.append({"range": {field: value['range']}})
                else:
                    filter_clauses.append({"term": {field: value}})

        # Construct query body
        if must_clauses or filter_clauses:
            body = {
                "query": {
                    "bool": {
                        "must": must_clauses if must_clauses else {"match_all": {}},
                        "filter": filter_clauses
                    }
                },
                "size": size,
                "from": from_,
                "sort": [
                    {"study_date": {"order": "desc", "missing": "_last"}},
                    {"_score": {"order": "desc"}}
                ]
            }
        else:
            body = {
                "query": {"match_all": {}},
                "size": size,
                "from": from_,
                "sort": [{"indexed_date": {"order": "desc"}}]
            }

        try:
            result = self.es.search(index="medical_images", body=body)

            return {
                "total": result["hits"]["total"]["value"],
                "hits": [
                    {
                        "id": hit["_id"],
                        "score": hit["_score"],
                        "source": hit["_source"]
                    }
                    for hit in result["hits"]["hits"]
                ]
            }

        except Exception as e:
            logger.error(f"Search error: {e}")
            return {"total": 0, "hits": []}

    def get_patient_images(self, patient_id: str, modality: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all images for a specific patient"""
        filters = {"patient_id": patient_id}
        if modality:
            filters["modality"] = modality

        result = self.search_images("", filters=filters, size=10000)
        return [hit["source"] for hit in result["hits"]]

    def get_image_by_hash(self, image_hash: str) -> Optional[Dict[str, Any]]:
        """Get a specific image by its hash"""
        if not self.es:
            return None

        try:
            response = self.es.get(
                index="medical_images",
                id=image_hash
            )
            return response["_source"]
        except Exception as e:
            logger.error(f"Error getting image {image_hash}: {e}")
            return None

    def delete_image(self, image_hash: str) -> bool:
        """Delete an image from the index"""
        if not self.es:
            return False

        try:
            response = self.es.delete(
                index="medical_images",
                id=image_hash,
                refresh=True
            )
            return response['result'] == 'deleted'
        except Exception as e:
            logger.error(f"Error deleting image {image_hash}: {e}")
            return False

    def update_image_metadata(self, image_hash: str, updates: Dict[str, Any]) -> bool:
        """Update image metadata"""
        if not self.es:
            return False

        try:
            response = self.es.update(
                index="medical_images",
                id=image_hash,
                body={"doc": updates},
                refresh=True
            )
            return response['result'] in ['updated', 'noop']
        except Exception as e:
            logger.error(f"Error updating image {image_hash}: {e}")
            return False

    def get_index_stats(self) -> Dict[str, Any]:
        """Get statistics about the image index"""
        if not self.es:
            return {}

        try:
            stats = self.es.indices.stats(index="medical_images")

            return {
                "total_images": stats["indices"]["medical_images"]["total"]["docs"]["count"],
                "index_size_bytes": stats["indices"]["medical_images"]["total"]["store"]["size_in_bytes"],
                "index_size_mb": stats["indices"]["medical_images"]["total"]["store"]["size_in_bytes"] / (1024 * 1024)
            }
        except Exception as e:
            logger.error(f"Error getting index stats: {e}")
            return {}

    def refresh_index(self) -> bool:
        """Refresh the index to make recent changes searchable"""
        if not self.es:
            return False

        try:
            self.es.indices.refresh(index="medical_images")
            return True
        except Exception as e:
            logger.error(f"Error refreshing index: {e}")
            return False

    def close(self) -> None:
        """Close Elasticsearch connection"""
        if self.es:
            try:
                self.es.close()
                logger.info("Elasticsearch connection closed")
            except Exception as e:
                logger.error(f"Error closing Elasticsearch: {e}")