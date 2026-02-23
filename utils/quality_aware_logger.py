import logging
from typing import Dict, Any
from utils.neo4j_connector import Neo4jConnector
from utils.data_quality_logger import DataQualityLogger, run_quality_checks

logger = logging.getLogger(__name__)


class QualityAwarePipeline:
    """Extension to ADNIPipeline with comprehensive quality logging"""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.quality_logger = DataQualityLogger()

    def run_with_quality_checks(self, pipeline):
        """Run pipeline with quality checks at each step"""

        # Run the main pipeline
        results = pipeline.run()

        # After pipeline completes, run comprehensive quality checks
        logger.info("\n" + "=" * 80)
        logger.info("RUNNING DATA QUALITY CHECKS")
        logger.info("=" * 80)

        connector = Neo4jConnector(
            self.config['neo4j_uri'],
            self.config['neo4j_user'],
            self.config['neo4j_password']
        )

        try:
            # Run quality checks
            total_issues = run_quality_checks(connector)

            # Add quality results to pipeline results
            results['quality_check'] = {
                'total_issues': total_issues,
                'log_directory': str(self.quality_logger.log_dir)
            }

            # Log specific issues for each step
            self._check_step_specific_issues(connector)

        finally:
            connector.close()

        return results

    def _check_step_specific_issues(self, connector):
        """Check for issues specific to each pipeline step"""

        # Step 3: Check patient issues
        self._check_patient_issues(connector)

        # Step 4: Check family issues
        self._check_family_issues(connector)

        # Step 5: Check imaging issues
        self._check_imaging_issues(connector)

        # Step 6: Check findings issues
        self._check_findings_issues(connector)

        # Step 8: Check relationship issues
        self._check_relationship_issues(connector)

    def _check_patient_issues(self, connector):
        """Check for patient data quality issues"""
        query = """
        MATCH (p:Patient)
        WHERE p.age_at_baseline IS NULL OR p.gender IS NULL
        RETURN p.ptid as patient_id, p.age_at_baseline as age, p.gender as gender
        LIMIT 50
        """

        results = connector.run_query(query)

        for result in results:
            if result['age'] is None:
                self.quality_logger.log_missing_data(
                    'Patient',
                    'age_at_baseline',
                    result['patient_id']
                )
            if result['gender'] is None:
                self.quality_logger.log_missing_data(
                    'Patient',
                    'gender',
                    result['patient_id']
                )

    def _check_family_issues(self, connector):
        """Check for family data issues"""
        # Check patients with family history but no extracted family members
        query = """
        MATCH (p:Patient)
        WHERE NOT (p)-[:HAS_FAMILY_MEMBER]->()
        RETURN count(p) as count
        """

        result = connector.run_query(query)
        count = result[0]['count'] if result else 0

        if count > 0:
            self.quality_logger.log_data_inconsistency(
                'MISSING_FAMILY_DATA',
                f'{count} patients have no family history data extracted',
                [],
                {'total_patients_without_family': count}
            )

    def _check_imaging_issues(self, connector):
        """Check for imaging data issues"""
        # Check images without proper study linkage
        query = """
        MATCH (i:ImageNode)
        WHERE NOT (i)<-[:HAS_IMAGE]-(:ImagingStudy)
        RETURN i.image_id as image_id, i.patient_id as patient_id
        LIMIT 50
        """

        results = connector.run_query(query)

        for result in results:
            self.quality_logger.log_orphan_data(
                'ImageNode',
                result['image_id'],
                'ImagingStudy',
                {'patient_id': result['patient_id']}
            )

    def _check_findings_issues(self, connector):
        """Check for clinical findings issues"""
        # Check cognitive assessments without scores
        query = """
        MATCH (ca:CognitiveAssessment)
        WHERE ca.total_score IS NULL
        RETURN ca.assessment_id as id, ca.test_name as test
        LIMIT 50
        """

        results = connector.run_query(query)

        for result in results:
            self.quality_logger.log_missing_data(
                'CognitiveAssessment',
                'total_score',
                result['id'],
                {'test_name': result['test']}
            )

        # Check biomarkers without values
        query = """
        MATCH (b:Biomarker)
        WHERE b.value IS NULL OR b.value <= 0
        RETURN b.biomarker_id as id, b.analyte as analyte
        LIMIT 50
        """

        results = connector.run_query(query)

        for result in results:
            self.quality_logger.log_missing_data(
                'Biomarker',
                'value',
                result['id'],
                {'analyte': result['analyte']}
            )

    def _check_relationship_issues(self, connector):
        """Check for relationship consistency issues"""
        # Check for missing expected relationships
        checks = [
            {
                'name': 'Visits without patient link',
                'query': """
                    MATCH (v:Visit)
                    WHERE NOT (:Patient)-[:HAS_VISIT]->(v)
                    RETURN v.visit_id as id
                    LIMIT 50
                """,
                'entity_type': 'Visit',
                'missing': 'Patient relationship'
            },
            {
                'name': 'Diagnoses without visit link',
                'query': """
                    MATCH (d:Diagnosis)
                    WHERE NOT (:Visit)-[:HAS_DIAGNOSIS]->(d)
                    RETURN d.diagnosis_id as id
                    LIMIT 50
                """,
                'entity_type': 'Diagnosis',
                'missing': 'Visit relationship'
            },
            {
                'name': 'Biomarkers without visit link',
                'query': """
                    MATCH (b:Biomarker)
                    WHERE NOT (:Visit)-[:HAS_BIOMARKER]->(b)
                    RETURN b.biomarker_id as id
                    LIMIT 50
                """,
                'entity_type': 'Biomarker',
                'missing': 'Visit relationship'
            }
        ]

        for check in checks:
            results = connector.run_query(check['query'])

            if results:
                self.quality_logger.log_data_inconsistency(
                    check['name'].replace(' ', '_').upper(),
                    f"Found {len(results)} {check['entity_type']} entities without proper relationships",
                    [r['id'] for r in results[:10]],
                    {'sample_count': len(results)}
                )

                # Log individual orphans
                for result in results[:20]:
                    self.quality_logger.log_orphan_data(
                        check['entity_type'],
                        result['id'],
                        check['missing']
                    )