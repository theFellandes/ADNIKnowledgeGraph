"""
Enhanced Neo4j database connector with support for enhanced schema, family relationships, and image nodes
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager
from neo4j import GraphDatabase, Session
from neo4j.exceptions import ServiceUnavailable, SessionExpired
from models.entities import ImageNode, FamilyMember, ImageFilePaths, ImageQualityMetrics
from models.relationships import FamilyRelationship, RelationshipType, FamilyRelationshipValidator


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
                    batch_size: int = 1000, param_name: str = "batch") -> int:
        total_processed = 0
        with self.get_session() as session:
            for i in range(0, len(data_list), batch_size):
                batch = data_list[i:i + batch_size]

                def _batch_write(tx):
                    return tx.run(query, **{param_name: batch}).consume().counters

                session.execute_write(_batch_write)
                total_processed += len(batch)
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

    # Enhanced schema management methods
    def create_enhanced_schema_constraints(self) -> bool:
        """Create all constraints for the enhanced schema"""
        constraints = [
            ("Patient", "ptid"),
            ("Patient", "rid"),
            ("Visit", "visit_id"),
            ("ImageNode", "image_id"),
            ("FamilyMember", "member_id"),
            ("ImagingStudy", "study_id"),
            ("CognitiveAssessment", "assessment_id"),
            ("Biomarker", "biomarker_id"),
            ("Diagnosis", "diagnosis_id"),
            ("VolumetricMeasure", "measure_id"),
            ("PETBinding", "binding_id")
        ]
        
        success_count = 0
        for label, property_name in constraints:
            if self.create_constraint(label, property_name):
                success_count += 1
        
        logger.info(f"Created {success_count}/{len(constraints)} constraints")
        return success_count == len(constraints)

    def create_enhanced_schema_indexes(self) -> bool:
        """Create all indexes for the enhanced schema"""
        indexes = [
            ("Patient", "apoe_genotype"),
            ("Patient", "age_at_baseline"),
            ("Visit", "viscode"),
            ("Visit", "months_from_baseline"),
            ("ImageNode", "patient_id"),
            ("ImageNode", "modality"),
            ("ImageNode", "processing_status"),
            ("FamilyMember", "patient_id"),
            ("FamilyMember", "relationship_type"),
            ("ImagingStudy", "patient_id"),
            ("ImagingStudy", "modality"),
            ("CognitiveAssessment", "patient_id"),
            ("CognitiveAssessment", "test_name"),
            ("Biomarker", "patient_id"),
            ("Biomarker", "analyte"),
            ("Diagnosis", "patient_id"),
            ("Diagnosis", "diagnosis_code")
        ]
        
        success_count = 0
        for label, property_name in indexes:
            if self.create_index(label, property_name):
                success_count += 1
        
        logger.info(f"Created {success_count}/{len(indexes)} indexes")
        return success_count == len(indexes)

    def validate_schema_integrity(self) -> Tuple[bool, List[str]]:
        """Validate the integrity of the enhanced schema"""
        errors = []
        
        # Check for orphaned nodes
        orphan_checks = [
            ("ImageNode", "Patient", "patient_id", "ptid"),
            ("FamilyMember", "Patient", "patient_id", "ptid"),
            ("Visit", "Patient", "patient_id", "ptid"),
            ("CognitiveAssessment", "Patient", "patient_id", "ptid"),
            ("Biomarker", "Patient", "patient_id", "ptid")
        ]
        
        for child_label, parent_label, child_prop, parent_prop in orphan_checks:
            query = f"""
            MATCH (c:{child_label})
            WHERE NOT EXISTS {{
                MATCH (p:{parent_label} {{{parent_prop}: c.{child_prop}}})
            }}
            RETURN count(c) as orphan_count
            """
            result = self.run_query(query)
            orphan_count = result[0]["orphan_count"] if result else 0
            if orphan_count > 0:
                errors.append(f"Found {orphan_count} orphaned {child_label} nodes")
        
        return len(errors) == 0, errors

    # Enhanced image node methods
    def create_enhanced_image_node(self, image_node: ImageNode) -> bool:
        """Create an enhanced image node with file path management"""
        try:
            query = """
            CREATE (img:ImageNode {
                image_id: $image_id,
                study_id: $study_id,
                patient_id: $patient_id,
                visit_id: $visit_id,
                series_description: $series_description,
                image_type: $image_type,
                anatomical_region: $anatomical_region,
                pet_tracer: $pet_tracer,
                slice_number: $slice_number,
                acquisition_parameters: $acquisition_parameters,
                file_paths: $file_paths,
                dicom_metadata: $dicom_metadata,
                processing_status: $processing_status,
                quality_metrics: $quality_metrics,
                created_at: $created_at,
                updated_at: $updated_at
            })
            """
            
            parameters = {
                'image_id': image_node.image_id,
                'study_id': image_node.study_id,
                'patient_id': image_node.patient_id,
                'visit_id': image_node.visit_id,
                'series_description': image_node.series_description,
                'image_type': image_node.image_type,
                'anatomical_region': image_node.anatomical_region,
                'pet_tracer': image_node.pet_tracer,
                'slice_number': image_node.slice_number,
                'acquisition_parameters': image_node.acquisition_parameters,
                'file_paths': image_node.file_paths.to_dict(),
                'dicom_metadata': image_node.dicom_metadata,
                'processing_status': image_node.processing_status,
                'quality_metrics': image_node.quality_metrics.to_dict(),
                'created_at': image_node.created_at,
                'updated_at': image_node.updated_at
            }
            
            self.execute_write_transaction(query, parameters)
            logger.debug(f"Created enhanced image node: {image_node.image_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create enhanced image node {image_node.image_id}: {e}")
            return False

    def batch_create_enhanced_image_nodes(self, image_nodes: List[ImageNode], 
                                        batch_size: int = 100) -> int:
        """Batch create enhanced image nodes"""
        query = """
        UNWIND $batch as img
        CREATE (n:ImageNode {
            image_id: img.image_id,
            study_id: img.study_id,
            patient_id: img.patient_id,
            visit_id: img.visit_id,
            series_description: img.series_description,
            image_type: img.image_type,
            anatomical_region: img.anatomical_region,
            pet_tracer: img.pet_tracer,
            slice_number: img.slice_number,
            acquisition_parameters: img.acquisition_parameters,
            file_paths: img.file_paths,
            dicom_metadata: img.dicom_metadata,
            processing_status: img.processing_status,
            quality_metrics: img.quality_metrics,
            created_at: img.created_at,
            updated_at: img.updated_at
        })
        """
        
        data_list = [image_node.to_dict() for image_node in image_nodes]
        return self.batch_write(query, data_list, batch_size)

    def update_image_processing_status(self, image_id: str, status: str, 
                                     quality_metrics: Optional[Dict[str, Any]] = None) -> bool:
        """Update image processing status and quality metrics"""
        try:
            query = """
            MATCH (img:ImageNode {image_id: $image_id})
            SET img.processing_status = $status,
                img.updated_at = datetime()
            """
            
            parameters = {'image_id': image_id, 'status': status}
            
            if quality_metrics:
                query += ", img.quality_metrics = $quality_metrics"
                parameters['quality_metrics'] = quality_metrics
            
            self.execute_write_transaction(query, parameters)
            return True
            
        except Exception as e:
            logger.error(f"Failed to update image processing status for {image_id}: {e}")
            return False

    # Family relationship methods
    def create_family_member_node(self, family_member: FamilyMember) -> bool:
        """Create a family member node"""
        try:
            query = """
            CREATE (fm:FamilyMember {
                member_id: $member_id,
                patient_id: $patient_id,
                relationship_type: $relationship_type,
                gender: $gender,
                ad_status: $ad_status,
                demographics: $demographics,
                properties: $properties,
                created_at: $created_at,
                updated_at: $updated_at
            })
            """
            
            parameters = {
                'member_id': family_member.member_id,
                'patient_id': family_member.patient_id,
                'relationship_type': family_member.relationship_type,
                'gender': family_member.gender,
                'ad_status': family_member.ad_status.to_dict(),
                'demographics': family_member.demographics.to_dict(),
                'properties': family_member.properties,
                'created_at': family_member.created_at,
                'updated_at': family_member.updated_at
            }
            
            self.execute_write_transaction(query, parameters)
            logger.debug(f"Created family member node: {family_member.member_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create family member node {family_member.member_id}: {e}")
            return False

    def batch_create_family_members(self, family_members: List[FamilyMember], 
                                  batch_size: int = 100) -> int:
        """Batch create family member nodes"""
        query = """
        UNWIND $batch as fm
        CREATE (n:FamilyMember {
            member_id: fm.member_id,
            patient_id: fm.patient_id,
            relationship_type: fm.relationship_type,
            gender: fm.gender,
            ad_status: fm.ad_status,
            demographics: fm.demographics,
            properties: fm.properties,
            created_at: fm.created_at,
            updated_at: fm.updated_at
        })
        """
        
        data_list = [family_member.to_dict() for family_member in family_members]
        return self.batch_write(query, data_list, batch_size)

    def create_family_relationship(self, relationship: FamilyRelationship) -> bool:
        """Create a family relationship between nodes"""
        try:
            # Validate relationship first
            is_valid, errors = relationship.validate_relationship_integrity()
            if not is_valid:
                logger.error(f"Invalid family relationship: {errors}")
                return False
            
            query = f"""
            MATCH (from:{relationship.from_type} {{id: $from_id}})
            MATCH (to:{relationship.to_type} {{id: $to_id}})
            CREATE (from)-[r:{relationship.relationship_type.value} $properties]->(to)
            """
            
            # Handle different ID fields for different node types
            if relationship.from_type == "Patient":
                query = query.replace("{{id: $from_id}}", "{ptid: $from_id}")
            elif relationship.from_type == "FamilyMember":
                query = query.replace("{{id: $from_id}}", "{member_id: $from_id}")
            
            if relationship.to_type == "Patient":
                query = query.replace("{{id: $to_id}}", "{ptid: $to_id}")
            elif relationship.to_type == "FamilyMember":
                query = query.replace("{{id: $to_id}}", "{member_id: $to_id}")
            
            parameters = {
                'from_id': relationship.from_id,
                'to_id': relationship.to_id,
                'properties': relationship.properties
            }
            
            self.execute_write_transaction(query, parameters)
            logger.debug(f"Created family relationship: {relationship.from_id} -> {relationship.to_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create family relationship: {e}")
            return False

    def batch_create_family_relationships(self, relationships: List[FamilyRelationship], 
                                        batch_size: int = 100) -> Tuple[int, List[str]]:
        """Batch create family relationships with validation"""
        # Validate all relationships first
        valid_relationships = []
        errors = []
        
        for rel in relationships:
            is_valid, rel_errors = rel.validate_relationship_integrity()
            if is_valid:
                valid_relationships.append(rel)
            else:
                errors.extend(rel_errors)
        
        # Validate family tree integrity
        tree_valid, tree_errors = FamilyRelationshipValidator.validate_family_tree_integrity(valid_relationships)
        if not tree_valid:
            errors.extend(tree_errors)
            logger.warning(f"Family tree validation failed: {tree_errors}")
        
        # Create relationships in batches
        created_count = 0
        for i in range(0, len(valid_relationships), batch_size):
            batch = valid_relationships[i:i + batch_size]
            
            for rel in batch:
                if self.create_family_relationship(rel):
                    created_count += 1
        
        logger.info(f"Created {created_count}/{len(relationships)} family relationships")
        return created_count, errors

    def get_family_tree(self, patient_id: str, max_depth: int = 3) -> Dict[str, Any]:
        """Get complete family tree for a patient"""
        query = """
        MATCH path = (p:Patient {ptid: $patient_id})-[r:hasFamilyMember|hasParent|hasSibling|hasChild*1..$max_depth]-(fm:FamilyMember)
        RETURN p, relationships(path) as rels, nodes(path) as nodes
        """
        
        result = self.run_query(query, {'patient_id': patient_id, 'max_depth': max_depth})
        
        # Process results into family tree structure
        family_tree = {
            'patient_id': patient_id,
            'family_members': {},
            'relationships': []
        }
        
        for record in result:
            nodes = record.get('nodes', [])
            rels = record.get('rels', [])
            
            for node in nodes:
                if 'FamilyMember' in node.labels:
                    member_id = node.get('member_id')
                    if member_id:
                        family_tree['family_members'][member_id] = dict(node)
            
            for rel in rels:
                family_tree['relationships'].append({
                    'type': rel.type,
                    'start_node': rel.start_node.get('ptid') or rel.start_node.get('member_id'),
                    'end_node': rel.end_node.get('ptid') or rel.end_node.get('member_id'),
                    'properties': dict(rel)
                })
        
        return family_tree

    def get_images_by_processing_status(self, status: str) -> List[Dict[str, Any]]:
        """Get images by processing status"""
        query = """
        MATCH (img:ImageNode {processing_status: $status})
        RETURN img
        ORDER BY img.created_at DESC
        """
        
        result = self.run_query(query, {'status': status})
        return [record['img'] for record in result]

    def get_family_ad_risk_summary(self, patient_id: str) -> Dict[str, Any]:
        """Get family AD risk summary for a patient"""
        query = """
        MATCH (p:Patient {ptid: $patient_id})-[:hasFamilyMember]->(fm:FamilyMember)
        WHERE fm.ad_status.has_ad = true
        RETURN 
            count(fm) as affected_family_count,
            collect(fm.relationship_type) as affected_relationships,
            collect(fm.ad_status) as ad_statuses,
            avg(CASE WHEN fm.ad_status.age_at_onset IS NOT NULL THEN fm.ad_status.age_at_onset END) as avg_onset_age
        """
        
        result = self.run_query(query, {'patient_id': patient_id})
        return result[0] if result else {}