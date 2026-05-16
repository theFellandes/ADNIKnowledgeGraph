"""
Step 15: Event-Based Graph Model for AD Progression
Models Alzheimer's disease progression as temporal events rather than static entities
Based on AlzKB and AD-DPC ontology approaches
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from collections import defaultdict
import uuid

from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


class EventBasedModelBuilder:
    """
    Builds an event-based graph model for AD progression
    Implements temporal event chains and state transitions
    """

    def __init__(self, connector: Neo4jConnector):
        self.connector = connector
        self.events_created = 0
        self.event_chains_created = 0
        self.state_transitions_created = 0

        # Event type definitions based on AD progression
        self.event_types = {
            'DIAGNOSIS_CHANGE': 'Clinical diagnosis transition',
            'BIOMARKER_CHANGE': 'Biomarker status change',
            'COGNITIVE_DECLINE': 'Cognitive score decline',
            'IMAGING_FINDING': 'New imaging finding',
            'SYMPTOM_ONSET': 'Symptom first appearance',
            'TREATMENT_START': 'Treatment initiation',
            'TREATMENT_END': 'Treatment termination',
            'STUDY_MILESTONE': 'Study enrollment/completion',
            'ATN_TRANSITION': 'ATN profile change',
            'CONVERSION': 'Disease stage conversion'
        }

        # State definitions for AD progression
        self.disease_states = {
            'HEALTHY': 'Cognitively normal',
            'SCD': 'Subjective cognitive decline',
            'MCI': 'Mild cognitive impairment',
            'DEMENTIA': 'Dementia',
            'AD': 'Alzheimer\'s disease'
        }

    def execute(self) -> Dict[str, Any]:
        """Execute event-based model creation"""

        logger.info("\n" + "=" * 70)
        logger.info("CREATING EVENT-BASED AD PROGRESSION MODEL")
        logger.info("=" * 70)

        results = {
            'events_created': 0,
            'event_chains': 0,
            'state_transitions': 0,
            'patient_timelines': 0,
            'event_correlations': 0
        }

        try:
            # 1. Create Event Type Ontology
            self._create_event_ontology()

            # 2. Extract Clinical Events
            clinical_events = self._extract_clinical_events()
            results['clinical_events'] = clinical_events

            # 3. Extract Biomarker Events
            biomarker_events = self._extract_biomarker_events()
            results['biomarker_events'] = biomarker_events

            # 4. Extract Cognitive Events
            cognitive_events = self._extract_cognitive_events()
            results['cognitive_events'] = cognitive_events

            # 5. Extract Imaging Events
            imaging_events = self._extract_imaging_events()
            results['imaging_events'] = imaging_events

            # 6. Create Event Sequences
            sequences = self._create_event_sequences()
            results['event_chains'] = sequences

            # 7. Create State Transition Network
            transitions = self._create_state_transitions()
            results['state_transitions'] = transitions

            # 8. Build Patient Timelines
            timelines = self._build_patient_timelines()
            results['patient_timelines'] = timelines

            # 9. Identify Event Patterns
            patterns = self._identify_event_patterns()
            results['event_patterns'] = patterns

            # 10. Create Causal Relationships
            causal = self._create_causal_relationships()
            results['causal_relationships'] = causal

            # 11. Calculate Event Statistics
            stats = self._calculate_event_statistics()
            results['statistics'] = stats

            results['events_created'] = self.events_created

            logger.info(f"\n✅ Event-Based Model Complete:")
            logger.info(f"   Total events created: {self.events_created}")
            logger.info(f"   Event chains: {results['event_chains']}")
            logger.info(f"   State transitions: {results['state_transitions']}")
            logger.info(f"   Patient timelines: {results['patient_timelines']}")

            return results

        except Exception as e:
            logger.error(f"Event model creation failed: {e}")
            results['error'] = str(e)
            return results

    def _create_event_ontology(self) -> int:
        """Create event type nodes and hierarchy - FIXED AGGREGATION"""

        # Create event types
        create_types_query = """
        // Create clinical events
        MERGE (clinical:EventType {
            type_id: 'clinical_event',
            name: 'Clinical Event',
            category: 'clinical',
            level: 1
        })

        MERGE (diagnosis_evt:EventType {
            type_id: 'diagnosis_event',
            name: 'Diagnosis Event',
            category: 'clinical',
            level: 2
        })

        MERGE (cognitive_evt:EventType {
            type_id: 'cognitive_event',
            name: 'Cognitive Assessment Event',
            category: 'clinical',
            level: 2
        })

        MERGE (biomarker_evt:EventType {
            type_id: 'biomarker_event',
            name: 'Biomarker Event',
            category: 'clinical',
            level: 2
        })

        MERGE (imaging_evt:EventType {
            type_id: 'imaging_event',
            name: 'Imaging Event',
            category: 'imaging',
            level: 2
        })

        MERGE (treatment_evt:EventType {
            type_id: 'treatment_event',
            name: 'Treatment Event',
            category: 'intervention',
            level: 2
        })
        """

        self.connector.execute_write_transaction(create_types_query)

        # Create hierarchies
        hierarchy_query = """
        MATCH (parent:EventType {type_id: 'clinical_event'})
        MATCH (child:EventType)
        WHERE child.type_id IN ['diagnosis_event', 'cognitive_event', 'biomarker_event']
        MERGE (parent)-[:HAS_SUBTYPE]->(child)
        RETURN count(*) as relationships_created
        """

        result = self.connector.run_query(hierarchy_query)

        # Create specific event subtypes
        subtypes_query = """
        // Diagnosis subtypes
        MERGE (cn_dx:EventType {
            type_id: 'diagnosis_cn',
            name: 'CN Diagnosis',
            category: 'diagnosis',
            level: 3
        })

        MERGE (mci_dx:EventType {
            type_id: 'diagnosis_mci',
            name: 'MCI Diagnosis',
            category: 'diagnosis',
            level: 3
        })

        MERGE (ad_dx:EventType {
            type_id: 'diagnosis_ad',
            name: 'AD Diagnosis',
            category: 'diagnosis',
            level: 3
        })

        // Biomarker subtypes
        MERGE (csf_evt:EventType {
            type_id: 'csf_biomarker',
            name: 'CSF Biomarker',
            category: 'biomarker',
            level: 3
        })

        MERGE (pet_evt:EventType {
            type_id: 'pet_biomarker',
            name: 'PET Biomarker',
            category: 'biomarker',
            level: 3
        })
        """

        self.connector.execute_write_transaction(subtypes_query)

        # FIXED: Link subtypes to their parents - properly handle aggregation
        link_subtypes_query = """
        // Link diagnosis subtypes
        MATCH (parent:EventType {type_id: 'diagnosis_event'})
        MATCH (child:EventType)
        WHERE child.type_id IN ['diagnosis_cn', 'diagnosis_mci', 'diagnosis_ad']
        MERGE (parent)-[:HAS_SUBTYPE]->(child)
        WITH count(*) as dx_links

        // Link biomarker subtypes
        MATCH (parent:EventType {type_id: 'biomarker_event'})
        MATCH (child:EventType)
        WHERE child.type_id IN ['csf_biomarker', 'pet_biomarker']
        MERGE (parent)-[:HAS_SUBTYPE]->(child)
        WITH dx_links, count(*) as bio_links

        RETURN dx_links + bio_links as total_links
        """

        result = self.connector.run_query(link_subtypes_query)

        # Count total event types created
        count_query = """
        MATCH (evt:EventType)
        RETURN count(evt) as count
        """

        result = self.connector.run_query(count_query)
        return result[0]['count'] if result else 0

    def _extract_clinical_events(self) -> int:
        """Extract clinical events from diagnosis changes"""

        logger.info("Extracting clinical events...")

        query = """
        // Find diagnosis changes for each patient
        MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        WITH p, v, d
        ORDER BY p.ptid, v.months_from_baseline

        // Group by patient and create diagnosis sequence
        WITH p, collect({
            visit: v,
            diagnosis: d,
            months: v.months_from_baseline
        }) as diagnosis_sequence
        WHERE size(diagnosis_sequence) > 1

        // Process each patient's diagnosis changes
        UNWIND range(0, size(diagnosis_sequence)-2) as i
        WITH p, 
             diagnosis_sequence[i] as current,
             diagnosis_sequence[i+1] as next
        WHERE current.diagnosis.diagnosis_code <> next.diagnosis.diagnosis_code

        // Create diagnosis change event
        MERGE (e:Event:ClinicalEvent {event_id: p.ptid + '_dx_change_' + toString(current.months) + '_to_' + toString(next.months)})
        ON CREATE SET e.created_at = datetime()
        SET e.event_type = 'DIAGNOSIS_CHANGE',
            e.patient_id = p.ptid,
            e.timestamp = next.visit.visit_date,
            e.months_from_baseline = next.months,
            e.from_state = current.diagnosis.diagnosis_code,
            e.to_state = next.diagnosis.diagnosis_code,
            e.transition = current.diagnosis.diagnosis_code + '_to_' + next.diagnosis.diagnosis_code,
            e.duration_months = next.months - current.months,
            e.updated_at = datetime()

        // Link to patient and visits
        MERGE (p)-[:EXPERIENCED_EVENT]->(e)
        MERGE (current.visit)-[:PRECEDED_EVENT]->(e)
        MERGE (e)-[:OCCURRED_AT]->(next.visit)
        MERGE (current.diagnosis)-[:TRANSITIONED_TO {via_event: e.event_id}]->(next.diagnosis)

        RETURN count(e) as events_created
        """

        result = self.connector.run_query(query)
        count = result[0]['events_created'] if result else 0
        self.events_created += count

        # Extract symptom onset events
        symptom_query = """
        // Find first occurrence of symptoms
        MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
        WHERE ca.clinical_significance IN ['mild_impairment', 'moderate_impairment', 'severe_impairment']
        WITH p, ca, v
        ORDER BY v.months_from_baseline
        WITH p, collect({assessment: ca, visit: v})[0] as first_impairment

        MERGE (e:Event:ClinicalEvent {event_id: p.ptid + '_symptom_onset_' + first_impairment.assessment.test_name})
        ON CREATE SET e.created_at = datetime()
        SET e.event_type = 'SYMPTOM_ONSET',
            e.patient_id = p.ptid,
            e.timestamp = first_impairment.visit.visit_date,
            e.months_from_baseline = first_impairment.visit.months_from_baseline,
            e.symptom_type = 'cognitive_impairment',
            e.test_name = first_impairment.assessment.test_name,
            e.severity = first_impairment.assessment.clinical_significance,
            e.updated_at = datetime()

        MERGE (p)-[:EXPERIENCED_EVENT]->(e)
        MERGE (e)-[:DETECTED_BY]->(first_impairment.assessment)

        RETURN count(e) as events_created
        """

        result = self.connector.run_query(symptom_query)
        if result:
            count = result[0]['events_created']
            self.events_created += count

        return self.events_created

    def _extract_biomarker_events(self) -> int:
        """Extract biomarker change events"""

        logger.info("Extracting biomarker events...")

        query = """
        // Find biomarker status changes
        MATCH (p:Patient)-[:HAS_BIOMARKER]->(b:Biomarker)
        WITH p, b
        ORDER BY p.ptid, b.viscode

        // Group by patient and analyte
        WITH p, b.analyte as analyte, collect(b) as biomarkers
        WHERE size(biomarkers) > 1

        // Process each biomarker sequence
        UNWIND range(0, size(biomarkers)-2) as i
        WITH p, analyte,
             biomarkers[i] as current,
             biomarkers[i+1] as next
        WHERE current.abnormal_flag <> next.abnormal_flag

        // Create biomarker change event
        MERGE (e:Event:BiomarkerEvent {event_id: p.ptid + '_bio_change_' + analyte + '_' + current.viscode})
        ON CREATE SET e.created_at = datetime()
        SET e.event_type = 'BIOMARKER_CHANGE',
            e.patient_id = p.ptid,
            e.analyte = analyte,
            e.from_status = CASE WHEN current.abnormal_flag THEN 'abnormal' ELSE 'normal' END,
            e.to_status = CASE WHEN next.abnormal_flag THEN 'abnormal' ELSE 'normal' END,
            e.from_value = current.value,
            e.to_value = next.value,
            e.change_magnitude = next.value - current.value,
            e.viscode = next.viscode,
            e.updated_at = datetime()

        MERGE (p)-[:EXPERIENCED_EVENT]->(e)
        MERGE (current)-[:CHANGED_TO {via_event: e.event_id}]->(next)

        RETURN count(e) as events_created
        """

        result = self.connector.run_query(query)
        count = result[0]['events_created'] if result else 0
        self.events_created += count

        # Extract ATN transition events
        atn_query = """
        // Find ATN profile changes
        MATCH (p:Patient)-[:HAS_ATN_PROFILE]->(atn:ATNProfile)
        WHERE atn.profile IS NOT NULL

        // Create ATN transition event based on profile
        WITH p, atn,
             CASE 
                WHEN atn.profile = 'A+/T+/N+' THEN 'full_ad_pathology'
                WHEN atn.profile = 'A+/T+/N-' THEN 'ad_pathologic_change'
                WHEN atn.profile = 'A+/T-/N-' THEN 'preclinical_ad'
                WHEN atn.profile = 'A-/T+/N+' THEN 'non_ad_pathology'
                ELSE 'other'
             END as atn_stage

        MERGE (e:Event:BiomarkerEvent {event_id: p.ptid + '_atn_transition_' + atn_stage})
        ON CREATE SET e.created_at = datetime()
        SET e.event_type = 'ATN_TRANSITION',
            e.patient_id = p.ptid,
            e.atn_profile = atn.profile,
            e.atn_stage = atn_stage,
            e.amyloid_status = atn.a_status,
            e.tau_status = atn.t_status,
            e.neurodegeneration_status = atn.n_status,
            e.updated_at = datetime()

        MERGE (p)-[:EXPERIENCED_EVENT]->(e)
        MERGE (atn)-[:REPRESENTS_EVENT]->(e)

        RETURN count(e) as events_created
        """

        result = self.connector.run_query(atn_query)
        if result:
            count = result[0]['events_created']
            self.events_created += count

        return self.events_created

    def _extract_cognitive_events(self) -> int:
        """Extract cognitive decline events"""

        logger.info("Extracting cognitive events...")

        query = """
        // Find significant cognitive score declines
        MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
        WHERE ca.test_name IN ['MMSE', 'CDR', 'ADAS-Cog']
        WITH p, ca.test_name as test, collect({
            assessment: ca,
            visit: v,
            score: ca.total_score,
            months: v.months_from_baseline
        }) as assessments
        WHERE size(assessments) >= 2

        // Order assessments by time
        WITH p, test, assessments
        UNWIND range(0, size(assessments)-2) as i
        WITH p, test,
             assessments[i] as baseline,
             assessments[i+1] as followup

        // Calculate decline based on test type
        WITH p, test, baseline, followup,
             CASE test
                WHEN 'MMSE' THEN baseline.score - followup.score
                WHEN 'CDR' THEN followup.score - baseline.score
                WHEN 'ADAS-Cog' THEN followup.score - baseline.score
                ELSE 0
             END as decline,
             CASE test
                WHEN 'MMSE' THEN 3.0
                WHEN 'CDR' THEN 0.5
                WHEN 'ADAS-Cog' THEN 4.0
                ELSE 999
             END as threshold
        WHERE decline >= threshold

        // Create cognitive decline event
        MERGE (e:Event:CognitiveEvent {event_id: p.ptid + '_cog_decline_' + test + '_' + toString(followup.months)})
        ON CREATE SET e.created_at = datetime()
        SET e.event_type = 'COGNITIVE_DECLINE',
            e.patient_id = p.ptid,
            e.test_name = test,
            e.baseline_score = baseline.score,
            e.followup_score = followup.score,
            e.decline_amount = decline,
            e.months_between = followup.months - baseline.months,
            e.months_from_baseline = followup.months,
            e.severity = CASE
                WHEN decline >= threshold * 2 THEN 'severe'
                WHEN decline >= threshold * 1.5 THEN 'moderate'
                ELSE 'mild'
            END,
            e.updated_at = datetime()

        MERGE (p)-[:EXPERIENCED_EVENT]->(e)
        MERGE (baseline.assessment)-[:PRECEDED_DECLINE]->(e)
        MERGE (e)-[:DETECTED_IN]->(followup.assessment)

        RETURN count(e) as events_created
        """

        result = self.connector.run_query(query)
        count = result[0]['events_created'] if result else 0
        self.events_created += count

        return count

    def _extract_imaging_events(self) -> int:
        """Extract imaging-based events"""

        logger.info("Extracting imaging events...")

        # Create events for significant imaging findings
        query = """
        // Find PET positivity events
        MATCH (p:Patient)-[:HAS_IMAGE]->(i:ImageNode)
        WHERE i.modality = 'PET' AND i.pet_tracer IN ['AV45', 'FBB', 'PIB']
        WITH p, i
        ORDER BY p.ptid, i.study_date
        WITH p, collect(i)[0] as first_pet

        MERGE (e:Event:ImagingEvent {event_id: p.ptid + '_pet_scan_' + first_pet.image_hash})
        ON CREATE SET e.created_at = datetime()
        SET e.event_type = 'IMAGING_FINDING',
            e.patient_id = p.ptid,
            e.modality = 'PET',
            e.tracer = first_pet.pet_tracer,
            e.finding = 'amyloid_pet_performed',
            e.study_date = first_pet.study_date,
            e.image_id = first_pet.image_id,
            e.updated_at = datetime()

        MERGE (p)-[:EXPERIENCED_EVENT]->(e)
        MERGE (first_pet)-[:REPRESENTS_EVENT]->(e)

        RETURN count(e) as events_created
        """

        result = self.connector.run_query(query)
        count = result[0]['events_created'] if result else 0
        self.events_created += count

        # Create events for volumetric changes
        volume_query = """
        // Find significant hippocampal volume loss
        MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_VOLUMETRIC_MEASURE]->(vm:VolumetricMeasure)
        WHERE vm.region CONTAINS 'Hippocampus'
        WITH p, collect({
            measure: vm,
            visit: v,
            volume: vm.volume,
            months: v.months_from_baseline
        }) as volumes
        WHERE size(volumes) >= 2

        // Calculate volume change
        WITH p, volumes[0] as baseline, volumes[-1] as followup
        WHERE followup.months > baseline.months
        WITH p, baseline, followup,
             (baseline.volume - followup.volume) / baseline.volume * 100 as percent_loss
        WHERE percent_loss > 5  // Significant if >5% loss

        MERGE (e:Event:ImagingEvent {event_id: p.ptid + '_hippocampal_atrophy_' + toString(followup.months)})
        ON CREATE SET e.created_at = datetime()
        SET e.event_type = 'IMAGING_FINDING',
            e.patient_id = p.ptid,
            e.finding = 'hippocampal_atrophy',
            e.baseline_volume = baseline.volume,
            e.followup_volume = followup.volume,
            e.percent_loss = percent_loss,
            e.months_between = followup.months - baseline.months,
            e.severity = CASE
                WHEN percent_loss > 15 THEN 'severe'
                WHEN percent_loss > 10 THEN 'moderate'
                ELSE 'mild'
            END,
            e.updated_at = datetime()

        MERGE (p)-[:EXPERIENCED_EVENT]->(e)
        MERGE (baseline.measure)-[:PRECEDED_ATROPHY]->(e)
        MERGE (e)-[:MEASURED_IN]->(followup.measure)

        RETURN count(e) as events_created
        """

        result = self.connector.run_query(volume_query)
        if result:
            count = result[0]['events_created']
            self.events_created += count

        return self.events_created

    def _create_event_sequences(self) -> int:
        """Create temporal sequences of events"""

        logger.info("Creating event sequences...")

        query = """
        // Create event chains for each patient
        MATCH (p:Patient)-[:EXPERIENCED_EVENT]->(e:Event)
        WITH p, e
        ORDER BY p.ptid, e.months_from_baseline, e.timestamp

        // Group events by patient
        WITH p, collect(e) as patient_events
        WHERE size(patient_events) > 1

        // Create event chain
        MERGE (ec:EventChain {chain_id: p.ptid + '_event_chain'})
        ON CREATE SET ec.created_at = datetime()
        SET ec.patient_id = p.ptid,
            ec.event_count = size(patient_events),
            ec.start_event = patient_events[0].event_type,
            ec.end_event = patient_events[-1].event_type,
            ec.duration_months = patient_events[-1].months_from_baseline - patient_events[0].months_from_baseline,
            ec.updated_at = datetime()

        MERGE (p)-[:HAS_EVENT_CHAIN]->(ec)

        WITH ec, patient_events
        UNWIND range(0, size(patient_events)-1) as i
        WITH ec, patient_events[i] as event, i
        MERGE (event)-[:PART_OF_CHAIN {sequence: i}]->(ec)

        RETURN count(DISTINCT ec) as chains_created
        """

        result = self.connector.run_query(query)
        chain_count = result[0]['chains_created'] if result else 0

        # Create temporal relationships between consecutive events
        temporal_query = """
        MATCH (p:Patient)-[:EXPERIENCED_EVENT]->(e1:Event)
        MATCH (p)-[:EXPERIENCED_EVENT]->(e2:Event)
        WHERE e1.months_from_baseline < e2.months_from_baseline
        WITH e1, e2, e2.months_from_baseline - e1.months_from_baseline as months_between
        ORDER BY e1.event_id, months_between
        WITH e1, collect({event: e2, months: months_between})[0] as next_event
        WHERE next_event IS NOT NULL

        MERGE (e1)-[r:FOLLOWED_BY {
            months_between: next_event.months,
            sequence_type: 'temporal'
        }]->(next_event.event)

        RETURN count(r) as relationships_created
        """

        result = self.connector.run_query(temporal_query)

        return chain_count

    def _create_state_transitions(self) -> int:
        """Create state transition network"""

        logger.info("Creating state transition network...")

        # Create disease state nodes
        state_query = """
        UNWIND $states as state
        MERGE (s:DiseaseState {state_id: state.id})
        SET s.name = state.name,
            s.description = state.description,
            s.severity_level = state.severity
        """

        states_data = [
            {'id': 'CN', 'name': 'Cognitively Normal', 'description': 'No cognitive impairment', 'severity': 0},
            {'id': 'SCD', 'name': 'Subjective Cognitive Decline', 'description': 'Self-reported decline',
             'severity': 1},
            {'id': 'EMCI', 'name': 'Early MCI', 'description': 'Early mild cognitive impairment', 'severity': 2},
            {'id': 'LMCI', 'name': 'Late MCI', 'description': 'Late mild cognitive impairment', 'severity': 3},
            {'id': 'AD', 'name': 'Alzheimer Disease', 'description': 'Clinical AD diagnosis', 'severity': 4}
        ]

        self.connector.run_query(state_query, {'states': states_data})

        # Create state transitions from events
        transition_query = """
        MATCH (e:Event)
        WHERE e.event_type = 'DIAGNOSIS_CHANGE'
        WITH e.from_state as from_state, e.to_state as to_state,
             count(*) as transition_count,
             avg(e.duration_months) as avg_duration

        MATCH (s1:DiseaseState {state_id: from_state})
        MATCH (s2:DiseaseState {state_id: to_state})

        MERGE (s1)-[t:CAN_TRANSITION_TO {
            transition_count: transition_count,
            avg_duration_months: avg_duration,
            probability: toFloat(transition_count) / 100.0
        }]->(s2)

        RETURN count(t) as transitions_created
        """

        result = self.connector.run_query(transition_query)
        transition_count = result[0]['transitions_created'] if result else 0

        # Create Markov chain properties
        markov_query = """
        MATCH (s:DiseaseState)
        OPTIONAL MATCH (s)-[t:CAN_TRANSITION_TO]->()
        WITH s, sum(t.transition_count) as total_transitions
        WHERE total_transitions > 0

        MATCH (s)-[t:CAN_TRANSITION_TO]->(next:DiseaseState)
        SET t.transition_probability = toFloat(t.transition_count) / toFloat(total_transitions)

        RETURN count(t) as updated
        """

        self.connector.execute_write_transaction(markov_query)

        return transition_count

    def _build_patient_timelines(self) -> int:
        """Build comprehensive patient timelines"""

        logger.info("Building patient timelines...")

        query = """
        // Create patient timeline with all events
        MATCH (p:Patient)-[:EXPERIENCED_EVENT]->(e:Event)
        WITH p, collect(e) as events
        WHERE size(events) > 0

        MERGE (tl:PatientTimeline {timeline_id: p.ptid + '_timeline'})
        ON CREATE SET tl.created_at = datetime()
        SET tl.patient_id = p.ptid,
            tl.total_events = size(events),
            tl.event_types = [e IN events | e.event_type],
            tl.start_date = events[0].timestamp,
            tl.end_date = events[-1].timestamp,
            tl.duration_months = events[-1].months_from_baseline - events[0].months_from_baseline,
            tl.updated_at = datetime()

        MERGE (p)-[:HAS_TIMELINE]->(tl)

        WITH tl, events
        UNWIND events as event
        MERGE (event)-[:ON_TIMELINE]->(tl)

        RETURN count(DISTINCT tl) as timelines_created
        """

        result = self.connector.run_query(query)
        timeline_count = result[0]['timelines_created'] if result else 0

        # Create milestone events
        milestone_query = """
        MATCH (tl:PatientTimeline)
        MATCH (e:Event)-[:ON_TIMELINE]->(tl)
        WHERE e.event_type IN ['DIAGNOSIS_CHANGE', 'CONVERSION', 'SYMPTOM_ONSET']
        WITH tl, e
        ORDER BY e.months_from_baseline
        WITH tl, collect(e) as milestones

        SET tl.milestone_count = size(milestones),
            tl.key_events = [m IN milestones | {
                type: m.event_type,
                months: m.months_from_baseline
            }]

        RETURN count(tl) as updated
        """

        self.connector.execute_write_transaction(milestone_query)

        return timeline_count

    def _identify_event_patterns(self) -> int:
        """Identify common event patterns in progression"""

        logger.info("Identifying event patterns...")

        # Find common event sequences
        pattern_query = """
        // Find common 3-event sequences with percentage
        MATCH (e1:Event)-[:FOLLOWED_BY]->(e2:Event)-[:FOLLOWED_BY]->(e3:Event)
        WITH e1.event_type + '->' + e2.event_type + '->' + e3.event_type as pattern,
             count(*) as frequency
        WHERE frequency >= 5

        // Calculate total for percentage
        WITH collect({pattern: pattern, frequency: frequency}) AS patterns,
             sum(frequency) AS total
        UNWIND patterns AS p

        MERGE (ep:EventPattern {pattern_id: replace(p.pattern, '->', '_')})
        ON CREATE SET ep.created_at = datetime()
        SET ep.pattern_string = p.pattern,
            ep.frequency = p.frequency,
            ep.percentage = round(100.0 * p.frequency / total, 2),
            ep.pattern_length = 3,
            ep.updated_at = datetime()

        RETURN count(ep) as patterns_found
        """

        result = self.connector.run_query(pattern_query)
        pattern_count = result[0]['patterns_found'] if result else 0

        # Identify progression patterns (any diagnosis change within 60 months)
        # Broadened from CN→AD<36mo to capture all transitions (CN→MCI, MCI→AD, etc.)
        rapid_query = """
        MATCH (p:Patient)-[:EXPERIENCED_EVENT]->(e:Event {event_type: 'DIAGNOSIS_CHANGE'})
        WHERE e.duration_months IS NOT NULL AND e.duration_months > 0

        MERGE (rp:ProgressionPattern {pattern_id: 'progression_' + p.ptid + '_' + e.from_state + '_' + e.to_state})
        ON CREATE SET rp.created_at = datetime()
        SET rp.pattern_type = CASE
                WHEN e.from_state = 'CN' AND e.to_state = 'AD' AND e.duration_months < 36 THEN 'rapid_progression'
                WHEN e.duration_months < 24 THEN 'fast_progression'
                ELSE 'standard_progression'
            END,
            rp.patient_id = p.ptid,
            rp.progression_time = e.duration_months,
            rp.from_state = e.from_state,
            rp.to_state = e.to_state,
            rp.updated_at = datetime()

        MERGE (p)-[:SHOWS_PATTERN]->(rp)
        MERGE (e)-[:EXEMPLIFIES]->(rp)

        RETURN count(rp) as rapid_progressors
        """

        result = self.connector.run_query(rapid_query)
        if result:
            pattern_count += result[0]['rapid_progressors']

        return pattern_count

    def _create_causal_relationships(self) -> int:
        """Create potential causal relationships between events"""

        logger.info("Creating causal relationships...")

        # Link biomarker events to subsequent clinical events
        causal_query = """
        // Find biomarker events followed by diagnosis changes
        MATCH (b:BiomarkerEvent)-[:FOLLOWED_BY]->(c:ClinicalEvent)
        WHERE b.event_type = 'BIOMARKER_CHANGE' 
          AND c.event_type = 'DIAGNOSIS_CHANGE'
          AND b.to_status = 'abnormal'

        MERGE (b)-[r:MAY_CAUSE {
            confidence: 0.7,
            lag_months: c.months_from_baseline - b.months_from_baseline,
            relationship_type: 'biomarker_precedes_clinical'
        }]->(c)

        RETURN count(r) as causal_relationships
        """

        result = self.connector.run_query(causal_query)
        causal_count = result[0]['causal_relationships'] if result else 0

        # Link imaging events to cognitive events
        imaging_causal_query = """
        MATCH (i:ImagingEvent)-[:FOLLOWED_BY]->(c:CognitiveEvent)
        WHERE i.finding = 'hippocampal_atrophy' 
          AND c.event_type = 'COGNITIVE_DECLINE'

        MERGE (i)-[r:MAY_CAUSE {
            confidence: 0.6,
            lag_months: c.months_from_baseline - i.months_from_baseline,
            relationship_type: 'atrophy_precedes_cognitive'
        }]->(c)

        RETURN count(r) as causal_relationships
        """

        result = self.connector.run_query(imaging_causal_query)
        if result:
            causal_count += result[0]['causal_relationships']

        return causal_count

    def _calculate_event_statistics(self) -> Dict[str, Any]:
        """Calculate statistics about the event model"""

        logger.info("Calculating event statistics...")

        stats_query = """
        MATCH (e:Event)
        WITH e.event_type as type, count(*) as count
        ORDER BY count DESC
        RETURN collect({event_type: type, count: count}) as event_distribution
        """

        result = self.connector.run_query(stats_query)
        event_dist = result[0]['event_distribution'] if result else []

        # Calculate average time between event types
        timing_query = """
        MATCH ()-[f:FOLLOWED_BY]->()
        RETURN avg(f.months_between) as avg_months_between_events,
               min(f.months_between) as min_months,
               max(f.months_between) as max_months,
               count(f) as total_sequences
        """

        result = self.connector.run_query(timing_query)
        timing_stats = result[0] if result else {}

        # Get progression statistics
        progression_query = """
        MATCH (p:Patient)-[:HAS_EVENT_CHAIN]->(ec:EventChain)
        RETURN avg(ec.duration_months) as avg_progression_duration,
               avg(ec.event_count) as avg_events_per_patient,
               count(DISTINCT p) as patients_with_events
        """

        result = self.connector.run_query(progression_query)
        progression_stats = result[0] if result else {}

        return {
            'event_distribution': event_dist,
            'timing_statistics': timing_stats,
            'progression_statistics': progression_stats,
            'total_events': self.events_created
        }

    def _categorize_event(self, event_type: str) -> str:
        """Categorize event type"""
        if 'DIAGNOSIS' in event_type or 'CONVERSION' in event_type:
            return 'clinical'
        elif 'BIOMARKER' in event_type or 'ATN' in event_type:
            return 'biomarker'
        elif 'COGNITIVE' in event_type:
            return 'cognitive'
        elif 'IMAGING' in event_type:
            return 'imaging'
        elif 'TREATMENT' in event_type:
            return 'treatment'
        else:
            return 'other'

    def create_event_based_queries(self) -> List[str]:
        """Generate useful queries for the event model"""

        queries = [
            # Find patients with rapid progression
            """
            MATCH (p:Patient)-[:HAS_EVENT_CHAIN]->(ec:EventChain)
            WHERE ec.duration_months < 24 
              AND ec.start_event = 'DIAGNOSIS_CHANGE'
              AND ec.end_event = 'DIAGNOSIS_CHANGE'
            RETURN p.ptid as patient, ec.duration_months as progression_time
            ORDER BY progression_time
            """,

            # Find most common event sequences
            """
            MATCH path = (e1:Event)-[:FOLLOWED_BY*2]->(e3:Event)
            WITH [n IN nodes(path) | n.event_type] as sequence
            RETURN sequence, count(*) as frequency
            ORDER BY frequency DESC
            LIMIT 10
            """,

            # Find biomarker events that predict conversion
            """
            MATCH (b:BiomarkerEvent)-[:MAY_CAUSE]->(c:ClinicalEvent)
            WHERE c.to_state = 'AD'
            RETURN b.analyte, count(*) as predictive_count
            ORDER BY predictive_count DESC
            """,

            # Patient trajectory visualization query
            """
            MATCH (p:Patient {ptid: $patient_id})-[:EXPERIENCED_EVENT]->(e:Event)
            RETURN e.event_type as type, 
                   e.months_from_baseline as months,
                   e ORDER BY e.months_from_baseline
            """
        ]

        return queries


def execute_event_based_model(neo4j_uri: str, neo4j_user: str, neo4j_password: str) -> Dict[str, Any]:
    """
    Execute event-based model creation

    Args:
        neo4j_uri: Neo4j connection URI
        neo4j_user: Username
        neo4j_password: Password

    Returns:
        Dictionary with model creation results
    """

    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        builder = EventBasedModelBuilder(connector)
        results = builder.execute()

        # Generate and store useful queries
        queries = builder.create_event_based_queries()
        results['example_queries'] = queries

        logger.info("\n" + "=" * 70)
        logger.info("EVENT-BASED MODEL CREATION COMPLETE")
        logger.info("=" * 70)

        return results

    except Exception as e:
        logger.error(f"Event model creation failed: {e}")
        raise
    finally:
        connector.close()


# Standalone execution
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Create Event-Based AD Progression Model")
    parser.add_argument('--neo4j-uri', default='bolt://localhost:7687', help='Neo4j URI')
    parser.add_argument('--neo4j-user', default='neo4j', help='Neo4j username')
    parser.add_argument('--neo4j-password', required=True, help='Neo4j password')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Execute event model creation
    results = execute_event_based_model(
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password
    )

    print(f"\n✅ Event-Based Model Created Successfully!")
    print(f"📊 Total events: {results.get('events_created', 0)}")
    print(f"🔗 Event chains: {results.get('event_chains', 0)}")
    print(f"📈 State transitions: {results.get('state_transitions', 0)}")
    print(f"👥 Patient timelines: {results.get('patient_timelines', 0)}")