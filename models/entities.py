"""
Data entity classes for ADNI Knowledge Graph
Based on AD-DPC ontology and enhanced with NIDM concepts
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime


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