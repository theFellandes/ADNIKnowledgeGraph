"""
Enhanced Data entity classes for ADNI Knowledge Graph
Based on AD-DPC ontology, AlzKB, and DemKG research insights
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime


# Existing entities (keep all the original ones)
@dataclass
class Patient:
    """Patient entity representing ADNI participant"""
    ptid: str  # Patient ID
    rid: str   # Research ID
    gender: Optional[str] = None
    age_at_baseline: Optional[float] = None
    education_years: Optional[int] = None
    apoe_genotype: Optional[str] = None
    demographic_data: Dict[str, Any] = field(default_factory=dict)
    clinical_data: Dict[str, Any] = field(default_factory=dict)
    source_tables: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'ptid': self.ptid,
            'rid': self.rid,
            'gender': self.gender,
            'age_at_baseline': self.age_at_baseline,
            'education_years': self.education_years,
            'apoe_genotype': self.apoe_genotype,
            'demographic_data': self.demographic_data,
            'clinical_data': self.clinical_data,
            'source_tables': self.source_tables,
            'created_at': self.created_at
        }


@dataclass
class Visit:
    """Visit entity representing a timepoint in patient's journey"""
    visit_id: str
    patient_id: str
    viscode: str  # Visit code (bl, m06, m12, etc.)
    months_from_baseline: int
    visit_date: Optional[str] = None
    visit_type: Optional[str] = None  # screening, baseline, follow-up
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'visit_id': self.visit_id,
            'patient_id': self.patient_id,
            'viscode': self.viscode,
            'months_from_baseline': self.months_from_baseline,
            'visit_date': self.visit_date,
            'visit_type': self.visit_type,
            'created_at': self.created_at
        }


@dataclass
class ImagingStudy:
    """Imaging study entity (MRI or PET)"""
    study_id: str
    patient_id: str
    visit_id: str
    modality: str  # MRI, PET
    study_date: str
    study_description: Optional[str] = None
    scanner_info: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'study_id': self.study_id,
            'patient_id': self.patient_id,
            'visit_id': self.visit_id,
            'modality': self.modality,
            'study_date': self.study_date,
            'study_description': self.study_description,
            'scanner_info': self.scanner_info,
            'created_at': self.created_at
        }


@dataclass
class ImageFilePaths:
    """File paths for different image formats"""
    dicom_path: Optional[str] = None
    png_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'dicom_path': self.dicom_path,
            'png_path': self.png_path,
            'thumbnail_path': self.thumbnail_path
        }


@dataclass
class ImageQualityMetrics:
    """Image quality assessment metrics"""
    psnr: Optional[float] = None  # Peak Signal-to-Noise Ratio
    ssim: Optional[float] = None  # Structural Similarity Index
    mse: Optional[float] = None   # Mean Squared Error
    quality_score: Optional[float] = None  # Overall quality score (0-1)
    validation_passed: bool = True
    validation_notes: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'psnr': self.psnr,
            'ssim': self.ssim,
            'mse': self.mse,
            'quality_score': self.quality_score,
            'validation_passed': self.validation_passed,
            'validation_notes': self.validation_notes
        }


@dataclass
class ImageNode:
    """Enhanced individual image with comprehensive file path management and quality metrics"""
    image_id: str
    study_id: str
    patient_id: str
    visit_id: str
    series_description: str
    image_type: str  # DICOM, PNG, JPG
    anatomical_region: Optional[str] = None
    pet_tracer: Optional[str] = None  # For PET images
    slice_number: Optional[int] = None
    acquisition_parameters: Dict[str, Any] = field(default_factory=dict)
    
    # Enhanced properties for file path management
    file_paths: ImageFilePaths = field(default_factory=ImageFilePaths)
    
    # Enhanced DICOM metadata storage
    dicom_metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Processing status tracking
    processing_status: str = "pending"  # pending, processing, completed, failed
    
    # Quality metrics for validation
    quality_metrics: ImageQualityMetrics = field(default_factory=ImageQualityMetrics)
    
    # Legacy fields for backward compatibility
    image_blob: Optional[bytes] = None  # Actual image data
    thumbnail_blob: Optional[bytes] = None
    file_path: Optional[str] = None  # Original file path - deprecated, use file_paths instead
    
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def update_processing_status(self, status: str, notes: Optional[str] = None):
        """Update processing status with timestamp"""
        self.processing_status = status
        self.updated_at = datetime.now().isoformat()
        if notes and hasattr(self.quality_metrics, 'validation_notes'):
            self.quality_metrics.validation_notes = notes

    def get_display_path(self) -> Optional[str]:
        """Get the best available path for display (PNG preferred, fallback to DICOM)"""
        if self.file_paths.png_path:
            return self.file_paths.png_path
        elif self.file_paths.dicom_path:
            return self.file_paths.dicom_path
        return self.file_path  # Legacy fallback

    def get_thumbnail_path(self) -> Optional[str]:
        """Get thumbnail path"""
        return self.file_paths.thumbnail_path

    def has_all_formats(self) -> bool:
        """Check if all image formats are available"""
        return all([
            self.file_paths.dicom_path,
            self.file_paths.png_path,
            self.file_paths.thumbnail_path
        ])

    def is_processing_complete(self) -> bool:
        """Check if image processing is complete and successful"""
        return (self.processing_status == "completed" and 
                self.quality_metrics.validation_passed and
                self.has_all_formats())

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict, excluding blob data for logging"""
        return {
            'image_id': self.image_id,
            'study_id': self.study_id,
            'patient_id': self.patient_id,
            'visit_id': self.visit_id,
            'series_description': self.series_description,
            'image_type': self.image_type,
            'anatomical_region': self.anatomical_region,
            'pet_tracer': self.pet_tracer,
            'slice_number': self.slice_number,
            'acquisition_parameters': self.acquisition_parameters,
            'file_paths': self.file_paths.to_dict(),
            'dicom_metadata': self.dicom_metadata,
            'processing_status': self.processing_status,
            'quality_metrics': self.quality_metrics.to_dict(),
            'has_blob': self.image_blob is not None,
            'has_thumbnail': self.thumbnail_blob is not None,
            'file_path': self.file_path,  # Legacy field
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


@dataclass
class CognitiveAssessment:
    """Cognitive test result"""
    assessment_id: str
    patient_id: str
    visit_id: str
    test_name: str  # MMSE, CDR, ADAS-Cog, etc.
    test_version: Optional[str] = None
    total_score: Optional[float] = None
    subscores: Dict[str, float] = field(default_factory=dict)
    clinical_significance: Optional[str] = None
    source_table: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'assessment_id': self.assessment_id,
            'patient_id': self.patient_id,
            'visit_id': self.visit_id,
            'test_name': self.test_name,
            'test_version': self.test_version,
            'total_score': self.total_score,
            'subscores': self.subscores,
            'clinical_significance': self.clinical_significance,
            'source_table': self.source_table,
            'created_at': self.created_at
        }


@dataclass
class Biomarker:
    """Biomarker measurement (CSF, blood, etc.)"""
    biomarker_id: str
    patient_id: str
    visit_id: str
    biomarker_type: str  # CSF, blood, genetic
    analyte: str  # Aβ42, tau, p-tau, etc.
    value: float
    unit: str
    specimen_type: Optional[str] = None
    assay_info: Dict[str, Any] = field(default_factory=dict)
    abnormal_flag: Optional[bool] = None
    source_table: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'biomarker_id': self.biomarker_id,
            'patient_id': self.patient_id,
            'visit_id': self.visit_id,
            'biomarker_type': self.biomarker_type,
            'analyte': self.analyte,
            'value': self.value,
            'unit': self.unit,
            'specimen_type': self.specimen_type,
            'assay_info': self.assay_info,
            'abnormal_flag': self.abnormal_flag,
            'source_table': self.source_table,
            'created_at': self.created_at
        }


@dataclass
class Diagnosis:
    """Clinical diagnosis"""
    diagnosis_id: str
    patient_id: str
    visit_id: str
    diagnosis_code: str  # CN, MCI, AD
    diagnosis_text: str
    confidence: Optional[float] = None
    criteria_used: Optional[str] = None
    source_table: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'diagnosis_id': self.diagnosis_id,
            'patient_id': self.patient_id,
            'visit_id': self.visit_id,
            'diagnosis_code': self.diagnosis_code,
            'diagnosis_text': self.diagnosis_text,
            'confidence': self.confidence,
            'criteria_used': self.criteria_used,
            'source_table': self.source_table,
            'created_at': self.created_at
        }


@dataclass
class FamilyMemberDemographics:
    """Demographics for family members"""
    age: Optional[int] = None
    birth_year: Optional[int] = None
    education_years: Optional[int] = None
    occupation: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'age': self.age,
            'birth_year': self.birth_year,
            'education_years': self.education_years,
            'occupation': self.occupation
        }


@dataclass
class ADStatus:
    """Alzheimer's Disease status for family members"""
    has_ad: Optional[bool] = None
    ad_type: Optional[str] = None  # early_onset, late_onset, familial
    age_at_onset: Optional[int] = None
    age_at_diagnosis: Optional[int] = None
    severity: Optional[str] = None  # mild, moderate, severe
    current_status: Optional[str] = None  # living_with_ad, deceased, unknown
    confidence_level: Optional[str] = None  # confirmed, probable, possible, family_report
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'has_ad': self.has_ad,
            'ad_type': self.ad_type,
            'age_at_onset': self.age_at_onset,
            'age_at_diagnosis': self.age_at_diagnosis,
            'severity': self.severity,
            'current_status': self.current_status,
            'confidence_level': self.confidence_level
        }


@dataclass
class FamilyMember:
    """Enhanced family member with comprehensive AD status and demographic tracking"""
    member_id: str
    patient_id: str
    relationship_type: str  # parent, sibling, child, grandparent, aunt, uncle, cousin
    gender: Optional[str] = None
    
    # Enhanced AD status tracking
    ad_status: ADStatus = field(default_factory=ADStatus)
    
    # Demographics
    demographics: FamilyMemberDemographics = field(default_factory=FamilyMemberDemographics)
    
    # Additional properties
    properties: Dict[str, Any] = field(default_factory=dict)
    
    # Legacy fields for backward compatibility
    has_dementia: Optional[bool] = None
    dementia_type: Optional[str] = None
    age_at_onset: Optional[int] = None
    
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        """Initialize legacy fields from new structure if needed"""
        if self.has_dementia is not None and self.ad_status.has_ad is None:
            self.ad_status.has_ad = self.has_dementia
        if self.dementia_type is not None and self.ad_status.ad_type is None:
            self.ad_status.ad_type = self.dementia_type
        if self.age_at_onset is not None and self.ad_status.age_at_onset is None:
            self.ad_status.age_at_onset = self.age_at_onset

    def validate_relationship_type(self) -> bool:
        """Validate that relationship type is valid"""
        valid_types = {
            'parent', 'mother', 'father',
            'sibling', 'brother', 'sister',
            'child', 'son', 'daughter',
            'grandparent', 'grandmother', 'grandfather',
            'aunt', 'uncle', 'cousin'
        }
        return self.relationship_type.lower() in valid_types

    def validate_constraints(self) -> Tuple[bool, List[str]]:
        """Validate family member data constraints"""
        errors = []
        
        if not self.validate_relationship_type():
            errors.append(f"Invalid relationship type: {self.relationship_type}")
        
        if self.ad_status.age_at_onset and self.ad_status.age_at_diagnosis:
            if self.ad_status.age_at_onset > self.ad_status.age_at_diagnosis:
                errors.append("Age at onset cannot be greater than age at diagnosis")
        
        if self.demographics.age and self.ad_status.age_at_onset:
            if self.ad_status.age_at_onset > self.demographics.age:
                errors.append("Age at onset cannot be greater than current age")
        
        return len(errors) == 0, errors

    def get_relationship_category(self) -> str:
        """Get broad relationship category"""
        relationship_map = {
            'parent': ['parent', 'mother', 'father'],
            'sibling': ['sibling', 'brother', 'sister'],
            'child': ['child', 'son', 'daughter'],
            'grandparent': ['grandparent', 'grandmother', 'grandfather'],
            'extended': ['aunt', 'uncle', 'cousin']
        }
        
        for category, types in relationship_map.items():
            if self.relationship_type.lower() in types:
                return category
        return 'other'

    def has_ad_diagnosis(self) -> bool:
        """Check if family member has confirmed AD diagnosis"""
        return (self.ad_status.has_ad is True and 
                self.ad_status.confidence_level in ['confirmed', 'probable'])

    def get_genetic_risk_contribution(self) -> float:
        """Calculate genetic risk contribution based on relationship and AD status"""
        if not self.has_ad_diagnosis():
            return 0.0
        
        # Risk weights based on relationship closeness and genetic contribution
        risk_weights = {
            'parent': 0.3,
            'sibling': 0.25,
            'child': 0.25,
            'grandparent': 0.1,
            'extended': 0.05
        }
        
        base_risk = risk_weights.get(self.get_relationship_category(), 0.0)
        
        # Adjust for early onset (higher genetic component)
        if (self.ad_status.age_at_onset and 
            self.ad_status.age_at_onset < 65):
            base_risk *= 1.5
        
        return min(base_risk, 1.0)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with only primitive types for Neo4j storage"""
        # Extract primitive values from complex objects
        result = {
            'member_id': self.member_id,
            'patient_id': self.patient_id,
            'relationship_type': self.relationship_type,
            'gender': self.gender,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }
        
        # Add legacy fields (primitive types only)
        if self.has_dementia is not None:
            result['has_dementia'] = self.has_dementia
        if self.dementia_type is not None:
            result['dementia_type'] = self.dementia_type
        if self.age_at_onset is not None:
            result['age_at_onset'] = self.age_at_onset
        
        # Extract primitive values from ad_status
        if self.ad_status.has_ad is not None:
            result['ad_status_has_ad'] = self.ad_status.has_ad
        if self.ad_status.ad_type is not None:
            result['ad_status_type'] = self.ad_status.ad_type
        if self.ad_status.age_at_onset is not None:
            result['ad_status_age_at_onset'] = self.ad_status.age_at_onset
        if self.ad_status.age_at_diagnosis is not None:
            result['ad_status_age_at_diagnosis'] = self.ad_status.age_at_diagnosis
        if self.ad_status.confidence_level is not None:
            result['ad_status_confidence'] = self.ad_status.confidence_level
        if self.ad_status.current_status is not None:
            result['ad_status_current'] = self.ad_status.current_status
        if self.ad_status.severity is not None:
            result['ad_status_severity'] = self.ad_status.severity
        
        # Extract primitive values from demographics
        if self.demographics.age is not None:
            result['demographics_age'] = self.demographics.age
        if self.demographics.birth_year is not None:
            result['demographics_birth_year'] = self.demographics.birth_year
        if self.demographics.education_years is not None:
            result['demographics_education'] = self.demographics.education_years
        if self.demographics.occupation is not None:
            result['demographics_occupation'] = self.demographics.occupation
        
        # Add primitive properties only
        if self.properties:
            for key, value in self.properties.items():
                # Only include primitive types
                if isinstance(value, (str, int, float, bool)) or value is None:
                    result[f'prop_{key}'] = value
        
        return result

    def build_family_tree_connections(self, all_family_members: List['FamilyMember']) -> Dict[str, List[str]]:
        """Build connections to other family members for family tree construction"""
        connections = {
            'parents': [],
            'siblings': [],
            'children': [],
            'extended': []
        }
        
        for member in all_family_members:
            if member.member_id == self.member_id:
                continue
                
            # Logic to determine relationships between family members
            # This is simplified - in practice would need more complex relationship inference
            member_category = member.get_relationship_category()
            if member_category in connections:
                connections[member_category].append(member.member_id)
        
        return connections

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            'member_id': self.member_id,
            'patient_id': self.patient_id,
            'relationship_type': self.relationship_type,
            'gender': self.gender,
            'ad_status': self.ad_status.to_dict(),
            'demographics': self.demographics.to_dict(),
            'properties': self.properties,
            'relationship_category': self.get_relationship_category(),
            'has_ad_diagnosis': self.has_ad_diagnosis(),
            'genetic_risk_contribution': self.get_genetic_risk_contribution(),
            # Legacy fields
            'has_dementia': self.has_dementia,
            'dementia_type': self.dementia_type,
            'age_at_onset': self.age_at_onset,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }


@dataclass
class VolumetricMeasure:
    """Brain volumetric measurement from MRI"""
    measure_id: str
    image_id: str
    patient_id: str
    visit_id: str
    region: str  # hippocampus, ventricles, etc.
    volume: float
    unit: str = "mm³"
    hemisphere: Optional[str] = None  # left, right, bilateral
    processing_method: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'measure_id': self.measure_id,
            'image_id': self.image_id,
            'patient_id': self.patient_id,
            'visit_id': self.visit_id,
            'region': self.region,
            'volume': self.volume,
            'unit': self.unit,
            'hemisphere': self.hemisphere,
            'processing_method': self.processing_method,
            'created_at': self.created_at
        }


@dataclass
class PETBinding:
    """PET tracer binding measurement"""
    binding_id: str
    image_id: str
    patient_id: str
    visit_id: str
    tracer: str  # FDG, AV45, AV1451, etc.
    region: str
    suvr: float  # Standardized uptake value ratio
    reference_region: Optional[str] = None
    abnormal_flag: Optional[bool] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'binding_id': self.binding_id,
            'image_id': self.image_id,
            'patient_id': self.patient_id,
            'visit_id': self.visit_id,
            'tracer': self.tracer,
            'region': self.region,
            'suvr': self.suvr,
            'reference_region': self.reference_region,
            'abnormal_flag': self.abnormal_flag,
            'created_at': self.created_at
        }


# NEW ENTITIES BASED ON RESEARCH PAPERS

@dataclass
class BiologicalPathway:
    """Biological pathway involved in AD pathophysiology (from AlzKB)"""
    pathway_id: str
    name: str
    category: str  # amyloid, tau, neuroinflammation, synaptic, metabolic
    description: Optional[str] = None
    genes: List[str] = field(default_factory=list)
    proteins: List[str] = field(default_factory=list)
    kegg_id: Optional[str] = None
    go_terms: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'pathway_id': self.pathway_id,
            'name': self.name,
            'category': self.category,
            'description': self.description,
            'genes': self.genes,
            'proteins': self.proteins,
            'kegg_id': self.kegg_id,
            'go_terms': self.go_terms,
            'created_at': self.created_at
        }


@dataclass
class DataSource:
    """Data source/provenance tracking (from DemKG)"""
    source_id: str
    name: str
    type: str  # database, publication, clinical_trial, registry
    version: Optional[str] = None
    url: Optional[str] = None
    citation: Optional[str] = None
    last_updated: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'source_id': self.source_id,
            'name': self.name,
            'type': self.type,
            'version': self.version,
            'url': self.url,
            'citation': self.citation,
            'last_updated': self.last_updated,
            'metadata': self.metadata,
            'created_at': self.created_at
        }


@dataclass
class BiomarkerType:
    """Biomarker classification and metadata (from AD-DPC)"""
    type_id: str
    name: str
    category: str  # amyloid, tau, neurodegeneration, inflammation, synaptic
    specimen_type: str  # CSF, blood, imaging
    measurement_unit: str
    normal_range_min: Optional[float] = None
    normal_range_max: Optional[float] = None
    clinical_significance: Optional[str] = None
    references: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'type_id': self.type_id,
            'name': self.name,
            'category': self.category,
            'specimen_type': self.specimen_type,
            'measurement_unit': self.measurement_unit,
            'normal_range_min': self.normal_range_min,
            'normal_range_max': self.normal_range_max,
            'clinical_significance': self.clinical_significance,
            'references': self.references,
            'created_at': self.created_at
        }


@dataclass
class GeneticRiskProfile:
    """Comprehensive genetic risk assessment"""
    profile_id: str
    patient_id: str
    apoe_status: str  # e2/e2, e2/e3, e2/e4, e3/e3, e3/e4, e4/e4
    apoe_risk_category: str  # low, medium, high, very_high
    polygenic_risk_score: Optional[float] = None
    rare_variants: List[Dict[str, Any]] = field(default_factory=list)
    other_risk_genes: Dict[str, Any] = field(default_factory=dict)  # TREM2, APP, PSEN1, etc.
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'profile_id': self.profile_id,
            'patient_id': self.patient_id,
            'apoe_status': self.apoe_status,
            'apoe_risk_category': self.apoe_risk_category,
            'polygenic_risk_score': self.polygenic_risk_score,
            'rare_variants': self.rare_variants,
            'other_risk_genes': self.other_risk_genes,
            'created_at': self.created_at
        }


@dataclass
class MultimodalSession:
    """Multimodal assessment session combining multiple data types"""
    session_id: str
    patient_id: str
    visit_id: str
    session_date: str
    modalities: List[str]  # cognitive, biomarker, imaging, clinical
    cognitive_tests: List[str] = field(default_factory=list)
    biomarkers_collected: List[str] = field(default_factory=list)
    imaging_performed: List[str] = field(default_factory=list)
    completeness_score: Optional[float] = None  # 0-1 scale
    notes: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'session_id': self.session_id,
            'patient_id': self.patient_id,
            'visit_id': self.visit_id,
            'session_date': self.session_date,
            'modalities': self.modalities,
            'cognitive_tests': self.cognitive_tests,
            'biomarkers_collected': self.biomarkers_collected,
            'imaging_performed': self.imaging_performed,
            'completeness_score': self.completeness_score,
            'notes': self.notes,
            'created_at': self.created_at
        }


@dataclass
class ProcessingActivity:
    """Data processing provenance tracking"""
    activity_id: str
    activity_type: str  # image_processing, score_calculation, quality_control
    software_used: str
    version: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    input_data: List[str] = field(default_factory=list)  # IDs of input entities
    output_data: List[str] = field(default_factory=list)  # IDs of output entities
    processing_date: str = field(default_factory=lambda: datetime.now().isoformat())
    operator: Optional[str] = None
    quality_metrics: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'activity_id': self.activity_id,
            'activity_type': self.activity_type,
            'software_used': self.software_used,
            'version': self.version,
            'parameters': self.parameters,
            'input_data': self.input_data,
            'output_data': self.output_data,
            'processing_date': self.processing_date,
            'operator': self.operator,
            'quality_metrics': self.quality_metrics,
            'created_at': self.created_at
        }


@dataclass
class DrugTreatment:
    """Drug treatment information (inspired by AlzKB)"""
    treatment_id: str
    patient_id: str
    drug_name: str
    drug_class: str  # cholinesterase_inhibitor, nmda_antagonist, etc.
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    dosage: Optional[str] = None
    response: Optional[str] = None  # positive, negative, no_change
    side_effects: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'treatment_id': self.treatment_id,
            'patient_id': self.patient_id,
            'drug_name': self.drug_name,
            'drug_class': self.drug_class,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'dosage': self.dosage,
            'response': self.response,
            'side_effects': self.side_effects,
            'created_at': self.created_at
        }


@dataclass
class ClinicalTrial:
    """Clinical trial participation"""
    trial_id: str
    patient_id: str
    trial_name: str
    nct_number: Optional[str] = None  # ClinicalTrials.gov ID
    enrollment_date: Optional[str] = None
    trial_arm: Optional[str] = None  # treatment, placebo, control
    status: Optional[str] = None  # enrolled, completed, withdrawn
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'trial_id': self.trial_id,
            'patient_id': self.patient_id,
            'trial_name': self.trial_name,
            'nct_number': self.nct_number,
            'enrollment_date': self.enrollment_date,
            'trial_arm': self.trial_arm,
            'status': self.status,
            'created_at': self.created_at
        }


@dataclass
class LifestyleFactor:
    """Lifestyle and environmental factors"""
    factor_id: str
    patient_id: str
    factor_type: str  # diet, exercise, sleep, social, cognitive_activity
    description: str
    frequency: Optional[str] = None  # daily, weekly, monthly
    duration: Optional[str] = None
    impact_score: Optional[float] = None  # Potential impact on AD risk
    source: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'factor_id': self.factor_id,
            'patient_id': self.patient_id,
            'factor_type': self.factor_type,
            'description': self.description,
            'frequency': self.frequency,
            'duration': self.duration,
            'impact_score': self.impact_score,
            'source': self.source,
            'created_at': self.created_at
        }