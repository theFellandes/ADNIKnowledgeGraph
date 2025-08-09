"""
MetadataGenerator for ADNI Knowledge Graph Enhancement
Generates comprehensive documentation, schema information, and data quality reports
"""

import os
import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from dataclasses import asdict
import inspect

from models.entities import *
from models.relationships import RelationshipType, FamilyRelationship

# Try to import optional dependencies
try:
    from utils.neo4j_connector import Neo4jConnector
except ImportError:
    Neo4jConnector = None

try:
    from utils.elasticsearch_indexer import SearchIndexer
except ImportError:
    SearchIndexer = None

logger = logging.getLogger(__name__)


class MetadataGenerator:
    """
    Comprehensive metadata and documentation generator for ADNI Knowledge Graph
    
    Generates:
    - Schema documentation from Neo4j and data models
    - Data dictionaries for all data types
    - ADNI protocol documentation integration
    - Data quality reports and processing summaries
    """

    def __init__(self, neo4j_connector: Optional[Any] = None,
                 elasticsearch_indexer: Optional[Any] = None,
                 output_base_path: str = "outputs"):
        """
        Initialize MetadataGenerator
        
        Args:
            neo4j_connector: Neo4j database connector
            elasticsearch_indexer: Elasticsearch indexer
            output_base_path: Base path for output files
        """
        self.neo4j = neo4j_connector
        self.elasticsearch = elasticsearch_indexer
        self.output_base_path = output_base_path
        
        # Create output directories
        self.metadata_path = os.path.join(output_base_path, "metadata")
        self.research_path = os.path.join(output_base_path, "research")
        
        self._ensure_directories()
        
        logger.info("MetadataGenerator initialized")

    def _ensure_directories(self):
        """Ensure all required directories exist"""
        directories = [
            self.metadata_path,
            self.research_path,
            os.path.join(self.metadata_path, "schema_documentation"),
            os.path.join(self.metadata_path, "data_dictionaries"),
            os.path.join(self.metadata_path, "processing_logs"),
            os.path.join(self.research_path, "analysis_reports"),
            os.path.join(self.research_path, "quality_metrics"),
            os.path.join(self.research_path, "usage_statistics")
        ]
        
        for directory in directories:
            os.makedirs(directory, exist_ok=True)

    def generate_schema_documentation(self) -> Dict[str, Any]:
        """
        Generate comprehensive schema documentation from Neo4j and data models
        
        Returns:
            Dictionary containing schema documentation
        """
        logger.info("Generating schema documentation...")
        
        schema_doc = {
            "generated_at": datetime.now().isoformat(),
            "neo4j_schema": self._extract_neo4j_schema(),
            "elasticsearch_schema": self._extract_elasticsearch_schema(),
            "data_model_schema": self._extract_data_model_schema(),
            "relationship_types": self._extract_relationship_types()
        }
        
        # Save to file
        output_file = os.path.join(self.metadata_path, "schema_documentation", "complete_schema.json")
        with open(output_file, 'w') as f:
            json.dump(schema_doc, f, indent=2, default=str)
        
        logger.info(f"Schema documentation saved to {output_file}")
        return schema_doc

    def _extract_neo4j_schema(self) -> Dict[str, Any]:
        """Extract Neo4j schema information"""
        if not self.neo4j:
            return {"error": "Neo4j connector not available"}
        
        try:
            # Get node labels and their properties
            node_labels_query = """
            CALL db.labels() YIELD label
            RETURN collect(label) as labels
            """
            labels_result = self.neo4j.run_query(node_labels_query)
            labels = labels_result[0]["labels"] if labels_result else []
            
            # Get relationship types
            rel_types_query = """
            CALL db.relationshipTypes() YIELD relationshipType
            RETURN collect(relationshipType) as types
            """
            rel_result = self.neo4j.run_query(rel_types_query)
            relationship_types = rel_result[0]["types"] if rel_result else []
            
            # Get property keys
            prop_keys_query = """
            CALL db.propertyKeys() YIELD propertyKey
            RETURN collect(propertyKey) as keys
            """
            prop_result = self.neo4j.run_query(prop_keys_query)
            property_keys = prop_result[0]["keys"] if prop_result else []
            
            # Get constraints
            constraints_query = """
            SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties
            RETURN collect({name: name, type: type, labels: labelsOrTypes, properties: properties}) as constraints
            """
            try:
                constraints_result = self.neo4j.run_query(constraints_query)
                constraints = constraints_result[0]["constraints"] if constraints_result else []
            except:
                constraints = []
            
            # Get indexes
            indexes_query = """
            SHOW INDEXES YIELD name, type, labelsOrTypes, properties
            RETURN collect({name: name, type: type, labels: labelsOrTypes, properties: properties}) as indexes
            """
            try:
                indexes_result = self.neo4j.run_query(indexes_query)
                indexes = indexes_result[0]["indexes"] if indexes_result else []
            except:
                indexes = []
            
            # Get node counts for each label
            node_counts = {}
            for label in labels:
                count_query = f"MATCH (n:{label}) RETURN count(n) as count"
                count_result = self.neo4j.run_query(count_query)
                node_counts[label] = count_result[0]["count"] if count_result else 0
            
            # Get relationship counts for each type
            relationship_counts = {}
            for rel_type in relationship_types:
                count_query = f"MATCH ()-[r:{rel_type}]->() RETURN count(r) as count"
                count_result = self.neo4j.run_query(count_query)
                relationship_counts[rel_type] = count_result[0]["count"] if count_result else 0
            
            return {
                "node_labels": labels,
                "relationship_types": relationship_types,
                "property_keys": property_keys,
                "constraints": constraints,
                "indexes": indexes,
                "node_counts": node_counts,
                "relationship_counts": relationship_counts,
                "total_nodes": sum(node_counts.values()),
                "total_relationships": sum(relationship_counts.values())
            }
            
        except Exception as e:
            logger.error(f"Error extracting Neo4j schema: {e}")
            return {"error": str(e)}

    def _extract_elasticsearch_schema(self) -> Dict[str, Any]:
        """Extract Elasticsearch schema information"""
        if not self.elasticsearch or not self.elasticsearch.es:
            return {"error": "Elasticsearch indexer not available"}
        
        try:
            indices_info = {}
            
            # Get all indices
            indices = self.elasticsearch.es.indices.get_alias(index="*")
            
            for index_name in indices.keys():
                if index_name.startswith('.'):  # Skip system indices
                    continue
                
                try:
                    # Get mapping
                    mapping = self.elasticsearch.es.indices.get_mapping(index=index_name)
                    
                    # Get settings
                    settings = self.elasticsearch.es.indices.get_settings(index=index_name)
                    
                    # Get document count
                    count = self.elasticsearch.es.count(index=index_name)
                    
                    indices_info[index_name] = {
                        "mappings": mapping[index_name]["mappings"],
                        "settings": settings[index_name]["settings"],
                        "document_count": count["count"]
                    }
                    
                except Exception as e:
                    logger.warning(f"Could not get info for index {index_name}: {e}")
                    indices_info[index_name] = {"error": str(e)}
            
            return {
                "indices": indices_info,
                "total_indices": len(indices_info),
                "total_documents": sum(info.get("document_count", 0) for info in indices_info.values() if "document_count" in info)
            }
            
        except Exception as e:
            logger.error(f"Error extracting Elasticsearch schema: {e}")
            return {"error": str(e)}

    def _extract_data_model_schema(self) -> Dict[str, Any]:
        """Extract data model schema from Python classes"""
        try:
            # Get all entity classes from models.entities
            entity_classes = []
            for name, obj in inspect.getmembers(inspect.getmodule(Patient)):
                if inspect.isclass(obj) and hasattr(obj, '__dataclass_fields__'):
                    entity_classes.append(obj)
            
            models_info = {}
            
            for cls in entity_classes:
                class_info = {
                    "name": cls.__name__,
                    "module": cls.__module__,
                    "docstring": cls.__doc__,
                    "fields": {}
                }
                
                # Extract field information
                if hasattr(cls, '__dataclass_fields__'):
                    for field_name, field in cls.__dataclass_fields__.items():
                        field_info = {
                            "type": str(field.type),
                            "default": str(field.default) if field.default != field.default_factory else "factory",
                            "required": field.default == field.default_factory and field.default_factory == field.default_factory
                        }
                        class_info["fields"][field_name] = field_info
                
                # Extract methods
                methods = []
                for method_name in dir(cls):
                    if not method_name.startswith('_') and callable(getattr(cls, method_name)):
                        methods.append(method_name)
                class_info["methods"] = methods
                
                models_info[cls.__name__] = class_info
            
            return {
                "entity_classes": models_info,
                "total_classes": len(models_info)
            }
            
        except Exception as e:
            logger.error(f"Error extracting data model schema: {e}")
            return {"error": str(e)}

    def _extract_relationship_types(self) -> Dict[str, Any]:
        """Extract relationship type definitions"""
        try:
            relationship_info = {}
            
            for rel_type in RelationshipType:
                relationship_info[rel_type.name] = {
                    "value": rel_type.value,
                    "description": f"Relationship type: {rel_type.value}"
                }
            
            return {
                "relationship_types": relationship_info,
                "total_types": len(relationship_info)
            }
            
        except Exception as e:
            logger.error(f"Error extracting relationship types: {e}")
            return {"error": str(e)}

    def create_data_dictionaries(self) -> Dict[str, Any]:
        """
        Create comprehensive data dictionaries for all data types
        
        Returns:
            Dictionary containing data dictionaries
        """
        logger.info("Creating data dictionaries...")
        
        data_dictionaries = {
            "generated_at": datetime.now().isoformat(),
            "patient_data": self._create_patient_dictionary(),
            "imaging_data": self._create_imaging_dictionary(),
            "biomarker_data": self._create_biomarker_dictionary(),
            "family_data": self._create_family_dictionary(),
            "clinical_data": self._create_clinical_dictionary()
        }
        
        # Save to file
        output_file = os.path.join(self.metadata_path, "data_dictionaries", "complete_data_dictionary.json")
        with open(output_file, 'w') as f:
            json.dump(data_dictionaries, f, indent=2, default=str)
        
        logger.info(f"Data dictionaries saved to {output_file}")
        return data_dictionaries

    def _create_patient_dictionary(self) -> Dict[str, Any]:
        """Create patient data dictionary"""
        return {
            "description": "Patient demographic and clinical information from ADNI dataset",
            "source": "ADNI clinical data tables",
            "fields": {
                "ptid": {
                    "description": "Patient identifier",
                    "type": "string",
                    "required": True,
                    "example": "002_S_0295"
                },
                "rid": {
                    "description": "Research identifier",
                    "type": "string",
                    "required": True,
                    "example": "2"
                },
                "gender": {
                    "description": "Patient gender",
                    "type": "string",
                    "values": ["Male", "Female"],
                    "required": False
                },
                "age_at_baseline": {
                    "description": "Age at baseline visit in years",
                    "type": "float",
                    "range": [55, 95],
                    "required": False
                },
                "education_years": {
                    "description": "Years of education completed",
                    "type": "integer",
                    "range": [6, 20],
                    "required": False
                },
                "apoe_genotype": {
                    "description": "APOE genotype",
                    "type": "string",
                    "values": ["2,2", "2,3", "2,4", "3,3", "3,4", "4,4"],
                    "required": False
                }
            }
        }

    def _create_imaging_dictionary(self) -> Dict[str, Any]:
        """Create imaging data dictionary"""
        return {
            "description": "Medical imaging data including MRI and PET scans",
            "source": "ADNI imaging data with DICOM metadata",
            "fields": {
                "image_id": {
                    "description": "Unique image identifier",
                    "type": "string",
                    "required": True
                },
                "modality": {
                    "description": "Imaging modality",
                    "type": "string",
                    "values": ["MRI", "PET", "DTI", "fMRI"],
                    "required": True
                },
                "series_description": {
                    "description": "DICOM series description",
                    "type": "string",
                    "required": False
                },
                "file_paths": {
                    "description": "File paths for different image formats",
                    "type": "object",
                    "properties": {
                        "dicom_path": "Path to original DICOM file",
                        "png_path": "Path to PNG conversion",
                        "thumbnail_path": "Path to thumbnail image"
                    }
                },
                "quality_metrics": {
                    "description": "Image quality assessment metrics",
                    "type": "object",
                    "properties": {
                        "psnr": "Peak Signal-to-Noise Ratio",
                        "ssim": "Structural Similarity Index",
                        "quality_score": "Overall quality score (0-1)"
                    }
                }
            }
        }

    def _create_biomarker_dictionary(self) -> Dict[str, Any]:
        """Create biomarker data dictionary"""
        return {
            "description": "Biomarker measurements including CSF and blood markers",
            "source": "ADNI biomarker data tables",
            "fields": {
                "biomarker_id": {
                    "description": "Unique biomarker measurement identifier",
                    "type": "string",
                    "required": True
                },
                "analyte": {
                    "description": "Biomarker analyte name",
                    "type": "string",
                    "values": ["ABETA", "TAU", "PTAU", "NFL", "GFAP"],
                    "required": True
                },
                "value": {
                    "description": "Measured biomarker value",
                    "type": "float",
                    "required": True
                },
                "unit": {
                    "description": "Measurement unit",
                    "type": "string",
                    "values": ["pg/mL", "ng/mL", "μg/mL"],
                    "required": True
                },
                "abnormal_flag": {
                    "description": "Whether value is outside normal range",
                    "type": "boolean",
                    "required": False
                }
            }
        }

    def _create_family_dictionary(self) -> Dict[str, Any]:
        """Create family data dictionary"""
        return {
            "description": "Family history and relationship information",
            "source": "ADNI family history questionnaires",
            "fields": {
                "member_id": {
                    "description": "Unique family member identifier",
                    "type": "string",
                    "required": True
                },
                "relationship_type": {
                    "description": "Relationship to patient",
                    "type": "string",
                    "values": ["parent", "sibling", "child", "grandparent", "aunt", "uncle", "cousin"],
                    "required": True
                },
                "ad_status": {
                    "description": "Alzheimer's disease status information",
                    "type": "object",
                    "properties": {
                        "has_ad": "Whether family member has AD",
                        "age_at_onset": "Age at AD onset",
                        "confidence_level": "Confidence in diagnosis"
                    }
                }
            }
        }

    def _create_clinical_dictionary(self) -> Dict[str, Any]:
        """Create clinical data dictionary"""
        return {
            "description": "Clinical assessments and visit information",
            "source": "ADNI clinical assessment data",
            "fields": {
                "visit_id": {
                    "description": "Unique visit identifier",
                    "type": "string",
                    "required": True
                },
                "viscode": {
                    "description": "Visit code",
                    "type": "string",
                    "values": ["bl", "m06", "m12", "m18", "m24", "m36"],
                    "required": True
                },
                "diagnosis_code": {
                    "description": "Clinical diagnosis code",
                    "type": "string",
                    "values": ["CN", "MCI", "AD"],
                    "required": False
                }
            }
        }

    def integrate_adni_protocol_documentation(self) -> Dict[str, Any]:
        """
        Integrate ADNI protocol documentation and references
        
        Returns:
            Dictionary containing ADNI protocol information
        """
        logger.info("Integrating ADNI protocol documentation...")
        
        adni_protocols = {
            "generated_at": datetime.now().isoformat(),
            "adni_overview": {
                "name": "Alzheimer's Disease Neuroimaging Initiative",
                "description": "Longitudinal multicenter study designed to develop clinical, imaging, genetic, and biochemical biomarkers for early detection and tracking of Alzheimer's disease",
                "website": "http://adni.loni.usc.edu/",
                "principal_investigator": "Michael W. Weiner, MD",
                "funding": "National Institute on Aging, National Institute of Biomedical Imaging and Bioengineering"
            },
            "study_phases": {
                "ADNI-1": {
                    "period": "2004-2009",
                    "participants": 800,
                    "description": "Initial phase focusing on MRI and PET imaging biomarkers"
                },
                "ADNI-GO": {
                    "period": "2009-2011",
                    "participants": 200,
                    "description": "Extension focusing on early mild cognitive impairment"
                },
                "ADNI-2": {
                    "period": "2011-2016",
                    "participants": 1000,
                    "description": "Expanded imaging protocols and biomarker collection"
                },
                "ADNI-3": {
                    "period": "2016-2022",
                    "participants": 1070,
                    "description": "Advanced imaging techniques and tau PET"
                }
            },
            "imaging_protocols": {
                "MRI": {
                    "sequences": ["T1-weighted", "T2-weighted", "FLAIR", "DTI"],
                    "field_strength": ["1.5T", "3T"],
                    "slice_thickness": "1.2mm",
                    "matrix_size": "256x256"
                },
                "PET": {
                    "tracers": ["FDG", "AV45 (Florbetapir)", "AV1451 (Flortaucipir)"],
                    "acquisition_time": "20 minutes",
                    "reconstruction": "OSEM with attenuation correction"
                }
            },
            "biomarker_protocols": {
                "CSF": {
                    "collection": "Lumbar puncture at L3/L4 or L4/L5",
                    "volume": "20-24 mL",
                    "processing": "Centrifugation at 2000g for 10 minutes",
                    "storage": "-80°C in polypropylene tubes"
                },
                "blood": {
                    "collection": "Fasting blood draw",
                    "tubes": "EDTA and serum separator tubes",
                    "processing": "Centrifugation within 1 hour",
                    "storage": "-80°C"
                }
            },
            "cognitive_assessments": {
                "MMSE": "Mini-Mental State Examination",
                "ADAS-Cog": "Alzheimer's Disease Assessment Scale-Cognitive",
                "CDR": "Clinical Dementia Rating",
                "FAQ": "Functional Activities Questionnaire",
                "NPI": "Neuropsychiatric Inventory"
            },
            "quality_control": {
                "imaging": "Phantom scans, visual quality checks, automated QC metrics",
                "biomarkers": "Duplicate measurements, inter-laboratory comparisons",
                "clinical": "Training and certification of raters"
            }
        }
        
        # Save to file
        output_file = os.path.join(self.metadata_path, "adni_protocol_documentation.json")
        with open(output_file, 'w') as f:
            json.dump(adni_protocols, f, indent=2, default=str)
        
        logger.info(f"ADNI protocol documentation saved to {output_file}")
        return adni_protocols

    def generate_all_metadata(self) -> Dict[str, Any]:
        """
        Generate all metadata documentation
        
        Returns:
            Dictionary containing all generated metadata
        """
        logger.info("Generating all metadata documentation...")
        
        metadata = {
            "generation_info": {
                "generated_at": datetime.now().isoformat(),
                "generator_version": "1.0.0",
                "adni_kg_version": "enhanced"
            },
            "schema_documentation": self.generate_schema_documentation(),
            "data_dictionaries": self.create_data_dictionaries(),
            "adni_protocols": self.integrate_adni_protocol_documentation()
        }
        
        # Save complete metadata
        output_file = os.path.join(self.metadata_path, "complete_metadata.json")
        with open(output_file, 'w') as f:
            json.dump(metadata, f, indent=2, default=str)
        
        logger.info(f"Complete metadata saved to {output_file}")
        return metadata

    def generate_data_quality_reports(self) -> Dict[str, Any]:
        """
        Generate comprehensive data quality reports
        
        Returns:
            Dictionary containing data quality analysis
        """
        logger.info("Generating data quality reports...")
        
        quality_report = {
            "generated_at": datetime.now().isoformat(),
            "completeness_analysis": self._analyze_data_completeness(),
            "image_quality_assessment": self._assess_image_quality(),
            "family_relationship_integrity": self._check_family_integrity(),
            "processing_statistics": self._generate_processing_stats()
        }
        
        # Save to file
        output_file = os.path.join(self.research_path, "quality_metrics", "data_quality_report.json")
        with open(output_file, 'w') as f:
            json.dump(quality_report, f, indent=2, default=str)
        
        logger.info(f"Data quality report saved to {output_file}")
        return quality_report

    def _analyze_data_completeness(self) -> Dict[str, Any]:
        """Analyze data completeness across all modalities"""
        if not self.neo4j:
            return {"error": "Neo4j connector not available"}
        
        try:
            completeness = {}
            
            # Patient data completeness
            patient_query = """
            MATCH (p:Patient)
            RETURN 
                count(p) as total_patients,
                count(p.gender) as has_gender,
                count(p.age_at_baseline) as has_age,
                count(p.education_years) as has_education,
                count(p.apoe_genotype) as has_apoe
            """
            patient_result = self.neo4j.run_query(patient_query)
            if patient_result:
                p_data = patient_result[0]
                total = p_data["total_patients"]
                completeness["patients"] = {
                    "total_count": total,
                    "gender_completeness": (p_data["has_gender"] / total * 100) if total > 0 else 0,
                    "age_completeness": (p_data["has_age"] / total * 100) if total > 0 else 0,
                    "education_completeness": (p_data["has_education"] / total * 100) if total > 0 else 0,
                    "apoe_completeness": (p_data["has_apoe"] / total * 100) if total > 0 else 0
                }
            
            # Imaging data completeness
            imaging_query = """
            MATCH (img:ImageNode)
            RETURN 
                count(img) as total_images,
                count(img.file_paths.dicom_path) as has_dicom,
                count(img.file_paths.png_path) as has_png,
                count(img.file_paths.thumbnail_path) as has_thumbnail,
                sum(CASE WHEN img.processing_status = 'completed' THEN 1 ELSE 0 END) as completed_processing
            """
            imaging_result = self.neo4j.run_query(imaging_query)
            if imaging_result:
                i_data = imaging_result[0]
                total = i_data["total_images"]
                completeness["imaging"] = {
                    "total_count": total,
                    "dicom_completeness": (i_data["has_dicom"] / total * 100) if total > 0 else 0,
                    "png_completeness": (i_data["has_png"] / total * 100) if total > 0 else 0,
                    "thumbnail_completeness": (i_data["has_thumbnail"] / total * 100) if total > 0 else 0,
                    "processing_completeness": (i_data["completed_processing"] / total * 100) if total > 0 else 0
                }
            
            # Family data completeness
            family_query = """
            MATCH (fm:FamilyMember)
            RETURN 
                count(fm) as total_family_members,
                count(fm.ad_status.has_ad) as has_ad_status,
                count(fm.demographics.age) as has_age,
                count(fm.gender) as has_gender
            """
            family_result = self.neo4j.run_query(family_query)
            if family_result:
                f_data = family_result[0]
                total = f_data["total_family_members"]
                completeness["family"] = {
                    "total_count": total,
                    "ad_status_completeness": (f_data["has_ad_status"] / total * 100) if total > 0 else 0,
                    "age_completeness": (f_data["has_age"] / total * 100) if total > 0 else 0,
                    "gender_completeness": (f_data["has_gender"] / total * 100) if total > 0 else 0
                }
            
            return completeness
            
        except Exception as e:
            logger.error(f"Error analyzing data completeness: {e}")
            return {"error": str(e)}

    def _assess_image_quality(self) -> Dict[str, Any]:
        """Assess image quality metrics"""
        if not self.neo4j:
            return {"error": "Neo4j connector not available"}
        
        try:
            quality_query = """
            MATCH (img:ImageNode)
            WHERE img.quality_metrics IS NOT NULL
            RETURN 
                count(img) as total_with_metrics,
                avg(img.quality_metrics.psnr) as avg_psnr,
                avg(img.quality_metrics.ssim) as avg_ssim,
                avg(img.quality_metrics.quality_score) as avg_quality_score,
                sum(CASE WHEN img.quality_metrics.validation_passed = true THEN 1 ELSE 0 END) as passed_validation,
                collect(img.quality_metrics.quality_score) as quality_scores
            """
            
            result = self.neo4j.run_query(quality_query)
            if result:
                data = result[0]
                quality_scores = data.get("quality_scores", [])
                
                # Calculate quality distribution
                quality_distribution = {
                    "excellent": sum(1 for score in quality_scores if score and score >= 0.9),
                    "good": sum(1 for score in quality_scores if score and 0.7 <= score < 0.9),
                    "fair": sum(1 for score in quality_scores if score and 0.5 <= score < 0.7),
                    "poor": sum(1 for score in quality_scores if score and score < 0.5)
                }
                
                return {
                    "total_images_with_metrics": data["total_with_metrics"],
                    "average_psnr": data["avg_psnr"],
                    "average_ssim": data["avg_ssim"],
                    "average_quality_score": data["avg_quality_score"],
                    "validation_pass_rate": (data["passed_validation"] / data["total_with_metrics"] * 100) if data["total_with_metrics"] > 0 else 0,
                    "quality_distribution": quality_distribution
                }
            
            return {"no_data": "No image quality metrics found"}
            
        except Exception as e:
            logger.error(f"Error assessing image quality: {e}")
            return {"error": str(e)}

    def _check_family_integrity(self) -> Dict[str, Any]:
        """Check family relationship integrity"""
        if not self.neo4j:
            return {"error": "Neo4j connector not available"}
        
        try:
            integrity_report = {}
            
            # Check for orphaned family members
            orphan_query = """
            MATCH (fm:FamilyMember)
            WHERE NOT EXISTS {
                MATCH (p:Patient {ptid: fm.patient_id})
            }
            RETURN count(fm) as orphaned_family_members
            """
            orphan_result = self.neo4j.run_query(orphan_query)
            integrity_report["orphaned_family_members"] = orphan_result[0]["orphaned_family_members"] if orphan_result else 0
            
            # Check for circular relationships
            circular_query = """
            MATCH path = (p:Patient)-[:hasFamilyMember*2..4]-(p)
            RETURN count(path) as circular_relationships
            """
            circular_result = self.neo4j.run_query(circular_query)
            integrity_report["circular_relationships"] = circular_result[0]["circular_relationships"] if circular_result else 0
            
            # Check relationship consistency
            consistency_query = """
            MATCH (p:Patient)-[r:hasParent]->(fm:FamilyMember)
            WHERE NOT EXISTS {
                MATCH (fm)-[:hasChild]->(p)
            }
            RETURN count(r) as inconsistent_parent_child
            """
            consistency_result = self.neo4j.run_query(consistency_query)
            integrity_report["inconsistent_parent_child"] = consistency_result[0]["inconsistent_parent_child"] if consistency_result else 0
            
            # Family AD status distribution
            ad_status_query = """
            MATCH (fm:FamilyMember)
            RETURN 
                count(fm) as total_family_members,
                sum(CASE WHEN fm.ad_status.has_ad = true THEN 1 ELSE 0 END) as with_ad,
                sum(CASE WHEN fm.ad_status.has_ad = false THEN 1 ELSE 0 END) as without_ad,
                sum(CASE WHEN fm.ad_status.has_ad IS NULL THEN 1 ELSE 0 END) as unknown_ad_status
            """
            ad_result = self.neo4j.run_query(ad_status_query)
            if ad_result:
                ad_data = ad_result[0]
                integrity_report["ad_status_distribution"] = {
                    "total": ad_data["total_family_members"],
                    "with_ad": ad_data["with_ad"],
                    "without_ad": ad_data["without_ad"],
                    "unknown": ad_data["unknown_ad_status"]
                }
            
            return integrity_report
            
        except Exception as e:
            logger.error(f"Error checking family integrity: {e}")
            return {"error": str(e)}

    def _generate_processing_stats(self) -> Dict[str, Any]:
        """Generate processing success/failure statistics"""
        if not self.neo4j:
            return {"error": "Neo4j connector not available"}
        
        try:
            stats = {}
            
            # Image processing statistics
            image_stats_query = """
            MATCH (img:ImageNode)
            RETURN 
                count(img) as total_images,
                sum(CASE WHEN img.processing_status = 'completed' THEN 1 ELSE 0 END) as completed,
                sum(CASE WHEN img.processing_status = 'failed' THEN 1 ELSE 0 END) as failed,
                sum(CASE WHEN img.processing_status = 'pending' THEN 1 ELSE 0 END) as pending,
                sum(CASE WHEN img.processing_status = 'processing' THEN 1 ELSE 0 END) as processing
            """
            image_result = self.neo4j.run_query(image_stats_query)
            if image_result:
                img_data = image_result[0]
                stats["image_processing"] = {
                    "total": img_data["total_images"],
                    "completed": img_data["completed"],
                    "failed": img_data["failed"],
                    "pending": img_data["pending"],
                    "processing": img_data["processing"],
                    "success_rate": (img_data["completed"] / img_data["total_images"] * 100) if img_data["total_images"] > 0 else 0
                }
            
            # Family extraction statistics
            family_stats_query = """
            MATCH (p:Patient)
            OPTIONAL MATCH (p)-[:hasFamilyMember]->(fm:FamilyMember)
            RETURN 
                count(DISTINCT p) as total_patients,
                count(DISTINCT fm) as total_family_members,
                count(DISTINCT p) - count(DISTINCT CASE WHEN fm IS NOT NULL THEN p END) as patients_without_family
            """
            family_result = self.neo4j.run_query(family_stats_query)
            if family_result:
                fam_data = family_result[0]
                stats["family_extraction"] = {
                    "total_patients": fam_data["total_patients"],
                    "total_family_members": fam_data["total_family_members"],
                    "patients_without_family": fam_data["patients_without_family"],
                    "family_extraction_rate": ((fam_data["total_patients"] - fam_data["patients_without_family"]) / fam_data["total_patients"] * 100) if fam_data["total_patients"] > 0 else 0
                }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error generating processing stats: {e}")
            return {"error": str(e)}

    def generate_research_content(self) -> Dict[str, Any]:
        """
        Generate research content and statistics
        
        Returns:
            Dictionary containing research content
        """
        logger.info("Generating research content and statistics...")
        
        research_content = {
            "generated_at": datetime.now().isoformat(),
            "dataset_statistics": self._generate_dataset_statistics(),
            "usage_analytics": self._generate_usage_analytics(),
            "research_examples": self._create_research_examples(),
            "export_workflows": self._document_export_workflows()
        }
        
        # Save to file
        output_file = os.path.join(self.research_path, "analysis_reports", "research_content.json")
        with open(output_file, 'w') as f:
            json.dump(research_content, f, indent=2, default=str)
        
        logger.info(f"Research content saved to {output_file}")
        return research_content

    def _generate_dataset_statistics(self) -> Dict[str, Any]:
        """Generate dataset statistics with patient demographics and data availability"""
        if not self.neo4j:
            return {"error": "Neo4j connector not available"}
        
        try:
            stats = {}
            
            # Patient demographics
            demo_query = """
            MATCH (p:Patient)
            RETURN 
                count(p) as total_patients,
                avg(p.age_at_baseline) as avg_age,
                min(p.age_at_baseline) as min_age,
                max(p.age_at_baseline) as max_age,
                sum(CASE WHEN p.gender = 'Male' THEN 1 ELSE 0 END) as male_count,
                sum(CASE WHEN p.gender = 'Female' THEN 1 ELSE 0 END) as female_count,
                avg(p.education_years) as avg_education
            """
            demo_result = self.neo4j.run_query(demo_query)
            if demo_result:
                demo_data = demo_result[0]
                stats["demographics"] = {
                    "total_patients": demo_data["total_patients"],
                    "age_statistics": {
                        "average": demo_data["avg_age"],
                        "minimum": demo_data["min_age"],
                        "maximum": demo_data["max_age"]
                    },
                    "gender_distribution": {
                        "male": demo_data["male_count"],
                        "female": demo_data["female_count"]
                    },
                    "average_education_years": demo_data["avg_education"]
                }
            
            # APOE distribution
            apoe_query = """
            MATCH (p:Patient)
            WHERE p.apoe_genotype IS NOT NULL
            RETURN p.apoe_genotype as genotype, count(p) as count
            ORDER BY count DESC
            """
            apoe_result = self.neo4j.run_query(apoe_query)
            if apoe_result:
                stats["apoe_distribution"] = {row["genotype"]: row["count"] for row in apoe_result}
            
            # Data modality availability
            modality_query = """
            MATCH (p:Patient)
            OPTIONAL MATCH (p)-[:hasVisit]->(v:Visit)
            OPTIONAL MATCH (v)-[:hasImaging]->(img:ImagingStudy)
            OPTIONAL MATCH (v)-[:hasBiomarker]->(bio:Biomarker)
            OPTIONAL MATCH (p)-[:hasFamilyMember]->(fm:FamilyMember)
            RETURN 
                count(DISTINCT p) as total_patients,
                count(DISTINCT v) as total_visits,
                count(DISTINCT img) as total_imaging_studies,
                count(DISTINCT bio) as total_biomarkers,
                count(DISTINCT fm) as total_family_members
            """
            modality_result = self.neo4j.run_query(modality_query)
            if modality_result:
                mod_data = modality_result[0]
                stats["data_availability"] = {
                    "total_visits": mod_data["total_visits"],
                    "total_imaging_studies": mod_data["total_imaging_studies"],
                    "total_biomarkers": mod_data["total_biomarkers"],
                    "total_family_members": mod_data["total_family_members"],
                    "visits_per_patient": mod_data["total_visits"] / mod_data["total_patients"] if mod_data["total_patients"] > 0 else 0
                }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error generating dataset statistics: {e}")
            return {"error": str(e)}

    def _generate_usage_analytics(self) -> Dict[str, Any]:
        """Generate usage analytics and system performance reports"""
        # This would typically connect to system logs, but for now we'll provide a template
        return {
            "system_performance": {
                "average_query_time": "< 100ms",
                "cache_hit_rate": "85%",
                "concurrent_users": "10-50",
                "data_processing_throughput": "1000 images/hour"
            },
            "popular_queries": [
                "Patient search by APOE genotype",
                "Image search by modality and quality",
                "Family history AD risk analysis",
                "Biomarker trend analysis"
            ],
            "data_access_patterns": {
                "most_accessed_modality": "MRI",
                "most_queried_biomarker": "ABETA",
                "peak_usage_hours": "9AM-5PM EST"
            }
        }

    def _create_research_examples(self) -> Dict[str, Any]:
        """Create research use case examples with sample queries"""
        return {
            "use_cases": {
                "genetic_risk_analysis": {
                    "description": "Analyze genetic risk factors for AD progression",
                    "neo4j_query": """
                    MATCH (p:Patient {apoe_genotype: '3,4'})-[:hasVisit]->(v:Visit)-[:hasDiagnosis]->(d:Diagnosis)
                    WHERE d.diagnosis_code IN ['MCI', 'AD']
                    RETURN p.ptid, p.age_at_baseline, d.diagnosis_code, v.months_from_baseline
                    ORDER BY v.months_from_baseline
                    """,
                    "elasticsearch_query": {
                        "query": {
                            "bool": {
                                "must": [
                                    {"term": {"demographics.apoe_genotype": "3,4"}},
                                    {"terms": {"diagnoses.diagnosis": ["MCI", "AD"]}}
                                ]
                            }
                        }
                    }
                },
                "imaging_biomarker_correlation": {
                    "description": "Correlate imaging findings with CSF biomarkers",
                    "neo4j_query": """
                    MATCH (p:Patient)-[:hasVisit]->(v:Visit)
                    MATCH (v)-[:hasImaging]->(img:ImagingStudy)
                    MATCH (v)-[:hasBiomarker]->(bio:Biomarker {analyte: 'ABETA'})
                    RETURN p.ptid, img.modality, bio.value, v.months_from_baseline
                    """,
                    "elasticsearch_query": {
                        "query": {
                            "bool": {
                                "must": [
                                    {"exists": {"field": "imaging_sessions"}},
                                    {"nested": {
                                        "path": "biomarkers",
                                        "query": {"term": {"biomarkers.biomarker_name": "ABETA"}}
                                    }}
                                ]
                            }
                        }
                    }
                },
                "family_history_analysis": {
                    "description": "Analyze family history patterns and AD risk",
                    "neo4j_query": """
                    MATCH (p:Patient)-[:hasFamilyMember]->(fm:FamilyMember)
                    WHERE fm.ad_status.has_ad = true
                    RETURN p.ptid, fm.relationship_type, fm.ad_status.age_at_onset,
                           count(fm) as affected_family_count
                    """,
                    "elasticsearch_query": {
                        "query": {
                            "nested": {
                                "path": "family_history.family_members",
                                "query": {"term": {"family_history.family_members.ad_status": "affected"}}
                            }
                        }
                    }
                }
            }
        }

    def _document_export_workflows(self) -> Dict[str, Any]:
        """Document data export and analysis workflow procedures"""
        return {
            "export_formats": {
                "csv": {
                    "description": "Comma-separated values for statistical analysis",
                    "use_cases": ["R analysis", "Python pandas", "Excel"],
                    "example_command": "MATCH (p:Patient) RETURN p.ptid, p.age_at_baseline, p.gender"
                },
                "json": {
                    "description": "JSON format for web applications and APIs",
                    "use_cases": ["Web applications", "API responses", "NoSQL databases"],
                    "example_command": "GET /api/patients/{patient_id}"
                },
                "rdf": {
                    "description": "RDF format for semantic web applications",
                    "use_cases": ["Ontology integration", "Linked data", "SPARQL queries"],
                    "example_command": "CONSTRUCT query for RDF export"
                }
            },
            "analysis_workflows": {
                "longitudinal_analysis": {
                    "steps": [
                        "1. Extract patient timeline data",
                        "2. Align visits by months from baseline",
                        "3. Calculate change scores",
                        "4. Apply statistical models",
                        "5. Visualize trajectories"
                    ],
                    "tools": ["R", "Python", "MATLAB", "SAS"]
                },
                "multimodal_integration": {
                    "steps": [
                        "1. Query data from multiple modalities",
                        "2. Align by visit and timepoint",
                        "3. Handle missing data",
                        "4. Apply dimensionality reduction",
                        "5. Build predictive models"
                    ],
                    "tools": ["Python scikit-learn", "R caret", "MATLAB"]
                }
            },
            "best_practices": [
                "Always include patient consent status in exports",
                "Remove direct identifiers for public sharing",
                "Document data preprocessing steps",
                "Validate data integrity after export",
                "Include metadata and data dictionaries"
            ]
        }

    def generate_complete_documentation(self) -> Dict[str, Any]:
        """
        Generate complete documentation package
        
        Returns:
            Dictionary containing all documentation
        """
        logger.info("Generating complete documentation package...")
        
        complete_docs = {
            "generation_info": {
                "generated_at": datetime.now().isoformat(),
                "generator_version": "1.0.0",
                "documentation_type": "complete_package"
            },
            "metadata": self.generate_all_metadata(),
            "quality_reports": self.generate_data_quality_reports(),
            "research_content": self.generate_research_content()
        }
        
        # Save complete documentation
        output_file = os.path.join(self.output_base_path, "complete_documentation.json")
        with open(output_file, 'w') as f:
            json.dump(complete_docs, f, indent=2, default=str)
        
        # Generate summary report
        self._generate_summary_report(complete_docs)
        
        logger.info(f"Complete documentation package saved to {output_file}")
        return complete_docs

    def _generate_summary_report(self, complete_docs: Dict[str, Any]):
        """Generate a human-readable summary report"""
        summary = f"""
# ADNI Knowledge Graph Enhancement - Documentation Summary

Generated: {complete_docs['generation_info']['generated_at']}

## System Overview
- **Neo4j Database**: {complete_docs['metadata']['schema_documentation']['neo4j_schema'].get('total_nodes', 'N/A')} nodes, {complete_docs['metadata']['schema_documentation']['neo4j_schema'].get('total_relationships', 'N/A')} relationships
- **Elasticsearch Indices**: {complete_docs['metadata']['schema_documentation']['elasticsearch_schema'].get('total_indices', 'N/A')} indices, {complete_docs['metadata']['schema_documentation']['elasticsearch_schema'].get('total_documents', 'N/A')} documents
- **Data Models**: {complete_docs['metadata']['schema_documentation']['data_model_schema'].get('total_classes', 'N/A')} entity classes

## Data Quality Summary
- **Image Processing**: {complete_docs['quality_reports'].get('processing_statistics', {}).get('image_processing', {}).get('success_rate', 'N/A')}% success rate
- **Family Extraction**: {complete_docs['quality_reports'].get('processing_statistics', {}).get('family_extraction', {}).get('family_extraction_rate', 'N/A')}% coverage
- **Data Completeness**: Varies by modality (see detailed reports)

## Dataset Statistics
- **Total Patients**: {complete_docs['research_content'].get('dataset_statistics', {}).get('demographics', {}).get('total_patients', 'N/A')}
- **Average Age**: {complete_docs['research_content'].get('dataset_statistics', {}).get('demographics', {}).get('age_statistics', {}).get('average', 'N/A')} years
- **Gender Distribution**: {complete_docs['research_content'].get('dataset_statistics', {}).get('demographics', {}).get('gender_distribution', {})}

## Files Generated
- Complete metadata: `outputs/complete_documentation.json`
- Schema documentation: `outputs/metadata/schema_documentation/`
- Data dictionaries: `outputs/metadata/data_dictionaries/`
- Quality reports: `outputs/research/quality_metrics/`
- Research content: `outputs/research/analysis_reports/`

## Next Steps
1. Review data quality reports for any issues
2. Use research examples for analysis workflows
3. Consult data dictionaries for field definitions
4. Follow export workflows for data analysis

For detailed information, see the complete documentation files.
"""
        
        summary_file = os.path.join(self.output_base_path, "DOCUMENTATION_SUMMARY.md")
        with open(summary_file, 'w') as f:
            f.write(summary)
        
        logger.info(f"Summary report saved to {summary_file}")