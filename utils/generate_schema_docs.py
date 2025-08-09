#!/usr/bin/env python3
"""
Schema Documentation Generator Script
Generates comprehensive schema documentation for ADNI Knowledge Graph
"""

import os
import sys
import logging
from pathlib import Path

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.metadata_generator import MetadataGenerator

# Try to import optional dependencies
try:
    from utils.neo4j_connector import Neo4jConnector
except ImportError:
    Neo4jConnector = None
    logger.warning("Neo4j connector not available")

try:
    from utils.elasticsearch_indexer import SearchIndexer
except ImportError:
    SearchIndexer = None
    logger.warning("Elasticsearch indexer not available")


def main():
    """Generate schema documentation"""
    logger.info("Starting schema documentation generation...")
    
    try:
        # Initialize connectors (with error handling for missing services)
        neo4j_connector = None
        elasticsearch_indexer = None
        
        if Neo4jConnector:
            try:
                # Try to connect to Neo4j
                neo4j_connector = Neo4jConnector(
                    uri="bolt://localhost:7687",
                    user="neo4j",
                    password="password"
                )
                if not neo4j_connector.verify_connection():
                    logger.warning("Neo4j connection failed, proceeding without Neo4j data")
                    neo4j_connector = None
            except Exception as e:
                logger.warning(f"Could not connect to Neo4j: {e}")
        
        if SearchIndexer:
            try:
                # Try to connect to Elasticsearch
                elasticsearch_indexer = SearchIndexer(
                    host="localhost",
                    port=9200
                )
                if not elasticsearch_indexer.es:
                    logger.warning("Elasticsearch connection failed, proceeding without Elasticsearch data")
                    elasticsearch_indexer = None
            except Exception as e:
                logger.warning(f"Could not connect to Elasticsearch: {e}")
        
        # Initialize MetadataGenerator
        metadata_generator = MetadataGenerator(
            neo4j_connector=neo4j_connector,
            elasticsearch_indexer=elasticsearch_indexer,
            output_base_path="outputs"
        )
        
        # Generate schema documentation
        logger.info("Generating Neo4j schema documentation...")
        neo4j_schema = metadata_generator._extract_neo4j_schema()
        
        logger.info("Generating Elasticsearch schema documentation...")
        elasticsearch_schema = metadata_generator._extract_elasticsearch_schema()
        
        logger.info("Generating data model schema documentation...")
        data_model_schema = metadata_generator._extract_data_model_schema()
        
        logger.info("Generating relationship types documentation...")
        relationship_types = metadata_generator._extract_relationship_types()
        
        # Create comprehensive schema documentation
        schema_documentation = {
            "neo4j_schema": neo4j_schema,
            "elasticsearch_schema": elasticsearch_schema,
            "data_model_schema": data_model_schema,
            "relationship_types": relationship_types
        }
        
        # Generate complete schema documentation
        complete_schema = metadata_generator.generate_schema_documentation()
        
        # Generate individual documentation files
        generate_individual_docs(metadata_generator, schema_documentation)
        
        logger.info("Schema documentation generation completed successfully!")
        
        # Print summary
        print_summary(complete_schema)
        
    except Exception as e:
        logger.error(f"Error generating schema documentation: {e}")
        sys.exit(1)
    
    finally:
        # Clean up connections
        if neo4j_connector:
            neo4j_connector.close()


def generate_individual_docs(metadata_generator, schema_docs):
    """Generate individual documentation files"""
    
    # Neo4j schema documentation
    if "error" not in schema_docs["neo4j_schema"]:
        neo4j_doc = create_neo4j_documentation(schema_docs["neo4j_schema"])
        neo4j_file = os.path.join(metadata_generator.metadata_path, "schema_documentation", "neo4j_schema.md")
        with open(neo4j_file, 'w') as f:
            f.write(neo4j_doc)
        logger.info(f"Neo4j schema documentation saved to {neo4j_file}")
    
    # Elasticsearch schema documentation
    if "error" not in schema_docs["elasticsearch_schema"]:
        es_doc = create_elasticsearch_documentation(schema_docs["elasticsearch_schema"])
        es_file = os.path.join(metadata_generator.metadata_path, "schema_documentation", "elasticsearch_schema.md")
        with open(es_file, 'w') as f:
            f.write(es_doc)
        logger.info(f"Elasticsearch schema documentation saved to {es_file}")
    
    # Data model documentation
    if "error" not in schema_docs["data_model_schema"]:
        model_doc = create_data_model_documentation(schema_docs["data_model_schema"])
        model_file = os.path.join(metadata_generator.metadata_path, "schema_documentation", "data_models.md")
        with open(model_file, 'w') as f:
            f.write(model_doc)
        logger.info(f"Data model documentation saved to {model_file}")
    
    # API documentation
    api_doc = create_api_documentation()
    api_file = os.path.join(metadata_generator.metadata_path, "schema_documentation", "api_documentation.md")
    with open(api_file, 'w') as f:
        f.write(api_doc)
    logger.info(f"API documentation saved to {api_file}")


def create_neo4j_documentation(neo4j_schema):
    """Create Neo4j schema documentation in Markdown format"""
    
    doc = """# Neo4j Schema Documentation

## Overview
This document describes the Neo4j graph database schema for the ADNI Knowledge Graph Enhancement project.

"""
    
    # Node labels
    if "node_labels" in neo4j_schema:
        doc += "## Node Labels\n\n"
        for label in neo4j_schema["node_labels"]:
            count = neo4j_schema.get("node_counts", {}).get(label, 0)
            doc += f"- **{label}**: {count:,} nodes\n"
        doc += "\n"
    
    # Relationship types
    if "relationship_types" in neo4j_schema:
        doc += "## Relationship Types\n\n"
        for rel_type in neo4j_schema["relationship_types"]:
            count = neo4j_schema.get("relationship_counts", {}).get(rel_type, 0)
            doc += f"- **{rel_type}**: {count:,} relationships\n"
        doc += "\n"
    
    # Constraints
    if "constraints" in neo4j_schema and neo4j_schema["constraints"]:
        doc += "## Constraints\n\n"
        for constraint in neo4j_schema["constraints"]:
            doc += f"- **{constraint.get('name', 'Unknown')}**: {constraint.get('type', 'Unknown')} on {constraint.get('labels', [])} properties {constraint.get('properties', [])}\n"
        doc += "\n"
    
    # Indexes
    if "indexes" in neo4j_schema and neo4j_schema["indexes"]:
        doc += "## Indexes\n\n"
        for index in neo4j_schema["indexes"]:
            doc += f"- **{index.get('name', 'Unknown')}**: {index.get('type', 'Unknown')} on {index.get('labels', [])} properties {index.get('properties', [])}\n"
        doc += "\n"
    
    # Statistics
    doc += "## Database Statistics\n\n"
    doc += f"- **Total Nodes**: {neo4j_schema.get('total_nodes', 0):,}\n"
    doc += f"- **Total Relationships**: {neo4j_schema.get('total_relationships', 0):,}\n"
    doc += f"- **Property Keys**: {len(neo4j_schema.get('property_keys', []))}\n"
    
    return doc


def create_elasticsearch_documentation(es_schema):
    """Create Elasticsearch schema documentation in Markdown format"""
    
    doc = """# Elasticsearch Schema Documentation

## Overview
This document describes the Elasticsearch indices and mappings for the ADNI Knowledge Graph Enhancement project.

"""
    
    if "indices" in es_schema:
        doc += "## Indices\n\n"
        
        for index_name, index_info in es_schema["indices"].items():
            if "error" in index_info:
                doc += f"### {index_name}\n**Error**: {index_info['error']}\n\n"
                continue
                
            doc += f"### {index_name}\n\n"
            doc += f"- **Document Count**: {index_info.get('document_count', 0):,}\n"
            
            # Mappings
            if "mappings" in index_info and "properties" in index_info["mappings"]:
                doc += "- **Fields**:\n"
                for field_name, field_info in index_info["mappings"]["properties"].items():
                    field_type = field_info.get("type", "unknown")
                    doc += f"  - `{field_name}`: {field_type}\n"
            
            doc += "\n"
    
    # Statistics
    doc += "## Index Statistics\n\n"
    doc += f"- **Total Indices**: {es_schema.get('total_indices', 0)}\n"
    doc += f"- **Total Documents**: {es_schema.get('total_documents', 0):,}\n"
    
    return doc


def create_data_model_documentation(model_schema):
    """Create data model documentation in Markdown format"""
    
    doc = """# Data Model Documentation

## Overview
This document describes the Python data model classes used in the ADNI Knowledge Graph Enhancement project.

"""
    
    if "entity_classes" in model_schema:
        doc += "## Entity Classes\n\n"
        
        for class_name, class_info in model_schema["entity_classes"].items():
            doc += f"### {class_name}\n\n"
            
            if class_info.get("docstring"):
                doc += f"{class_info['docstring']}\n\n"
            
            # Fields
            if "fields" in class_info:
                doc += "**Fields**:\n"
                for field_name, field_info in class_info["fields"].items():
                    doc += f"- `{field_name}`: {field_info.get('type', 'unknown')}"
                    if not field_info.get('required', True):
                        doc += " (optional)"
                    doc += "\n"
            
            # Methods
            if "methods" in class_info and class_info["methods"]:
                doc += "\n**Methods**:\n"
                for method in class_info["methods"]:
                    doc += f"- `{method}()`\n"
            
            doc += "\n"
    
    doc += f"## Summary\n\n"
    doc += f"- **Total Classes**: {model_schema.get('total_classes', 0)}\n"
    
    return doc


def create_api_documentation():
    """Create API documentation for search and caching interfaces"""
    
    doc = """# API Documentation

## Overview
This document describes the API interfaces for search and caching in the ADNI Knowledge Graph Enhancement project.

## Search Engine API

### MultiModalSearchEngine

The `MultiModalSearchEngine` class provides unified search across Neo4j and Elasticsearch.

#### Methods

- `search_patients(query: SearchQuery) -> SearchResults`
  - Search across patient data using Elasticsearch
  - Supports complex queries with filters
  - Returns ranked results with highlighting

- `search_images(criteria: ImageSearchCriteria) -> List[ImageResult]`
  - Search medical images with metadata filtering
  - Supports modality, quality, and date range filters
  - Returns image metadata with file paths

- `get_cached_results(query_hash: str) -> Optional[SearchResults]`
  - Retrieve cached search results from Redis
  - Improves performance for repeated queries

- `cache_search_results(query_hash: str, results: SearchResults)`
  - Cache search results in Redis with TTL
  - Automatic cache invalidation

## Caching API

### Redis Caching System

The Redis caching system provides intelligent caching for images and metadata.

#### Cache Key Patterns

- `patient:{patient_id}:summary` - Patient summary JSON
- `image:{image_hash}:thumbnail` - Binary thumbnail data
- `image:{image_hash}:metadata` - Image metadata JSON
- `search:{query_hash}` - Cached search results
- `biomarker:{patient_id}:latest` - Latest biomarker values
- `family:{patient_id}:tree` - Family relationship data

#### Cache Policies

- **TTL**: 24 hours for patient summaries, 1 hour for search results
- **Eviction**: LRU with memory limit of 2GB
- **Preloading**: Cache frequently accessed patient data on startup

## Neo4j Query API

### Common Query Patterns

#### Patient Queries
```cypher
// Get patient with all visits
MATCH (p:Patient {ptid: $patient_id})-[:hasVisit]->(v:Visit)
RETURN p, collect(v) as visits

// Get patient family tree
MATCH (p:Patient {ptid: $patient_id})-[:hasFamilyMember*1..3]-(fm:FamilyMember)
RETURN p, collect(fm) as family_members
```

#### Image Queries
```cypher
// Get images by modality and quality
MATCH (img:ImageNode {modality: $modality})
WHERE img.quality_metrics.quality_score > $min_quality
RETURN img

// Get patient images with processing status
MATCH (p:Patient {ptid: $patient_id})-[:hasImage]->(img:ImageNode)
RETURN img.processing_status, count(img) as count
```

## Error Handling

All API methods implement comprehensive error handling:

- Connection failures are handled gracefully
- Partial results are returned when possible
- Detailed error logging for debugging
- Automatic retry mechanisms for transient failures

## Performance Considerations

- Use batch operations for large datasets
- Implement connection pooling for database connections
- Cache frequently accessed data in Redis
- Use appropriate indexes for query optimization
"""
    
    return doc


def print_summary(schema_docs):
    """Print a summary of the generated documentation"""
    
    print("\n" + "="*60)
    print("SCHEMA DOCUMENTATION GENERATION SUMMARY")
    print("="*60)
    
    # Neo4j summary
    neo4j_data = schema_docs.get("neo4j_schema", {})
    if "error" not in neo4j_data:
        print(f"Neo4j Database:")
        print(f"  - Nodes: {neo4j_data.get('total_nodes', 0):,}")
        print(f"  - Relationships: {neo4j_data.get('total_relationships', 0):,}")
        print(f"  - Node Labels: {len(neo4j_data.get('node_labels', []))}")
        print(f"  - Relationship Types: {len(neo4j_data.get('relationship_types', []))}")
    else:
        print(f"Neo4j Database: {neo4j_data['error']}")
    
    # Elasticsearch summary
    es_data = schema_docs.get("elasticsearch_schema", {})
    if "error" not in es_data:
        print(f"Elasticsearch:")
        print(f"  - Indices: {es_data.get('total_indices', 0)}")
        print(f"  - Documents: {es_data.get('total_documents', 0):,}")
    else:
        print(f"Elasticsearch: {es_data['error']}")
    
    # Data models summary
    model_data = schema_docs.get("data_model_schema", {})
    if "error" not in model_data:
        print(f"Data Models:")
        print(f"  - Entity Classes: {model_data.get('total_classes', 0)}")
    else:
        print(f"Data Models: {model_data['error']}")
    
    print("\nDocumentation files generated in outputs/metadata/schema_documentation/")
    print("="*60)


if __name__ == "__main__":
    main()