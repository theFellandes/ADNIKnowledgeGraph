"""
Step 10: Execute ADNI Knowledge Graph Queries
Executes all analysis and enrichment queries on the knowledge graph
"""

import logging
from typing import Dict, List, Any
from datetime import datetime
import json
from pathlib import Path

from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


class ADNIQueryExecutor:
    """Execute predefined queries for ADNI knowledge graph analysis and enrichment"""

    def __init__(self, connector: Neo4jConnector):
        self.connector = connector
        self.results = {}
        self.statistics = {
            'total_queries': 0,
            'successful': 0,
            'failed': 0,
            'nodes_created': 0,
            'relationships_created': 0,
            'rows_returned': 0,
            'execution_time': 0
        }

    def execute_all_queries(self) -> Dict[str, Any]:
        """Execute all ADNI analysis queries"""

        logger.info("\n" + "="*70)
        logger.info("STEP 10: EXECUTING ADNI KNOWLEDGE GRAPH QUERIES")
        logger.info("="*70)

        start_time = datetime.now()

        # Execute queries in sequence
        self._execute_diagnosis_creation_queries()
        self._execute_relationship_queries()
        self._execute_progression_queries()
        self._execute_analysis_queries()
        self._execute_visualization_prep_queries()
        self._execute_cohort_queries()
        self._create_diagnosis_relationships()

        self.statistics['execution_time'] = (datetime.now() - start_time).total_seconds()

        # Generate summary
        self._generate_summary()

        return {
            'results': self.results,
            'statistics': self.statistics
        }

    def _execute_diagnosis_creation_queries(self):
        """Create diagnoses from cognitive assessments"""

        logger.info("\n" + "-"*60)
        logger.info("Creating Diagnoses from Cognitive Assessments")
        logger.info("-"*60)

        # Query 1: Create diagnoses from CDR scores
        query1 = """
        MATCH (ca:CognitiveAssessment)
        WHERE ca.test_name = 'CDR'
        WITH ca,
             CASE
               WHEN ca.total_score = 0 THEN 'CN'
               WHEN ca.total_score <= 0.5 THEN 'MCI'
               WHEN ca.total_score >= 1 THEN 'AD'
               ELSE 'Unknown'
             END as diagnosis_code
        WHERE diagnosis_code <> 'Unknown'
        MERGE (d:Diagnosis {
          diagnosis_id: ca.patient_id + '_' + ca.visit_id + '_CDR_derived',
          patient_id: ca.patient_id,
          visit_id: ca.visit_id,
          diagnosis_code: diagnosis_code,
          diagnosis_text: CASE diagnosis_code
            WHEN 'CN' THEN 'Cognitively Normal'
            WHEN 'MCI' THEN 'Mild Cognitive Impairment'
            WHEN 'AD' THEN 'Alzheimers Disease'
            ELSE 'Unknown'
          END,
          confidence: 0.8,
          source: 'Derived from CDR'
        })
        WITH ca, d
        MATCH (v:Visit {visit_id: ca.visit_id})
        MERGE (v)-[:RESULTED_IN]->(d)
        RETURN count(d) as diagnoses_created
        """

        result = self._execute_query("Create diagnoses from CDR", query1)
        if result and 'diagnoses_created' in result[0]:
            count = result[0]['diagnoses_created']
            logger.info(f"  ✅ Created {count} diagnoses from CDR scores")
            self.statistics['nodes_created'] += count

        # Query 2: Create diagnoses from MMSE scores
        query2 = """
        MATCH (ca:CognitiveAssessment)
        WHERE ca.test_name = 'MMSE'
        WITH ca,
             CASE
               WHEN ca.total_score >= 27 THEN 'CN'
               WHEN ca.total_score >= 21 AND ca.total_score < 27 THEN 'MCI'
               WHEN ca.total_score < 21 THEN 'AD'
               ELSE 'Unknown'
             END as diagnosis_code
        WHERE diagnosis_code <> 'Unknown'
        MERGE (d:Diagnosis {
          diagnosis_id: ca.patient_id + '_' + ca.visit_id + '_MMSE_derived',
          patient_id: ca.patient_id,
          visit_id: ca.visit_id,
          diagnosis_code: diagnosis_code,
          diagnosis_text: CASE diagnosis_code
            WHEN 'CN' THEN 'Cognitively Normal'
            WHEN 'MCI' THEN 'Mild Cognitive Impairment'
            WHEN 'AD' THEN 'Alzheimers Disease'
            ELSE 'Unknown'
          END,
          confidence: 0.75,
          source: 'Derived from MMSE'
        })
        WITH ca, d
        MATCH (v:Visit {visit_id: ca.visit_id})
        MERGE (v)-[:RESULTED_IN]->(d)
        RETURN count(d) as diagnoses_created
        """

        result = self._execute_query("Create diagnoses from MMSE", query2)
        if result and 'diagnoses_created' in result[0]:
            count = result[0]['diagnoses_created']
            logger.info(f"  ✅ Created {count} diagnoses from MMSE scores")
            self.statistics['nodes_created'] += count

    def _execute_relationship_queries(self):
        """Ensure all relationships are properly connected"""

        logger.info("\n" + "-"*60)
        logger.info("Creating and Fixing Relationships")
        logger.info("-"*60)

        # Query 3: Ensure all visits are connected to patients
        query3 = """
        MATCH (v:Visit)
        WHERE NOT (v)<-[:HAS_VISIT]-(:Patient)
        WITH v, split(v.visit_id, '_')[0] as patient_id
        MATCH (p:Patient {ptid: patient_id})
        MERGE (p)-[:HAS_VISIT]->(v)
        RETURN count(v) as visits_connected
        """

        result = self._execute_query("Connect visits to patients", query3)
        if result and 'visits_connected' in result[0]:
            count = result[0]['visits_connected']
            logger.info(f"  ✅ Connected {count} visits to patients")
            self.statistics['relationships_created'] += count

        # Query 4: Connect diagnoses to patients
        query4 = """
        MATCH (d:Diagnosis)
        WHERE NOT (d)<-[:HAS_DIAGNOSIS]-(:Patient)
        MATCH (p:Patient {ptid: d.patient_id})
        MERGE (p)-[:HAS_DIAGNOSIS]->(d)
        RETURN count(d) as diagnoses_connected
        """

        result = self._execute_query("Connect diagnoses to patients", query4)
        if result and 'diagnoses_connected' in result[0]:
            count = result[0]['diagnoses_connected']
            logger.info(f"  ✅ Connected {count} diagnoses to patients")
            self.statistics['relationships_created'] += count

    def _execute_progression_queries(self):
        """Create progression relationships between diagnoses"""

        logger.info("\n" + "-"*60)
        logger.info("Creating Disease Progression Relationships")
        logger.info("-"*60)

        # Query 5: Create progression relationships
        query5 = """
        MATCH (p:Patient)-[:HAS_VISIT]->(v1:Visit)-[:RESULTED_IN]->(d1:Diagnosis)
        MATCH (p)-[:HAS_VISIT]->(v2:Visit)-[:RESULTED_IN]->(d2:Diagnosis)
        WHERE v1.months_from_baseline < v2.months_from_baseline
          AND d1.diagnosis_code <> d2.diagnosis_code
          AND id(d1) < id(d2)  // Avoid duplicates
        WITH p, d1, d2, v1, v2
        ORDER BY p.ptid, v1.months_from_baseline, v2.months_from_baseline
        WITH p, d1, d2, min(v2.months_from_baseline - v1.months_from_baseline) as duration
        MERGE (d1)-[:PROGRESSED_TO {
          patient_id: p.ptid,
          duration_months: duration
        }]->(d2)
        RETURN count(*) as progressions_created
        """

        result = self._execute_query("Create progression relationships", query5)
        if result and 'progressions_created' in result[0]:
            count = result[0]['progressions_created']
            logger.info(f"  ✅ Created {count} progression relationships")
            self.statistics['relationships_created'] += count

    def _execute_analysis_queries(self):
        """Execute analytical queries"""

        logger.info("\n" + "-"*60)
        logger.info("Running Analysis Queries")
        logger.info("-"*60)

        # Query 6: See cognitive trajectories
        query6 = """
        MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
        WHERE ca.test_name = 'MMSE'
        WITH p.ptid as patient,
             v.months_from_baseline as months,
             ca.total_score as score
        ORDER BY patient, months
        WITH patient, collect({months: months, score: score}) as trajectory
        WHERE size(trajectory) >= 3
        RETURN patient, trajectory
        LIMIT 10
        """

        result = self._execute_query("Analyze cognitive trajectories", query6)
        if result:
            count = len(result)
            logger.info(f"  ✅ Found {count} patients with cognitive trajectories")
            self.statistics['rows_returned'] += count

            # Store sample trajectories
            self.results['cognitive_trajectories'] = result[:5]

        # Query 7: Find patients with declining MMSE scores
        query7 = """
        MATCH (p:Patient)-[:HAS_VISIT]->(v1:Visit)-[:HAS_COGNITIVE_ASSESSMENT]->(ca1:CognitiveAssessment {test_name: 'MMSE'})
        MATCH (p)-[:HAS_VISIT]->(v2:Visit)-[:HAS_COGNITIVE_ASSESSMENT]->(ca2:CognitiveAssessment {test_name: 'MMSE'})
        WHERE v1.months_from_baseline = 0
          AND v2.months_from_baseline > 0
          AND ca2.total_score < ca1.total_score - 3  // Significant decline
        RETURN p.ptid as patient,
               ca1.total_score as baseline_mmse,
               ca2.total_score as followup_mmse,
               v2.months_from_baseline as months_later,
               ca1.total_score - ca2.total_score as decline
        ORDER BY decline DESC
        LIMIT 20
        """

        result = self._execute_query("Find declining MMSE patients", query7)
        if result:
            count = len(result)
            logger.info(f"  ✅ Found {count} patients with significant MMSE decline")
            self.statistics['rows_returned'] += count

            # Store declining patients
            self.results['declining_patients'] = result

        # Query 8: Patient summary view
        query8 = """
        MATCH (p:Patient)
        OPTIONAL MATCH (p)-[:HAS_VISIT]->(v:Visit)
        OPTIONAL MATCH (v)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
        OPTIONAL MATCH (v)-[:RESULTED_IN]->(d:Diagnosis)
        WITH p,
             count(distinct v) as visit_count,
             count(distinct ca) as assessment_count,
             count(distinct d) as diagnosis_count,
             collect(distinct ca.test_name) as tests_taken,
             collect(distinct d.diagnosis_code) as diagnoses
        RETURN p.ptid as patient,
               p.age_at_baseline as age,
               p.gender as gender,
               p.apoe_genotype as apoe,
               visit_count,
               assessment_count,
               diagnosis_count,
               tests_taken,
               diagnoses
        LIMIT 20
        """

        result = self._execute_query("Generate patient summary", query8)
        if result:
            count = len(result)
            logger.info(f"  ✅ Generated summary for {count} patients")
            self.statistics['rows_returned'] += count

            # Store patient summaries
            self.results['patient_summaries'] = result

        # Query 9: Find cognitive assessment patterns
        query9 = """
        MATCH (ca:CognitiveAssessment)
        WITH ca.test_name as test,
             count(*) as frequency,
             avg(ca.total_score) as avg_score,
             min(ca.total_score) as min_score,
             max(ca.total_score) as max_score
        RETURN test, frequency,
               round(avg_score, 2) as avg_score,
               min_score, max_score
        ORDER BY frequency DESC
        """

        result = self._execute_query("Analyze assessment patterns", query9)
        if result:
            count = len(result)
            logger.info(f"  ✅ Found {count} assessment patterns")
            self.statistics['rows_returned'] += count

            # Store assessment patterns
            self.results['assessment_patterns'] = result

    def _execute_visualization_prep_queries(self):
        """Create nodes for better visualization"""

        logger.info("\n" + "-"*60)
        logger.info("Creating Visualization Support Nodes")
        logger.info("-"*60)

        # Query 10: Create test type nodes
        query10 = """
        MATCH (ca:CognitiveAssessment)
        WITH DISTINCT ca.test_name as test_name
        MERGE (t:TestType {name: test_name})
        WITH t
        MATCH (ca:CognitiveAssessment {test_name: t.name})
        MERGE (ca)-[:IS_TYPE]->(t)
        RETURN count(t) as test_types_created
        """

        result = self._execute_query("Create test type nodes", query10)
        if result and 'test_types_created' in result[0]:
            count = result[0]['test_types_created']
            logger.info(f"  ✅ Created {count} test type nodes")
            self.statistics['nodes_created'] += count

    def _execute_cohort_queries(self):
        """Create cohort classifications"""

        logger.info("\n" + "-"*60)
        logger.info("Creating Research Cohorts")
        logger.info("-"*60)

        # Query 11: Create cohort nodes based on baseline assessments
        query11 = """
        MATCH (p:Patient)-[:HAS_VISIT]->(v:Visit {months_from_baseline: 0})
        MATCH (v)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment {test_name: 'MMSE'})
        WITH p, ca.total_score as baseline_mmse
        WITH p,
             CASE
               WHEN baseline_mmse >= 27 THEN 'Normal_Baseline'
               WHEN baseline_mmse >= 21 THEN 'MCI_Baseline'
               ELSE 'AD_Baseline'
             END as cohort_name
        MERGE (c:Cohort {name: cohort_name})
        MERGE (p)-[:BELONGS_TO_COHORT]->(c)
        RETURN cohort_name, count(p) as patients_in_cohort
        """

        result = self._execute_query("Create baseline cohorts", query11)
        if result:
            total_patients = sum(r['patients_in_cohort'] for r in result)
            logger.info(f"  ✅ Assigned {total_patients} patients to cohorts")

            # Log cohort breakdown
            for row in result:
                logger.info(f"    - {row['cohort_name']}: {row['patients_in_cohort']} patients")

            self.statistics['relationships_created'] += total_patients

            # Store cohort information
            self.results['cohorts'] = result

    def _execute_query(self, description: str, query: str) -> List[Dict]:
        """Execute a single query and handle results"""

        self.statistics['total_queries'] += 1

        try:
            logger.debug(f"Executing: {description}")

            # Determine if this is a write or read query
            query_upper = query.upper()
            is_write = any(keyword in query_upper for keyword in ['MERGE', 'CREATE', 'SET', 'DELETE'])

            if is_write:
                # For write queries that return results
                if 'RETURN' in query_upper:
                    result = self.connector.run_query(query)
                else:
                    # For write queries without return
                    self.connector.execute_write_transaction(query)
                    result = [{'status': 'executed'}]
            else:
                # For read queries
                result = self.connector.run_query(query)

            self.statistics['successful'] += 1
            return result

        except Exception as e:
            logger.error(f"  ❌ Failed to execute '{description}': {e}")
            self.statistics['failed'] += 1
            return []

    def _generate_summary(self):
        """Generate execution summary"""

        logger.info("\n" + "="*70)
        logger.info("QUERY EXECUTION SUMMARY")
        logger.info("="*70)

        logger.info(f"Total queries executed: {self.statistics['total_queries']}")
        logger.info(f"Successful: {self.statistics['successful']}")
        logger.info(f"Failed: {self.statistics['failed']}")
        logger.info(f"Nodes created: {self.statistics['nodes_created']:,}")
        logger.info(f"Relationships created: {self.statistics['relationships_created']:,}")
        logger.info(f"Total rows returned: {self.statistics['rows_returned']:,}")
        logger.info(f"Execution time: {self.statistics['execution_time']:.2f} seconds")

        if self.results:
            logger.info("\nStored Results:")
            for key in self.results.keys():
                logger.info(f"  - {key}")

    def _create_diagnosis_relationships(self):
        """Create comprehensive diagnosis relationships"""

        queries = [
            # Connect diagnoses to patients
            """
            MATCH (d:Diagnosis)
            MATCH (p:Patient {ptid: d.patient_id})
            MERGE (p)-[:HAS_DIAGNOSIS {
                confidence: d.confidence,
                source: d.source  // Fixed: changed from d.source_table to d.source
            }]->(d)
            """,

            # Create disease progression paths
            """
            MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d1:Diagnosis)
            MATCH (p)-[:HAS_DIAGNOSIS]->(d2:Diagnosis)
            WHERE d1.visit_id < d2.visit_id 
            AND d1.diagnosis_code <> d2.diagnosis_code
            MERGE (d1)-[:PROGRESSED_TO {
                patient_id: p.ptid
            }]->(d2)
            """,

            # Link cognitive assessments to diagnoses - Fixed query
            """
            MATCH (v:Visit)-[:RESULTED_IN]->(d:Diagnosis)  // Changed from HAS_DIAGNOSIS
            MATCH (v)-[:HAS_COGNITIVE_ASSESSMENT]->(ca:CognitiveAssessment)
            MERGE (ca)-[:SUPPORTS_DIAGNOSIS {
                diagnosis_code: d.diagnosis_code
            }]->(d)
            """,

            # Create ATN profiles
            """
            MATCH (p:Patient)-[:HAS_BIOMARKER]->(b:Biomarker)
            WHERE b.analyte IN ['Aβ42', 'p-Tau181', 'Total Tau']
            WITH p, 
                 MAX(CASE WHEN b.analyte = 'Aβ42' AND b.value < 600 THEN 1 ELSE 0 END) as A_pos,
                 MAX(CASE WHEN b.analyte = 'p-Tau181' AND b.value > 80 THEN 1 ELSE 0 END) as T_pos,
                 MAX(CASE WHEN b.analyte = 'Total Tau' AND b.value > 400 THEN 1 ELSE 0 END) as N_pos
            MERGE (atn:ATNProfile {
                patient_id: p.ptid,
                A_status: CASE WHEN A_pos = 1 THEN 'A+' ELSE 'A-' END,
                T_status: CASE WHEN T_pos = 1 THEN 'T+' ELSE 'T-' END,
                N_status: CASE WHEN N_pos = 1 THEN 'N+' ELSE 'N-' END
            })
            MERGE (p)-[:HAS_ATN_PROFILE]->(atn)
            """
        ]

        for query in queries:
            self.connector.execute_write_transaction(query)

    def export_results(self, output_dir: str = "outputs"):
        """Export results to JSON file"""

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_path / f"query_results_{timestamp}.json"

        export_data = {
            'execution_time': datetime.now().isoformat(),
            'statistics': self.statistics,
            'results': {}
        }

        # Convert results to serializable format
        for key, value in self.results.items():
            if isinstance(value, list):
                # Limit large result sets
                export_data['results'][key] = value[:100] if len(value) > 100 else value
            else:
                export_data['results'][key] = value

        with open(output_file, 'w') as f:
            json.dump(export_data, f, indent=2, default=str)

        logger.info(f"\n📄 Results exported to: {output_file}")
        return str(output_file)


def execute_adni_queries(neo4j_uri: str, neo4j_user: str, neo4j_password: str) -> Dict[str, Any]:
    """
    Execute all ADNI knowledge graph queries

    Args:
        neo4j_uri: Neo4j connection URI
        neo4j_user: Username
        neo4j_password: Password

    Returns:
        Dictionary with execution results and statistics
    """

    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        executor = ADNIQueryExecutor(connector)

        # Execute all queries
        result = executor.execute_all_queries()

        # Export results
        output_file = executor.export_results()
        result['output_file'] = output_file

        logger.info("\n" + "="*70)
        logger.info("✅ STEP 10 COMPLETED SUCCESSFULLY")
        logger.info("="*70)

        return result

    except Exception as e:
        logger.error(f"Query execution failed: {e}")
        raise
    finally:
        connector.close()


# Standalone execution
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Execute ADNI knowledge graph queries")
    parser.add_argument('--neo4j-uri', default='bolt://localhost:7687', help='Neo4j URI')
    parser.add_argument('--neo4j-user', default='neo4j', help='Neo4j username')
    parser.add_argument('--neo4j-password', required=True, help='Neo4j password')
    parser.add_argument('--log-level', default='INFO', help='Logging level')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format='%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s'
    )

    try:
        # Execute queries
        results = execute_adni_queries(
            neo4j_uri=args.neo4j_uri,
            neo4j_user=args.neo4j_user,
            neo4j_password=args.neo4j_password
        )

        print(f"\n✅ All queries executed successfully!")
        print(f"📊 Nodes created: {results['statistics']['nodes_created']:,}")
        print(f"🔗 Relationships created: {results['statistics']['relationships_created']:,}")
        print(f"📄 Results saved to: {results.get('output_file', 'N/A')}")

        sys.exit(0)

    except Exception as e:
        print(f"\n❌ Query execution failed: {e}")
        sys.exit(1)