"""
Step 13: Graph Exploratory Data Analysis
Fixed version with corrected Cypher queries
"""

import logging
from typing import Dict, List, Any
from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)


class GraphExplorer:
    """Performs exploratory data analysis on the ADNI knowledge graph"""

    def __init__(self, connector: Neo4jConnector):
        self.connector = connector
        self.analysis = {}

    def execute(self) -> Dict[str, Any]:
        """Execute comprehensive graph analysis"""

        logger.info("\n" + "=" * 70)
        logger.info("GRAPH EXPLORATORY DATA ANALYSIS")
        logger.info("=" * 70)

        # 1. Analyze master nodes
        self._analyze_master_nodes()

        # 2. Analyze node distribution
        self._analyze_node_distribution()

        # 3. Analyze relationship patterns
        self._analyze_relationship_patterns()

        # 4. Analyze patient characteristics
        self._analyze_patient_characteristics()

        # 5. Analyze disease progression patterns
        self._analyze_progression_patterns()

        # 6. Analyze biomarker distributions
        self._analyze_biomarker_distributions()

        # 7. Analyze connectivity
        self._analyze_connectivity()

        # 8. Generate summary report
        self._generate_summary()

        return self.analysis

    def _analyze_master_nodes(self):
        """Identify and analyze master/hub nodes in the graph"""

        logger.info("\nAnalyzing master nodes...")

        # Find nodes with highest degree centrality
        query = """
        MATCH (n)
        WITH labels(n) as node_labels, n
        MATCH (n)-[r]-()
        WITH node_labels[0] as label, n, count(r) as degree
        ORDER BY degree DESC
        WITH label, collect({id: id(n), degree: degree})[..5] as top_nodes
        RETURN label, top_nodes
        """

        try:
            result = self.connector.run_query(query)

            master_nodes = {}
            for row in result:
                master_nodes[row['label']] = row['top_nodes']

            self.analysis['master_nodes'] = master_nodes
        except Exception as e:
            logger.warning(f"Failed to analyze master nodes: {e}")
            self.analysis['master_nodes'] = {}

        # Identify super-connectors (patients with most relationships)
        patient_query = """
        MATCH (p:Patient)
        OPTIONAL MATCH (p)-[r]-()
        WITH p, count(r) as connections
        ORDER BY connections DESC
        LIMIT 10
        RETURN p.ptid as patient_id, 
               connections,
               p.apoe_genotype as apoe,
               p.age_at_baseline as age
        """

        try:
            result = self.connector.run_query(patient_query)
            self.analysis['super_connector_patients'] = result
        except Exception as e:
            logger.warning(f"Failed to analyze super-connector patients: {e}")
            self.analysis['super_connector_patients'] = []

    def _analyze_node_distribution(self):
        """Analyze distribution of different node types"""

        logger.info("Analyzing node distribution...")

        query = """
        MATCH (n)
        WITH labels(n)[0] as label, count(n) as count
        ORDER BY count DESC
        RETURN label as node_type, count
        """

        try:
            result = self.connector.run_query(query)

            distribution = {}
            total = 0
            for row in result:
                distribution[row['node_type']] = row['count']
                total += row['count']

            # Calculate percentages
            for node_type in distribution:
                percentage = (distribution[node_type] / total) * 100 if total > 0 else 0
                distribution[node_type] = {
                    'count': distribution[node_type],
                    'percentage': round(percentage, 2)
                }

            self.analysis['node_distribution'] = distribution
            self.analysis['total_nodes'] = total
        except Exception as e:
            logger.warning(f"Failed to analyze node distribution: {e}")
            self.analysis['node_distribution'] = {}
            self.analysis['total_nodes'] = 0

    def _analyze_relationship_patterns(self):
        """Analyze relationship patterns and frequencies"""

        logger.info("Analyzing relationship patterns...")

        # Top relationship types
        query = """
        MATCH ()-[r]->()
        WITH type(r) as rel_type, count(r) as count
        ORDER BY count DESC
        RETURN rel_type, count
        LIMIT 20
        """

        try:
            result = self.connector.run_query(query)
            self.analysis['top_relationships'] = result
        except Exception as e:
            logger.warning(f"Failed to analyze top relationships: {e}")
            self.analysis['top_relationships'] = []

        # Fixed: Calculate average relationships per node type
        density_query = """
        MATCH (n)
        WITH labels(n)[0] as label, n
        OPTIONAL MATCH (n)-[r]-()
        WITH label, n, count(r) as rel_count
        WITH label, avg(rel_count) as avg_relationships
        ORDER BY avg_relationships DESC
        RETURN label as node_type, 
               toInteger(avg_relationships) as avg_connections
        """

        try:
            result = self.connector.run_query(density_query)
            self.analysis['relationship_density'] = result
        except Exception as e:
            logger.warning(f"Failed to analyze relationship density: {e}")
            self.analysis['relationship_density'] = []

    def _analyze_patient_characteristics(self):
        """Analyze patient demographic and clinical characteristics"""

        logger.info("Analyzing patient characteristics...")

        # Demographics distribution
        demo_query = """
        MATCH (p:Patient)
        RETURN 
            count(p) as total_patients,
            avg(p.age_at_baseline) as avg_age,
            min(p.age_at_baseline) as min_age,
            max(p.age_at_baseline) as max_age,
            avg(p.education_years) as avg_education,
            sum(CASE WHEN p.gender = 'M' THEN 1 ELSE 0 END) as male_count,
            sum(CASE WHEN p.gender = 'F' THEN 1 ELSE 0 END) as female_count,
            sum(CASE WHEN p.apoe_genotype CONTAINS '4' THEN 1 ELSE 0 END) as apoe4_carriers
        """

        try:
            result = self.connector.run_query(demo_query)
            if result:
                self.analysis['patient_demographics'] = result[0]
        except Exception as e:
            logger.warning(f"Failed to analyze patient demographics: {e}")
            self.analysis['patient_demographics'] = {}

        # Diagnosis distribution
        dx_query = """
        MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d:Diagnosis)
        WITH d.diagnosis_code as dx, count(DISTINCT p) as patient_count
        ORDER BY patient_count DESC
        RETURN dx as diagnosis, patient_count
        """

        try:
            result = self.connector.run_query(dx_query)
            self.analysis['diagnosis_distribution'] = result
        except Exception as e:
            logger.warning(f"Failed to analyze diagnosis distribution: {e}")
            self.analysis['diagnosis_distribution'] = []

    def _analyze_progression_patterns(self):
        """Analyze disease progression patterns"""

        logger.info("Analyzing disease progression patterns...")

        # Check if ProgressionEvent nodes exist
        check_query = """
        MATCH (pe:ProgressionEvent)
        RETURN count(pe) as count
        """

        try:
            result = self.connector.run_query(check_query)
            if result and result[0]['count'] > 0:
                query = """
                MATCH (p:Patient)-[:EXPERIENCED_PROGRESSION]->(pe:ProgressionEvent)
                WITH pe.from_diagnosis as from_dx, 
                     pe.to_diagnosis as to_dx,
                     avg(pe.duration_months) as avg_duration,
                     count(p) as patient_count
                ORDER BY patient_count DESC
                RETURN from_dx + ' -> ' + to_dx as progression_path,
                       patient_count,
                       toInteger(avg_duration) as avg_months
                """

                result = self.connector.run_query(query)
                self.analysis['progression_patterns'] = result
            else:
                # Alternative: analyze diagnosis changes over visits
                alt_query = """
                MATCH (p:Patient)-[:HAS_DIAGNOSIS]->(d1:Diagnosis)
                MATCH (p)-[:HAS_DIAGNOSIS]->(d2:Diagnosis)
                WHERE d1.visit_id < d2.visit_id AND d1.diagnosis_code <> d2.diagnosis_code
                WITH d1.diagnosis_code as from_dx, 
                     d2.diagnosis_code as to_dx,
                     count(DISTINCT p) as patient_count
                ORDER BY patient_count DESC
                RETURN from_dx + ' -> ' + to_dx as progression_path,
                       patient_count
                LIMIT 10
                """

                result = self.connector.run_query(alt_query)
                self.analysis['progression_patterns'] = result
        except Exception as e:
            logger.warning(f"Failed to analyze progression patterns: {e}")
            self.analysis['progression_patterns'] = []

    def _analyze_biomarker_distributions(self):
        """Analyze biomarker distributions and patterns"""

        logger.info("Analyzing biomarker distributions...")

        # ATN profile distribution - check if profiles exist
        atn_check = """
        MATCH (atn:ATNProfile)
        RETURN count(atn) as count
        """

        try:
            result = self.connector.run_query(atn_check)
            if result and result[0]['count'] > 0:
                atn_query = """
                MATCH (atn:ATNProfile)
                WITH atn.profile as atn_profile, count(atn) as count
                ORDER BY count DESC
                RETURN atn_profile, count
                """

                result = self.connector.run_query(atn_query)
                self.analysis['atn_distribution'] = result
            else:
                # Alternative: analyze biomarker profiles
                alt_query = """
                MATCH (bp:BiomarkerProfile)
                WITH bp.atn_status as atn, count(bp) as count
                ORDER BY count DESC
                RETURN atn as atn_profile, count
                """

                result = self.connector.run_query(alt_query)
                self.analysis['atn_distribution'] = result
        except Exception as e:
            logger.warning(f"Failed to analyze ATN distribution: {e}")
            self.analysis['atn_distribution'] = []

        # Biomarker abnormality rates
        abnormal_query = """
        MATCH (b:Biomarker)
        WITH b.analyte as analyte,
             count(b) as total,
             sum(CASE WHEN b.abnormal_flag = true THEN 1 ELSE 0 END) as abnormal
        WHERE total >= 10
        RETURN analyte,
               total as measurements,
               abnormal as abnormal_count,
               round(100.0 * abnormal / total, 1) as abnormal_percentage
        ORDER BY abnormal_percentage DESC
        """

        try:
            result = self.connector.run_query(abnormal_query)
            self.analysis['biomarker_abnormality_rates'] = result
        except Exception as e:
            logger.warning(f"Failed to analyze biomarker abnormality rates: {e}")
            self.analysis['biomarker_abnormality_rates'] = []

    def _analyze_connectivity(self):
        """Analyze graph connectivity metrics"""

        logger.info("Analyzing graph connectivity...")

        # Connected components - simplified version
        components_query = """
        MATCH (p:Patient)
        OPTIONAL MATCH (p)-[r]-()
        WITH p, count(r) as connections
        WITH CASE 
            WHEN connections = 0 THEN 'isolated'
            WHEN connections < 5 THEN 'low'
            WHEN connections < 20 THEN 'medium'
            ELSE 'high'
        END as connectivity_level, count(p) as patient_count
        ORDER BY patient_count DESC
        RETURN connectivity_level, patient_count
        """

        try:
            result = self.connector.run_query(components_query)
            self.analysis['connectivity_distribution'] = result
        except Exception as e:
            logger.warning(f"Failed to analyze connectivity: {e}")
            self.analysis['connectivity_distribution'] = []

    def _generate_summary(self):
        """Generate summary statistics"""

        logger.info("\nGenerating summary report...")

        # Overall graph statistics
        stats_query = """
        MATCH (n)
        WITH count(n) as node_count
        OPTIONAL MATCH ()-[r]->()
        WITH node_count, count(r) as relationship_count
        RETURN node_count, 
               relationship_count,
               CASE 
                   WHEN node_count > 0 
                   THEN toFloat(relationship_count) / toFloat(node_count) 
                   ELSE 0.0 
               END as avg_degree
        """

        try:
            result = self.connector.run_query(stats_query)
            if result:
                self.analysis['graph_statistics'] = result[0]
        except Exception as e:
            logger.warning(f"Failed to generate graph statistics: {e}")
            self.analysis['graph_statistics'] = {
                'node_count': 0,
                'relationship_count': 0,
                'avg_degree': 0.0
            }

        # Print summary to console
        logger.info("\n" + "=" * 60)
        logger.info("GRAPH ANALYSIS SUMMARY")
        logger.info("=" * 60)

        if 'graph_statistics' in self.analysis:
            stats = self.analysis['graph_statistics']
            logger.info(f"Total Nodes: {stats.get('node_count', 0):,}")
            logger.info(f"Total Relationships: {stats.get('relationship_count', 0):,}")
            logger.info(f"Average Degree: {stats.get('avg_degree', 0):.2f}")

        if 'patient_demographics' in self.analysis:
            demo = self.analysis['patient_demographics']
            logger.info(f"\nPatient Statistics:")
            logger.info(f"  Total Patients: {demo.get('total_patients', 0)}")
            if demo.get('avg_age'):
                logger.info(f"  Average Age: {demo['avg_age']:.1f}")
            logger.info(f"  APOE4 Carriers: {demo.get('apoe4_carriers', 0)}")

        if 'top_relationships' in self.analysis:
            logger.info(f"\nTop Relationship Types:")
            for rel in self.analysis['top_relationships'][:5]:
                logger.info(f"  {rel['rel_type']}: {rel['count']:,}")

        if 'node_distribution' in self.analysis:
            logger.info(f"\nNode Distribution:")
            for node_type, info in list(self.analysis['node_distribution'].items())[:5]:
                logger.info(f"  {node_type}: {info['count']:,} ({info['percentage']:.1f}%)")


def execute_graph_eda(neo4j_uri: str, neo4j_user: str, neo4j_password: str) -> Dict[str, Any]:
    """Execute graph exploratory data analysis"""

    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)

    try:
        explorer = GraphExplorer(connector)
        results = explorer.execute()

        return results

    except Exception as e:
        logger.error(f"Graph EDA failed: {e}")
        raise
    finally:
        connector.close()