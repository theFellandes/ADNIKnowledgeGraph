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
class ImageNode:
    """Individual image with BLOB data"""
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
    dicom_metadata: Dict[str, Any] = field(default_factory=dict)
    image_blob: Optional[bytes] = None  # Actual image data
    thumbnail_blob: Optional[bytes] = None
    file_path: Optional[str] = None  # Original file path
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

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
            'dicom_metadata': self.dicom_metadata,
            'has_blob': self.image_blob is not None,
            'has_thumbnail': self.thumbnail_blob is not None,
            'file_path': self.file_path,
            'created_at': self.created_at
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
class FamilyMember:
    """Family member with dementia history"""
    member_id: str
    patient_id: str
    relationship_type: str  # parent, sibling, child
    gender: Optional[str] = None
    has_dementia: Optional[bool] = None
    dementia_type: Optional[str] = None
    age_at_onset: Optional[int] = None
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            'member_id': self.member_id,
            'patient_id': self.patient_id,
            'relationship_type': self.relationship_type,
            'gender': self.gender,
            'has_dementia': self.has_dementia,
            'dementia_type': self.dementia_type,
            'age_at_onset': self.age_at_onset,
            'properties': self.properties,
            'created_at': self.created_at
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