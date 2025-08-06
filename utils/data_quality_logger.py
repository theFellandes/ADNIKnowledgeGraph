"""
Data Quality Logger for ADNI Knowledge Graph Pipeline
Logs all data quality issues, orphaned records, and missing relationships
"""

import logging
from typing import Dict, List, Any, Optional, Set
from datetime import datetime
from pathlib import Path
import json
from collections import defaultdict


class DataQualityLogger:
    """Comprehensive data quality logger for the pipeline"""

    def __init__(self, log_dir: str = "outputs/quality_logs"):
        """Initialize the data quality logger"""
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Create timestamp for this run
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Setup main quality log file
        self.quality_log_file = self.log_dir / f"data_quality_{self.timestamp}.log"

        # Setup specialized loggers
        self.setup_loggers()

        # Track issues
        self.issues = defaultdict(list)
        self.orphan_counts = defaultdict(int)
        self.missing_relationships = defaultdict(int)

    def setup_loggers(self):
        """Setup different loggers for different types of issues"""

        # Main quality logger
        self.quality_logger = logging.getLogger('data_quality')
        self.quality_logger.setLevel(logging.WARNING)

        # File handler for quality issues
        quality_handler = logging.FileHandler(self.quality_log_file)
        quality_handler.setLevel(logging.WARNING)
        quality_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - [%(category)s] - %(message)s'
        )
        quality_handler.setFormatter(quality_formatter)
        self.quality_logger.addHandler(quality_handler)

        # Orphan data logger
        self.orphan_log_file = self.log_dir / f"orphan_data_{self.timestamp}.log"
        self.orphan_logger = logging.getLogger('orphan_data')
        self.orphan_logger.setLevel(logging.WARNING)
        orphan_handler = logging.FileHandler(self.orphan_log_file)
        orphan_handler.setFormatter(quality_formatter)
        self.orphan_logger.addHandler(orphan_handler)

        # Missing data logger
        self.missing_log_file = self.log_dir / f"missing_data_{self.timestamp}.log"
        self.missing_logger = logging.getLogger('missing_data')
        self.missing_logger.setLevel(logging.WARNING)
        missing_handler = logging.FileHandler(self.missing_log_file)
        missing_handler.setFormatter(quality_formatter)
        self.missing_logger.addHandler(missing_handler)

    def log_orphan_data(self, entity_type: str, entity_id: str, missing_reference: str, details: Dict[str, Any] = None):
        """Log orphaned data that doesn't have expected relationships"""
        message = f"Orphan {entity_type}: {entity_id} - Missing {missing_reference}"
        if details:
            message += f" - Details: {json.dumps(details)}"

        self.orphan_logger.warning(message, extra={'category': 'ORPHAN'})
        self.orphan_counts[f"{entity_type}_missing_{missing_reference}"] += 1
        self.issues['orphans'].append({
            'entity_type': entity_type,
            'entity_id': entity_id,
            'missing_reference': missing_reference,
            'details': details
        })

    def log_missing_data(self, entity_type: str, expected_field: str, entity_id: str, details: Dict[str, Any] = None):
        """Log missing required data fields"""
        message = f"Missing {expected_field} in {entity_type}: {entity_id}"
        if details:
            message += f" - Details: {json.dumps(details)}"

        self.missing_logger.warning(message, extra={'category': 'MISSING'})
        self.missing_relationships[f"{entity_type}_missing_{expected_field}"] += 1
        self.issues['missing'].append({
            'entity_type': entity_type,
            'expected_field': expected_field,
            'entity_id': entity_id,
            'details': details
        })

    def log_data_inconsistency(self, issue_type: str, description: str, affected_entities: List[str],
                               details: Dict[str, Any] = None):
        """Log data inconsistencies"""
        message = f"Data Inconsistency [{issue_type}]: {description} - Affected: {len(affected_entities)} entities"
        if details:
            message += f" - Details: {json.dumps(details)}"

        self.quality_logger.warning(message, extra={'category': 'INCONSISTENCY'})
        self.issues['inconsistencies'].append({
            'issue_type': issue_type,
            'description': description,
            'affected_count': len(affected_entities),
            'sample_entities': affected_entities[:10],  # First 10 as sample
            'details': details
        })

    def log_extraction_failure(self, step: str, table: str, reason: str, row_count: int = 0):
        """Log when data extraction fails from a table"""
        message = f"Extraction Failed - Step: {step}, Table: {table}, Reason: {reason}, Rows Affected: {row_count}"

        self.quality_logger.warning(message, extra={'category': 'EXTRACTION_FAILURE'})
        self.issues['extraction_failures'].append({
            'step': step,
            'table': table,
            'reason': reason,
            'row_count': row_count
        })

    def log_relationship_issue(self, rel_type: str, from_entity: str, to_entity: str, issue: str):
        """Log issues with relationship creation"""
        message = f"Relationship Issue [{rel_type}]: {from_entity} -> {to_entity} - {issue}"

        self.quality_logger.warning(message, extra={'category': 'RELATIONSHIP'})
        self.issues['relationship_issues'].append({
            'relationship_type': rel_type,
            'from_entity': from_entity,
            'to_entity': to_entity,
            'issue': issue
        })

    def check_orphan_images(self, connector, log_details: bool = True):
        """Check for images without patients"""
        query = """
        MATCH (i:ImageNode)
        WHERE NOT (i)<-[:HAS_IMAGE]-(:ImagingStudy)<-[:HAS_IMAGING_STUDY]-(:Patient)
        RETURN i.image_id as image_id, i.patient_id as patient_id, i.study_id as study_id
        LIMIT 100
        """

        results = connector.run_query(query)

        if results:
            self.log_data_inconsistency(
                'ORPHAN_IMAGES',
                f'Found {len(results)} images without patient connections',
                [r['image_id'] for r in results],
                {'sample_count': len(results)}
            )

            if log_details:
                for result in results[:20]:  # Log first 20
                    self.log_orphan_data(
                        'ImageNode',
                        result['image_id'],
                        'Patient connection',
                        {
                            'patient_id': result['patient_id'],
                            'study_id': result['study_id']
                        }
                    )

        return len(results)

    def check_patients_without_visits(self, connector, log_details: bool = True):
        """Check for patients without any visits"""
        query = """
        MATCH (p:Patient)
        WHERE NOT (p)-[:HAS_VISIT]->(:Visit)
        RETURN p.ptid as patient_id, p.rid as rid
        LIMIT 100
        """

        results = connector.run_query(query)

        if results:
            self.log_data_inconsistency(
                'PATIENTS_WITHOUT_VISITS',
                f'Found {len(results)} patients without any visits',
                [r['patient_id'] for r in results],
                {'sample_count': len(results)}
            )

            if log_details:
                for result in results[:20]:
                    self.log_orphan_data(
                        'Patient',
                        result['patient_id'],
                        'Visit',
                        {'rid': result['rid']}
                    )

        return len(results)

    def check_visits_without_assessments(self, connector, log_details: bool = True):
        """Check for visits without any assessments"""
        query = """
        MATCH (v:Visit)
        WHERE NOT (v)-[:HAS_COGNITIVE_ASSESSMENT|HAS_BIOMARKER|HAS_DIAGNOSIS|HAS_IMAGING]->()
        RETURN v.visit_id as visit_id, v.patient_id as patient_id, v.viscode as viscode
        LIMIT 100
        """

        results = connector.run_query(query)

        if results:
            self.log_data_inconsistency(
                'VISITS_WITHOUT_DATA',
                f'Found {len(results)} visits without any associated data',
                [r['visit_id'] for r in results],
                {'sample_count': len(results)}
            )

            if log_details:
                for result in results[:20]:
                    self.log_orphan_data(
                        'Visit',
                        result['visit_id'],
                        'Clinical data',
                        {
                            'patient_id': result['patient_id'],
                            'viscode': result['viscode']
                        }
                    )

        return len(results)

    def check_missing_apoe(self, connector):
        """Check patients without APOE genotype"""
        query = """
        MATCH (p:Patient)
        WHERE p.apoe_genotype IS NULL
        RETURN count(p) as count
        """

        result = connector.run_query(query)
        count = result[0]['count'] if result else 0

        if count > 0:
            self.log_data_inconsistency(
                'MISSING_APOE',
                f'{count} patients missing APOE genotype data',
                [],
                {'total_count': count}
            )

        return count

    def check_biomarker_orphans(self, connector):
        """Check biomarkers not linked to visits"""
        query = """
        MATCH (b:Biomarker)
        WHERE NOT (:Visit)-[:HAS_BIOMARKER]->(b)
        RETURN b.biomarker_id as id, b.patient_id as patient_id, b.visit_id as visit_id
        LIMIT 50
        """

        results = connector.run_query(query)

        if results:
            self.log_data_inconsistency(
                'ORPHAN_BIOMARKERS',
                f'Found {len(results)} biomarkers not linked to visits',
                [r['id'] for r in results],
                {'sample_count': len(results)}
            )

        return len(results)

    def run_full_quality_check(self, connector):
        """Run comprehensive quality checks"""
        print("\n" + "=" * 80)
        print("DATA QUALITY CHECK REPORT")
        print("=" * 80)

        checks = [
            ("Orphan Images", self.check_orphan_images),
            ("Patients without Visits", self.check_patients_without_visits),
            ("Visits without Assessments", self.check_visits_without_assessments),
            ("Missing APOE Genotype", self.check_missing_apoe),
            ("Orphan Biomarkers", self.check_biomarker_orphans)
        ]

        total_issues = 0
        for check_name, check_func in checks:
            print(f"\nChecking: {check_name}...")
            count = check_func(connector)
            total_issues += count
            if count > 0:
                print(f"  ⚠️  Found {count} issues")
            else:
                print(f"  ✅ No issues found")

        # Generate summary report
        self.generate_summary_report()

        return total_issues

    def generate_summary_report(self):
        """Generate a summary report of all issues"""
        summary_file = self.log_dir / f"quality_summary_{self.timestamp}.json"

        summary = {
            'timestamp': self.timestamp,
            'total_issues': sum(len(v) for v in self.issues.values()),
            'orphan_counts': dict(self.orphan_counts),
            'missing_counts': dict(self.missing_relationships),
            'issues_by_category': {
                category: len(issues) for category, issues in self.issues.items()
            },
            'detailed_issues': self.issues
        }

        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)

        print(f"\n📊 Quality Summary Report saved to: {summary_file}")
        print(f"📋 Detailed logs saved to: {self.log_dir}")

        # Print summary to console
        print("\nSUMMARY:")
        print(f"  Total Issues: {summary['total_issues']}")
        print(f"  Orphan Records: {sum(self.orphan_counts.values())}")
        print(f"  Missing Data: {sum(self.missing_relationships.values())}")

        if self.orphan_counts:
            print("\n  Top Orphan Issues:")
            for issue, count in sorted(self.orphan_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"    - {issue}: {count}")


# Singleton instance
_quality_logger = None


def get_quality_logger() -> DataQualityLogger:
    """Get or create the singleton quality logger instance"""
    global _quality_logger
    if _quality_logger is None:
        _quality_logger = DataQualityLogger()
    return _quality_logger


def log_extraction_issue(step: str, table: str, issue: str, details: Dict[str, Any] = None):
    """Convenience function to log extraction issues"""
    logger = get_quality_logger()
    logger.log_extraction_failure(step, table, issue, details.get('row_count', 0) if details else 0)


def log_orphan(entity_type: str, entity_id: str, missing: str, details: Dict[str, Any] = None):
    """Convenience function to log orphan data"""
    logger = get_quality_logger()
    logger.log_orphan_data(entity_type, entity_id, missing, details)


def run_quality_checks(connector):
    """Run all quality checks"""
    logger = get_quality_logger()
    return logger.run_full_quality_check(connector)