"""
Multi-Modal Search Engine for ADNI Knowledge Graph
Combines Neo4j graph queries, Elasticsearch text search, and Redis caching
"""

import logging
import hashlib
import json
import time
from typing import Dict, List, Any, Optional, Union, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum

from utils.elasticsearch_indexer import SearchIndexer
from utils.redis_cacher import EnhancedCacheManager
from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


class SearchType(Enum):
    """Types of searches supported by the engine"""
    PATIENT = "patient"
    IMAGE = "image"
    BIOMARKER = "biomarker"
    FAMILY = "family"
    COMBINED = "combined"


@dataclass
class SearchCriteria:
    """Search criteria for multi-modal searches"""
    query_text: Optional[str] = None
    patient_id: Optional[str] = None
    age_range: Optional[Tuple[int, int]] = None
    gender: Optional[str] = None
    diagnosis: Optional[str] = None
    modality: Optional[str] = None
    biomarker_name: Optional[str] = None
    biomarker_range: Optional[Tuple[float, float]] = None
    date_range: Optional[Tuple[datetime, datetime]] = None
    family_ad_history: Optional[bool] = None
    apoe_genotype: Optional[str] = None
    limit: int = 50
    offset: int = 0
    sort_by: Optional[str] = None
    sort_order: str = "desc"


@dataclass
class SearchResult:
    """Individual search result"""
    id: str
    type: str
    score: float
    data: Dict[str, Any]
    highlights: Dict[str, List[str]] = None
    cached: bool = False


@dataclass
class SearchResults:
    """Complete search results with metadata"""
    results: List[SearchResult]
    total_count: int
    search_time_ms: float
    cached: bool = False
    facets: Dict[str, Any] = None
    suggestions: List[str] = None


class MultiModalSearchEngine:
    """
    Multi-modal search engine combining Neo4j graph queries, Elasticsearch text search,
    and Redis caching for comprehensive ADNI Knowledge Graph searches
    """

    def __init__(self, 
                 elasticsearch_client: SearchIndexer,
                 redis_client: EnhancedCacheManager,
                 neo4j_connector: Neo4jConnector,
                 cache_ttl: int = 3600):
        """
        Initialize the multi-modal search engine

        Args:
            elasticsearch_client: Elasticsearch indexer instance
            redis_client: Redis cache manager instance
            neo4j_connector: Neo4j database connector
            cache_ttl: Cache time-to-live in seconds
        """
        self.es = elasticsearch_client
        self.redis = redis_client
        self.neo4j = neo4j_connector
        self.cache_ttl = cache_ttl
        
        logger.info("MultiModalSearchEngine initialized")

    def search_patients(self, criteria: SearchCriteria) -> SearchResults:
        """
        Search for patients using combined Neo4j and Elasticsearch queries

        Args:
            criteria: Search criteria

        Returns:
            Search results with patient data
        """
        start_time = time.time()
        
        # Generate cache key
        cache_key = self._generate_cache_key("patient_search", criteria)
        
        # Check cache first
        cached_results = self.redis.get_search_results(cache_key)
        if cached_results:
            cached_results.cached = True
            return cached_results
        
        try:
            # Build Elasticsearch query for patient search
            es_query = self._build_patient_elasticsearch_query(criteria)
            
            # Execute Elasticsearch search
            es_results = self.es.search_patients(
                query=criteria.query_text or "",
                filters=self._extract_patient_filters(criteria),
                size=criteria.limit,
                from_=criteria.offset
            )
            
            # Enhance results with Neo4j graph data
            enhanced_results = []
            for hit in es_results.get("hits", []):
                patient_data = hit["source"]
                patient_id = patient_data.get("patient_id")
                
                # Get additional graph data from Neo4j
                graph_data = self._get_patient_graph_data(patient_id)
                
                # Merge data
                enhanced_data = {**patient_data, **graph_data}
                
                enhanced_results.append(SearchResult(
                    id=patient_id,
                    type="patient",
                    score=hit["score"],
                    data=enhanced_data,
                    highlights=hit.get("highlight", {}),
                    cached=False
                ))
            
            # Create final results
            results = SearchResults(
                results=enhanced_results,
                total_count=es_results.get("total", 0),
                search_time_ms=(time.time() - start_time) * 1000,
                cached=False,
                facets=self._generate_patient_facets(es_results),
                suggestions=self._generate_search_suggestions(criteria.query_text)
            )
            
            # Cache results
            self.redis.cache_search_results(cache_key, results, ttl=self.cache_ttl)
            
            return results
            
        except Exception as e:
            logger.error(f"Patient search failed: {e}")
            return SearchResults(
                results=[],
                total_count=0,
                search_time_ms=(time.time() - start_time) * 1000,
                cached=False
            )

    def search_images(self, criteria: SearchCriteria) -> SearchResults:
        """
        Search for medical images with metadata filtering and caching

        Args:
            criteria: Search criteria

        Returns:
            Search results with image data
        """
        start_time = time.time()
        
        # Generate cache key
        cache_key = self._generate_cache_key("image_search", criteria)
        
        # Check cache first
        cached_results = self.redis.get_search_results(cache_key)
        if cached_results:
            cached_results.cached = True
            return cached_results
        
        try:
            # Build image search filters
            filters = self._extract_image_filters(criteria)
            
            # Execute Elasticsearch search
            es_results = self.es.search_images(
                query=criteria.query_text or "",
                filters=filters,
                size=criteria.limit,
                from_=criteria.offset
            )
            
            # Enhance results with cached thumbnails and metadata
            enhanced_results = []
            for hit in es_results.get("hits", []):
                image_data = hit["source"]
                image_hash = image_data.get("image_hash")
                
                # Get cached thumbnail and metadata
                thumbnail_data = self.redis.get_thumbnail(image_hash)
                cached_metadata = self.redis.get_image_metadata(image_hash)
                
                # Enhance with cached data
                if cached_metadata:
                    image_data.update(cached_metadata)
                
                if thumbnail_data:
                    image_data["thumbnail_cached"] = True
                    image_data["thumbnail_size"] = len(thumbnail_data)
                
                enhanced_results.append(SearchResult(
                    id=image_hash,
                    type="image",
                    score=hit["score"],
                    data=image_data,
                    highlights=hit.get("highlight", {}),
                    cached=thumbnail_data is not None
                ))
            
            # Create final results
            results = SearchResults(
                results=enhanced_results,
                total_count=es_results.get("total", 0),
                search_time_ms=(time.time() - start_time) * 1000,
                cached=False,
                facets=self._generate_image_facets(es_results),
                suggestions=self._generate_search_suggestions(criteria.query_text)
            )
            
            # Cache results
            self.redis.cache_search_results(cache_key, results, ttl=self.cache_ttl)
            
            return results
            
        except Exception as e:
            logger.error(f"Image search failed: {e}")
            return SearchResults(
                results=[],
                total_count=0,
                search_time_ms=(time.time() - start_time) * 1000,
                cached=False
            )

    def search_biomarkers(self, criteria: SearchCriteria) -> SearchResults:
        """
        Search biomarker data with range queries and temporal filtering

        Args:
            criteria: Search criteria

        Returns:
            Search results with biomarker data
        """
        start_time = time.time()
        
        # Generate cache key
        cache_key = self._generate_cache_key("biomarker_search", criteria)
        
        # Check cache first
        cached_results = self.redis.get_search_results(cache_key)
        if cached_results:
            cached_results.cached = True
            return cached_results
        
        try:
            # Build biomarker search query
            filters = self._extract_biomarker_filters(criteria)
            
            # Execute Elasticsearch search on biomarkers index
            es_results = self.es.search_biomarkers(
                query=criteria.query_text or "",
                filters=filters,
                size=criteria.limit,
                from_=criteria.offset
            )
            
            # Enhance results with cached patient data
            enhanced_results = []
            for hit in es_results.get("hits", []):
                biomarker_data = hit["source"]
                patient_id = biomarker_data.get("patient_id")
                
                # Get cached patient summary
                patient_summary = self.redis.get_patient_summary(patient_id)
                if patient_summary:
                    biomarker_data["patient_info"] = patient_summary
                
                enhanced_results.append(SearchResult(
                    id=biomarker_data.get("measurement_id"),
                    type="biomarker",
                    score=hit["score"],
                    data=biomarker_data,
                    highlights=hit.get("highlight", {}),
                    cached=patient_summary is not None
                ))
            
            # Create final results
            results = SearchResults(
                results=enhanced_results,
                total_count=es_results.get("total", 0),
                search_time_ms=(time.time() - start_time) * 1000,
                cached=False,
                facets=self._generate_biomarker_facets(es_results),
                suggestions=self._generate_search_suggestions(criteria.query_text)
            )
            
            # Cache results
            self.redis.cache_search_results(cache_key, results, ttl=self.cache_ttl)
            
            return results
            
        except Exception as e:
            logger.error(f"Biomarker search failed: {e}")
            return SearchResults(
                results=[],
                total_count=0,
                search_time_ms=(time.time() - start_time) * 1000,
                cached=False
            )

    def search_family_history(self, criteria: SearchCriteria) -> SearchResults:
        """
        Search family history data with relationship traversal

        Args:
            criteria: Search criteria

        Returns:
            Search results with family history data
        """
        start_time = time.time()
        
        # Generate cache key
        cache_key = self._generate_cache_key("family_search", criteria)
        
        # Check cache first
        cached_results = self.redis.get_search_results(cache_key)
        if cached_results:
            cached_results.cached = True
            return cached_results
        
        try:
            # For family searches, use Neo4j primarily with Elasticsearch enhancement
            if criteria.patient_id:
                # Get family tree from Neo4j
                family_tree = self.neo4j.get_family_tree(criteria.patient_id)
                
                # Enhance with Elasticsearch data
                enhanced_results = []
                for member_id, member_data in family_tree.get("family_members", {}).items():
                    # Get additional data from Elasticsearch if available
                    es_data = self._get_family_member_es_data(member_id)
                    if es_data:
                        member_data.update(es_data)
                    
                    enhanced_results.append(SearchResult(
                        id=member_id,
                        type="family_member",
                        score=1.0,  # Neo4j doesn't provide relevance scores
                        data=member_data,
                        cached=False
                    ))
                
                results = SearchResults(
                    results=enhanced_results,
                    total_count=len(enhanced_results),
                    search_time_ms=(time.time() - start_time) * 1000,
                    cached=False
                )
            else:
                # Use Elasticsearch for broader family history search
                filters = self._extract_family_filters(criteria)
                
                es_results = self.es.search_family_history(
                    query=criteria.query_text or "",
                    filters=filters,
                    size=criteria.limit,
                    from_=criteria.offset
                )
                
                enhanced_results = []
                for hit in es_results.get("hits", []):
                    family_data = hit["source"]
                    
                    enhanced_results.append(SearchResult(
                        id=family_data.get("family_member_id"),
                        type="family_member",
                        score=hit["score"],
                        data=family_data,
                        highlights=hit.get("highlight", {}),
                        cached=False
                    ))
                
                results = SearchResults(
                    results=enhanced_results,
                    total_count=es_results.get("total", 0),
                    search_time_ms=(time.time() - start_time) * 1000,
                    cached=False
                )
            
            # Cache results
            self.redis.cache_search_results(cache_key, results, ttl=self.cache_ttl)
            
            return results
            
        except Exception as e:
            logger.error(f"Family history search failed: {e}")
            return SearchResults(
                results=[],
                total_count=0,
                search_time_ms=(time.time() - start_time) * 1000,
                cached=False
            )

    def combined_search(self, criteria: SearchCriteria) -> Dict[str, SearchResults]:
        """
        Perform combined search across all data types with result aggregation and ranking

        Args:
            criteria: Search criteria

        Returns:
            Dictionary with search results for each data type
        """
        start_time = time.time()
        
        # Generate cache key for combined search
        cache_key = self._generate_cache_key("combined_search", criteria)
        
        # Check cache first
        cached_results = self.redis.get(cache_key)
        if cached_results:
            # Update cached flag for all results
            for search_type, results in cached_results.items():
                if isinstance(results, SearchResults):
                    results.cached = True
            return cached_results
        
        try:
            # Execute searches in parallel (simplified sequential implementation)
            results = {}
            
            # Patient search
            patient_criteria = SearchCriteria(**asdict(criteria))
            patient_criteria.limit = min(criteria.limit, 20)  # Limit for combined search
            results["patients"] = self.search_patients(patient_criteria)
            
            # Image search
            image_criteria = SearchCriteria(**asdict(criteria))
            image_criteria.limit = min(criteria.limit, 20)
            results["images"] = self.search_images(image_criteria)
            
            # Biomarker search
            biomarker_criteria = SearchCriteria(**asdict(criteria))
            biomarker_criteria.limit = min(criteria.limit, 20)
            results["biomarkers"] = self.search_biomarkers(biomarker_criteria)
            
            # Family history search
            family_criteria = SearchCriteria(**asdict(criteria))
            family_criteria.limit = min(criteria.limit, 20)
            results["family_history"] = self.search_family_history(family_criteria)
            
            # Add aggregated results
            results["aggregated"] = self._aggregate_search_results(results, criteria)
            
            # Cache combined results
            self.redis.set(cache_key, results, expire=self.cache_ttl)
            
            logger.info(f"Combined search completed in {(time.time() - start_time) * 1000:.2f}ms")
            return results
            
        except Exception as e:
            logger.error(f"Combined search failed: {e}")
            return {
                "patients": SearchResults([], 0, 0),
                "images": SearchResults([], 0, 0),
                "biomarkers": SearchResults([], 0, 0),
                "family_history": SearchResults([], 0, 0),
                "aggregated": SearchResults([], 0, 0)
            }

    def get_search_suggestions(self, query: str, search_type: SearchType = SearchType.COMBINED) -> List[str]:
        """
        Get search suggestions based on query and search type

        Args:
            query: Partial query string
            search_type: Type of search for context-specific suggestions

        Returns:
            List of suggested search terms
        """
        try:
            suggestions = []
            
            # Cache key for suggestions
            cache_key = f"suggestions:{search_type.value}:{hashlib.md5(query.encode()).hexdigest()}"
            cached_suggestions = self.redis.get(cache_key)
            if cached_suggestions:
                return cached_suggestions
            
            # Generate suggestions based on search type
            if search_type in [SearchType.PATIENT, SearchType.COMBINED]:
                suggestions.extend(self._get_patient_suggestions(query))
            
            if search_type in [SearchType.IMAGE, SearchType.COMBINED]:
                suggestions.extend(self._get_image_suggestions(query))
            
            if search_type in [SearchType.BIOMARKER, SearchType.COMBINED]:
                suggestions.extend(self._get_biomarker_suggestions(query))
            
            # Remove duplicates and limit
            suggestions = list(set(suggestions))[:10]
            
            # Cache suggestions
            self.redis.set(cache_key, suggestions, expire=3600)  # 1 hour cache
            
            return suggestions
            
        except Exception as e:
            logger.error(f"Failed to get search suggestions: {e}")
            return []

    # Private helper methods

    def _generate_cache_key(self, search_type: str, criteria: SearchCriteria) -> str:
        """Generate cache key for search criteria"""
        criteria_dict = asdict(criteria)
        # Remove None values and sort for consistent hashing
        filtered_dict = {k: v for k, v in criteria_dict.items() if v is not None}
        criteria_str = json.dumps(filtered_dict, sort_keys=True, default=str)
        hash_key = hashlib.md5(criteria_str.encode()).hexdigest()
        return f"search:{search_type}:{hash_key}"

    def _build_patient_elasticsearch_query(self, criteria: SearchCriteria) -> Dict[str, Any]:
        """Build Elasticsearch query for patient search"""
        query = {"bool": {"must": [], "filter": []}}
        
        # Text search
        if criteria.query_text:
            query["bool"]["must"].append({
                "multi_match": {
                    "query": criteria.query_text,
                    "fields": ["clinical_notes^2", "tags", "demographics.*"],
                    "type": "best_fields",
                    "fuzziness": "AUTO"
                }
            })
        
        # Add filters
        filters = self._extract_patient_filters(criteria)
        for field, value in filters.items():
            if isinstance(value, list):
                query["bool"]["filter"].append({"terms": {field: value}})
            elif isinstance(value, dict) and "gte" in value:
                query["bool"]["filter"].append({"range": {field: value}})
            else:
                query["bool"]["filter"].append({"term": {field: value}})
        
        return query

    def _extract_patient_filters(self, criteria: SearchCriteria) -> Dict[str, Any]:
        """Extract patient-specific filters from search criteria"""
        filters = {}
        
        if criteria.patient_id:
            filters["patient_id"] = criteria.patient_id
        
        if criteria.gender:
            filters["demographics.gender"] = criteria.gender
        
        if criteria.diagnosis:
            filters["diagnoses.diagnosis"] = criteria.diagnosis
        
        if criteria.age_range:
            filters["demographics.age"] = {
                "gte": criteria.age_range[0],
                "lte": criteria.age_range[1]
            }
        
        if criteria.apoe_genotype:
            filters["apoe_genotype"] = criteria.apoe_genotype
        
        if criteria.family_ad_history is not None:
            filters["family_history.has_family_ad"] = criteria.family_ad_history
        
        return filters

    def _extract_image_filters(self, criteria: SearchCriteria) -> Dict[str, Any]:
        """Extract image-specific filters from search criteria"""
        filters = {}
        
        if criteria.patient_id:
            filters["patient_id"] = criteria.patient_id
        
        if criteria.modality:
            filters["modality"] = criteria.modality
        
        if criteria.date_range:
            filters["acquisition_date"] = {
                "gte": criteria.date_range[0].isoformat(),
                "lte": criteria.date_range[1].isoformat()
            }
        
        return filters

    def _extract_biomarker_filters(self, criteria: SearchCriteria) -> Dict[str, Any]:
        """Extract biomarker-specific filters from search criteria"""
        filters = {}
        
        if criteria.patient_id:
            filters["patient_id"] = criteria.patient_id
        
        if criteria.biomarker_name:
            filters["biomarker_name"] = criteria.biomarker_name
        
        if criteria.biomarker_range:
            filters["value"] = {
                "gte": criteria.biomarker_range[0],
                "lte": criteria.biomarker_range[1]
            }
        
        if criteria.date_range:
            filters["measurement_date"] = {
                "gte": criteria.date_range[0].isoformat(),
                "lte": criteria.date_range[1].isoformat()
            }
        
        return filters

    def _extract_family_filters(self, criteria: SearchCriteria) -> Dict[str, Any]:
        """Extract family history-specific filters from search criteria"""
        filters = {}
        
        if criteria.patient_id:
            filters["patient_id"] = criteria.patient_id
        
        if criteria.family_ad_history is not None:
            filters["ad_status"] = "affected" if criteria.family_ad_history else "unaffected"
        
        return filters

    def _get_patient_graph_data(self, patient_id: str) -> Dict[str, Any]:
        """Get additional patient data from Neo4j graph"""
        try:
            # Get cached patient data first
            cached_data = self.redis.get_patient_summary(patient_id)
            if cached_data:
                return cached_data
            
            # Query Neo4j for graph-specific data
            query = """
            MATCH (p:Patient {ptid: $patient_id})
            OPTIONAL MATCH (p)-[:HAS_VISIT]->(v:Visit)
            OPTIONAL MATCH (p)-[:HAS_IMAGE]->(img:ImageNode)
            OPTIONAL MATCH (p)-[:HAS_FAMILY_MEMBER]->(fm:FamilyMember)
            RETURN p,
                   count(DISTINCT v) as visit_count,
                   count(DISTINCT img) as image_count,
                   count(DISTINCT fm) as family_member_count,
                   collect(DISTINCT img.modality) as modalities
            """
            
            result = self.neo4j.run_query(query, {"patient_id": patient_id})
            if result:
                graph_data = {
                    "visit_count": result[0].get("visit_count", 0),
                    "image_count": result[0].get("image_count", 0),
                    "family_member_count": result[0].get("family_member_count", 0),
                    "available_modalities": result[0].get("modalities", [])
                }
                
                # Cache the graph data
                self.redis.cache_patient_summary(patient_id, graph_data)
                return graph_data
            
            return {}
            
        except Exception as e:
            logger.error(f"Failed to get patient graph data for {patient_id}: {e}")
            return {}

    def _get_family_member_es_data(self, member_id: str) -> Optional[Dict[str, Any]]:
        """Get family member data from Elasticsearch"""
        try:
            es_results = self.es.search_family_history(
                query="",
                filters={"family_member_id": member_id},
                size=1
            )
            
            hits = es_results.get("hits", [])
            return hits[0]["source"] if hits else None
            
        except Exception as e:
            logger.error(f"Failed to get family member ES data for {member_id}: {e}")
            return None

    def _generate_patient_facets(self, es_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate facets for patient search results"""
        # This would typically use Elasticsearch aggregations
        # Simplified implementation
        return {
            "gender": {"male": 0, "female": 0},
            "diagnosis": {},
            "age_ranges": {}
        }

    def _generate_image_facets(self, es_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate facets for image search results"""
        return {
            "modality": {"MRI": 0, "PET": 0, "CT": 0},
            "anatomical_region": {},
            "quality_score": {}
        }

    def _generate_biomarker_facets(self, es_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate facets for biomarker search results"""
        return {
            "biomarker_name": {},
            "abnormal_flag": {"true": 0, "false": 0},
            "measurement_method": {}
        }

    def _generate_search_suggestions(self, query: Optional[str]) -> List[str]:
        """Generate search suggestions based on query"""
        if not query:
            return []
        
        # Simplified suggestion generation
        suggestions = []
        query_lower = query.lower()
        
        # Common medical terms
        medical_terms = [
            "alzheimer", "dementia", "cognitive", "memory", "mri", "pet", "amyloid",
            "tau", "apoe", "biomarker", "hippocampus", "cortex", "ventricle"
        ]
        
        for term in medical_terms:
            if query_lower in term or term.startswith(query_lower):
                suggestions.append(term)
        
        return suggestions[:5]

    def _aggregate_search_results(self, results: Dict[str, SearchResults], 
                                criteria: SearchCriteria) -> SearchResults:
        """Aggregate and rank results from multiple search types"""
        all_results = []
        
        # Combine results with type-specific scoring
        type_weights = {"patients": 1.0, "images": 0.8, "biomarkers": 0.6, "family_history": 0.4}
        
        for search_type, search_results in results.items():
            if search_type == "aggregated":
                continue
                
            weight = type_weights.get(search_type, 0.5)
            for result in search_results.results:
                result.score *= weight
                result.data["search_type"] = search_type
                all_results.append(result)
        
        # Sort by score
        all_results.sort(key=lambda x: x.score, reverse=True)
        
        # Limit results
        limited_results = all_results[:criteria.limit]
        
        return SearchResults(
            results=limited_results,
            total_count=len(all_results),
            search_time_ms=0,  # Already calculated in individual searches
            cached=False
        )

    def _get_patient_suggestions(self, query: str) -> List[str]:
        """Get patient-specific search suggestions"""
        return [f"{query} patient", f"{query} diagnosis", f"{query} demographics"]

    def _get_image_suggestions(self, query: str) -> List[str]:
        """Get image-specific search suggestions"""
        return [f"{query} MRI", f"{query} PET", f"{query} imaging"]

    def _get_biomarker_suggestions(self, query: str) -> List[str]:
        """Get biomarker-specific search suggestions"""
        return [f"{query} biomarker", f"{query} amyloid", f"{query} tau"]