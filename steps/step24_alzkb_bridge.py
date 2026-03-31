"""
Step 24 – AlzKB Bridge
======================
Downloads the AlzKB CYPHERL dump from GitHub, parses it to extract
AD-relevant concepts (genes, diseases, anatomy, pathways, drugs),
creates :AlzKBConcept nodes in Neo4j, and links them to existing
OntologyConcept / CausalVariable nodes via :SAME_AS edges.

Output
------
- AlzKBConcept nodes in Neo4j
- SAME_AS relationships (AlzKBConcept → OntologyConcept / CausalVariable)
- ontology/alzkb_cache/alzkb_concepts.json  (parsed concepts)
- ontology/alzkb_cache/alzkb_bridge_report.json
"""

import logging
import json
import re
import os
import gzip
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────
# ALZKB CONCEPT DEFINITIONS (manual fallback)
# ────────────────────────────────────────────────────────────────
# If the CYPHERL download fails, we use this curated set of ~50
# key concepts from the AlzKB paper (Khemani et al., 2024).

MANUAL_ALZKB_CONCEPTS = [
    # Genes
    {'alzkb_id': 'alzkb:gene_APOE',   'label': 'APOE',   'source_type': 'Gene',   'gene_id': '348'},
    {'alzkb_id': 'alzkb:gene_APP',    'label': 'APP',    'source_type': 'Gene',   'gene_id': '351'},
    {'alzkb_id': 'alzkb:gene_PSEN1',  'label': 'PSEN1',  'source_type': 'Gene',   'gene_id': '5663'},
    {'alzkb_id': 'alzkb:gene_PSEN2',  'label': 'PSEN2',  'source_type': 'Gene',   'gene_id': '5664'},
    {'alzkb_id': 'alzkb:gene_MAPT',   'label': 'MAPT',   'source_type': 'Gene',   'gene_id': '4137'},
    {'alzkb_id': 'alzkb:gene_TREM2',  'label': 'TREM2',  'source_type': 'Gene',   'gene_id': '54209'},
    {'alzkb_id': 'alzkb:gene_CLU',    'label': 'CLU',    'source_type': 'Gene',   'gene_id': '1191'},
    {'alzkb_id': 'alzkb:gene_BIN1',   'label': 'BIN1',   'source_type': 'Gene',   'gene_id': '274'},
    {'alzkb_id': 'alzkb:gene_ABCA7',  'label': 'ABCA7',  'source_type': 'Gene',   'gene_id': '10347'},
    {'alzkb_id': 'alzkb:gene_CD33',   'label': 'CD33',   'source_type': 'Gene',   'gene_id': '945'},
    {'alzkb_id': 'alzkb:gene_CR1',    'label': 'CR1',    'source_type': 'Gene',   'gene_id': '1378'},
    {'alzkb_id': 'alzkb:gene_SORL1',  'label': 'SORL1',  'source_type': 'Gene',   'gene_id': '6653'},
    {'alzkb_id': 'alzkb:gene_ADAM10', 'label': 'ADAM10', 'source_type': 'Gene',   'gene_id': '102'},
    {'alzkb_id': 'alzkb:gene_BACE1',  'label': 'BACE1',  'source_type': 'Gene',   'gene_id': '23621'},
    {'alzkb_id': 'alzkb:gene_BDNF',   'label': 'BDNF',   'source_type': 'Gene',   'gene_id': '627'},

    # Diseases
    {'alzkb_id': 'alzkb:disease_AD',       'label': "Alzheimer's disease",          'source_type': 'Disease', 'disease_id': 'DOID:10652'},
    {'alzkb_id': 'alzkb:disease_EOAD',     'label': 'Early-onset Alzheimer disease', 'source_type': 'Disease', 'disease_id': 'DOID:0110041'},
    {'alzkb_id': 'alzkb:disease_LOAD',     'label': 'Late-onset Alzheimer disease',  'source_type': 'Disease', 'disease_id': 'DOID:0110042'},
    {'alzkb_id': 'alzkb:disease_dementia', 'label': 'Dementia',                      'source_type': 'Disease', 'disease_id': 'DOID:1307'},
    {'alzkb_id': 'alzkb:disease_MCI',      'label': 'Mild cognitive impairment',     'source_type': 'Disease', 'disease_id': 'DOID:0060903'},
    {'alzkb_id': 'alzkb:disease_tauopathy','label': 'Tauopathy',                     'source_type': 'Disease', 'disease_id': 'DOID:680'},

    # Anatomy
    {'alzkb_id': 'alzkb:anatomy_hippocampus',    'label': 'Hippocampus',              'source_type': 'Anatomy', 'mesh_id': 'D006624'},
    {'alzkb_id': 'alzkb:anatomy_entorhinal',     'label': 'Entorhinal cortex',        'source_type': 'Anatomy', 'mesh_id': 'D018728'},
    {'alzkb_id': 'alzkb:anatomy_temporal_lobe',  'label': 'Temporal lobe',            'source_type': 'Anatomy', 'mesh_id': 'D013702'},
    {'alzkb_id': 'alzkb:anatomy_frontal_lobe',   'label': 'Frontal lobe',             'source_type': 'Anatomy', 'mesh_id': 'D005625'},
    {'alzkb_id': 'alzkb:anatomy_amygdala',       'label': 'Amygdala',                 'source_type': 'Anatomy', 'mesh_id': 'D000679'},
    {'alzkb_id': 'alzkb:anatomy_cerebral_cortex','label': 'Cerebral cortex',          'source_type': 'Anatomy', 'mesh_id': 'D002540'},
    {'alzkb_id': 'alzkb:anatomy_csf',            'label': 'Cerebrospinal fluid',      'source_type': 'Anatomy', 'mesh_id': 'D002555'},

    # Biological Processes
    {'alzkb_id': 'alzkb:bp_amyloid_beta',    'label': 'Amyloid-beta formation',         'source_type': 'BiologicalProcess', 'go_id': 'GO:0034205'},
    {'alzkb_id': 'alzkb:bp_tau_phosph',      'label': 'Tau protein phosphorylation',    'source_type': 'BiologicalProcess', 'go_id': 'GO:0050886'},
    {'alzkb_id': 'alzkb:bp_neuroinflammation','label': 'Neuroinflammatory response',    'source_type': 'BiologicalProcess', 'go_id': 'GO:0150076'},
    {'alzkb_id': 'alzkb:bp_apoptosis',       'label': 'Neuronal apoptotic process',     'source_type': 'BiologicalProcess', 'go_id': 'GO:0051402'},
    {'alzkb_id': 'alzkb:bp_synaptic',        'label': 'Synaptic transmission',          'source_type': 'BiologicalProcess', 'go_id': 'GO:0007268'},
    {'alzkb_id': 'alzkb:bp_autophagy',       'label': 'Autophagy',                      'source_type': 'BiologicalProcess', 'go_id': 'GO:0006914'},
    {'alzkb_id': 'alzkb:bp_oxidative_stress','label': 'Response to oxidative stress',   'source_type': 'BiologicalProcess', 'go_id': 'GO:0006979'},

    # Pathways
    {'alzkb_id': 'alzkb:pw_amyloid_precursor', 'label': 'Amyloid precursor protein pathway', 'source_type': 'Pathway'},
    {'alzkb_id': 'alzkb:pw_wnt_signaling',     'label': 'Wnt signaling pathway',              'source_type': 'Pathway'},
    {'alzkb_id': 'alzkb:pw_pi3k_akt',          'label': 'PI3K-Akt signaling pathway',         'source_type': 'Pathway'},
    {'alzkb_id': 'alzkb:pw_mapk',              'label': 'MAPK signaling pathway',              'source_type': 'Pathway'},
    {'alzkb_id': 'alzkb:pw_notch',             'label': 'Notch signaling pathway',              'source_type': 'Pathway'},

    # Drugs (common AD therapeutics)
    {'alzkb_id': 'alzkb:drug_donepezil',   'label': 'Donepezil',     'source_type': 'Drug', 'drugbank_id': 'DB00843'},
    {'alzkb_id': 'alzkb:drug_memantine',   'label': 'Memantine',     'source_type': 'Drug', 'drugbank_id': 'DB01043'},
    {'alzkb_id': 'alzkb:drug_rivastigmine','label': 'Rivastigmine',  'source_type': 'Drug', 'drugbank_id': 'DB00989'},
    {'alzkb_id': 'alzkb:drug_galantamine', 'label': 'Galantamine',   'source_type': 'Drug', 'drugbank_id': 'DB00674'},
    {'alzkb_id': 'alzkb:drug_aducanumab',  'label': 'Aducanumab',    'source_type': 'Drug', 'drugbank_id': 'DB14580'},
    {'alzkb_id': 'alzkb:drug_lecanemab',   'label': 'Lecanemab',     'source_type': 'Drug', 'drugbank_id': 'DB16649'},
]

# AlzKB relationships (manual — key edges from the knowledge base)
MANUAL_ALZKB_RELATIONSHIPS = [
    {'source': 'alzkb:gene_APOE',   'target': 'alzkb:disease_AD',      'type': 'GENEASSOCIATESWITHDISEASE'},
    {'source': 'alzkb:gene_APP',    'target': 'alzkb:disease_AD',      'type': 'GENEASSOCIATESWITHDISEASE'},
    {'source': 'alzkb:gene_PSEN1',  'target': 'alzkb:disease_EOAD',    'type': 'GENEASSOCIATESWITHDISEASE'},
    {'source': 'alzkb:gene_PSEN2',  'target': 'alzkb:disease_EOAD',    'type': 'GENEASSOCIATESWITHDISEASE'},
    {'source': 'alzkb:gene_MAPT',   'target': 'alzkb:disease_AD',      'type': 'GENEASSOCIATESWITHDISEASE'},
    {'source': 'alzkb:gene_TREM2',  'target': 'alzkb:disease_AD',      'type': 'GENEASSOCIATESWITHDISEASE'},
    {'source': 'alzkb:gene_CLU',    'target': 'alzkb:disease_AD',      'type': 'GENEASSOCIATESWITHDISEASE'},
    {'source': 'alzkb:gene_BIN1',   'target': 'alzkb:disease_AD',      'type': 'GENEASSOCIATESWITHDISEASE'},
    {'source': 'alzkb:gene_BACE1',  'target': 'alzkb:bp_amyloid_beta', 'type': 'GENEPARTICIPATESBP'},
    {'source': 'alzkb:gene_MAPT',   'target': 'alzkb:bp_tau_phosph',   'type': 'GENEPARTICIPATESBP'},
    {'source': 'alzkb:disease_AD',  'target': 'alzkb:anatomy_hippocampus', 'type': 'DISEASELOCALIZESTOANATOMY'},
    {'source': 'alzkb:disease_AD',  'target': 'alzkb:anatomy_entorhinal',  'type': 'DISEASELOCALIZESTOANATOMY'},
    {'source': 'alzkb:disease_AD',  'target': 'alzkb:anatomy_temporal_lobe', 'type': 'DISEASELOCALIZESTOANATOMY'},
    {'source': 'alzkb:disease_AD',  'target': 'alzkb:anatomy_cerebral_cortex', 'type': 'DISEASELOCALIZESTOANATOMY'},
    {'source': 'alzkb:drug_donepezil', 'target': 'alzkb:disease_AD',   'type': 'DRUGTREATSDISEASE'},
    {'source': 'alzkb:drug_memantine', 'target': 'alzkb:disease_AD',   'type': 'DRUGTREATSDISEASE'},
    {'source': 'alzkb:drug_aducanumab','target': 'alzkb:disease_AD',   'type': 'DRUGTREATSDISEASE'},
    {'source': 'alzkb:drug_lecanemab', 'target': 'alzkb:disease_AD',   'type': 'DRUGTREATSDISEASE'},
]


# ────────────────────────────────────────────────────────────────
# SAME_AS MAPPING RULES
# ────────────────────────────────────────────────────────────────
# Maps AlzKB concept IDs → our OntologyConcept URIs or CausalVariable IDs.

SAME_AS_RULES = [
    # Genes → CausalVariable
    {'alzkb_id': 'alzkb:gene_APOE',  'target_label': 'CausalVariable', 'target_key': 'variable_id', 'target_value': 'apoe_e4_count', 'method': 'manual_gene'},

    # Diseases → OntologyConcept
    {'alzkb_id': 'alzkb:disease_AD',      'target_label': 'OntologyConcept', 'target_key': 'uri', 'target_value': 'snomed:26929004', 'method': 'manual_disease'},
    {'alzkb_id': 'alzkb:disease_dementia','target_label': 'OntologyConcept', 'target_key': 'uri', 'target_value': 'snomed:52448006', 'method': 'manual_disease'},
    {'alzkb_id': 'alzkb:disease_MCI',     'target_label': 'OntologyConcept', 'target_key': 'uri', 'target_value': 'hpo:HP:0100543',  'method': 'manual_disease'},

    # Anatomy → OntologyConcept (UBERON)
    {'alzkb_id': 'alzkb:anatomy_hippocampus',    'target_label': 'OntologyConcept', 'target_key': 'uri', 'target_value': 'uberon:UBERON:0002421', 'method': 'manual_anatomy'},
    {'alzkb_id': 'alzkb:anatomy_entorhinal',     'target_label': 'OntologyConcept', 'target_key': 'uri', 'target_value': 'uberon:UBERON:0002728', 'method': 'manual_anatomy'},
    {'alzkb_id': 'alzkb:anatomy_amygdala',       'target_label': 'OntologyConcept', 'target_key': 'uri', 'target_value': 'uberon:UBERON:0001876', 'method': 'manual_anatomy'},
    {'alzkb_id': 'alzkb:anatomy_cerebral_cortex','target_label': 'OntologyConcept', 'target_key': 'uri', 'target_value': 'uberon:UBERON:0000956', 'method': 'manual_anatomy'},

    # CSF biomarkers → CausalVariable
    {'alzkb_id': 'alzkb:bp_amyloid_beta', 'target_label': 'CausalVariable', 'target_key': 'variable_id', 'target_value': 'BIO_ABETA',  'method': 'manual_biomarker'},
    {'alzkb_id': 'alzkb:bp_tau_phosph',   'target_label': 'CausalVariable', 'target_key': 'variable_id', 'target_value': 'BIO_PTAU',  'method': 'manual_biomarker'},
]


# ────────────────────────────────────────────────────────────────
# CYPHERL PARSER
# ────────────────────────────────────────────────────────────────

# Regex patterns for parsing CREATE statements from the CYPHERL dump
_CREATE_NODE_RE = re.compile(
    r"CREATE\s*\(:\s*(\w+)\s*\{(.+?)\}\s*\)",
    re.IGNORECASE | re.DOTALL,
)
_PROP_RE = re.compile(r"(\w+)\s*:\s*(?:'([^']*)'|\"([^\"]*)\"|(\d+\.?\d*))")

# AD-relevant keywords for filtering
_AD_KEYWORDS = {
    'alzheimer', 'dementia', 'amyloid', 'tau', 'apoe', 'hippocampus',
    'entorhinal', 'temporal', 'frontal', 'parietal', 'cerebral', 'cortex',
    'cerebrospinal', 'neurodegeneration', 'cognitive', 'memory',
    'donepezil', 'memantine', 'rivastigmine', 'galantamine', 'aducanumab',
    'lecanemab', 'bace', 'presenilin', 'psen1', 'psen2', 'app',
    'trem2', 'clu', 'bin1', 'abca7', 'sorl1', 'mapt', 'bdnf',
    'synaptic', 'neuroinflam', 'autophagy', 'oxidative',
}

_NODE_TYPES_OF_INTEREST = {'Gene', 'Disease', 'Anatomy', 'BiologicalProcess',
                           'Pathway', 'Drug', 'Symptom'}


def _parse_props(prop_str: str) -> Dict[str, str]:
    """Parse property key-value pairs from a Cypher property string."""
    props = {}
    for match in _PROP_RE.finditer(prop_str):
        key = match.group(1)
        value = match.group(2) or match.group(3) or match.group(4)
        if value is not None:
            props[key] = value
    return props


def _is_ad_relevant(props: Dict[str, str]) -> bool:
    """Check if a concept is AD-relevant by keyword matching."""
    text = ' '.join(str(v).lower() for v in props.values())
    return any(kw in text for kw in _AD_KEYWORDS)


def parse_cypherl(content: str, max_concepts: int = 200) -> List[Dict]:
    """Parse CYPHERL dump and extract AD-relevant concepts."""
    concepts = []

    for match in _CREATE_NODE_RE.finditer(content):
        node_type = match.group(1)
        if node_type not in _NODE_TYPES_OF_INTEREST:
            continue

        props = _parse_props(match.group(2))
        if not _is_ad_relevant(props):
            continue

        label = (props.get('commonName') or props.get('name') or
                 props.get('label') or 'Unknown')

        concept = {
            'alzkb_id': f"alzkb:{node_type.lower()}_{label.replace(' ', '_')[:40]}",
            'label': label,
            'source_type': node_type,
        }

        # Carry over key identifiers
        for key in ('geneId', 'diseaseId', 'meshId', 'goId',
                    'drugbankId', 'commonName', 'sourceDatabase'):
            if key in props:
                concept[key.lower()] = props[key]

        concepts.append(concept)

        if len(concepts) >= max_concepts:
            break

    return concepts


# ────────────────────────────────────────────────────────────────
# CYPHER TEMPLATES
# ────────────────────────────────────────────────────────────────

MERGE_ALZKB_CONCEPT = """
UNWIND $concepts AS c
MERGE (a:AlzKBConcept {alzkb_id: c.alzkb_id})
SET a.label = c.label,
    a.source_type = c.source_type,
    a.properties = c.properties,
    a.created_at = datetime()
"""

MERGE_ALZKB_RELATIONSHIP = """
UNWIND $rels AS rel
MATCH (src:AlzKBConcept {alzkb_id: rel.source})
MATCH (tgt:AlzKBConcept {alzkb_id: rel.target})
MERGE (src)-[r:ALZKB_RELATES_TO {type: rel.type}]->(tgt)
SET r.created_at = datetime()
"""

MERGE_SAME_AS_ONTOLOGY = """
MATCH (a:AlzKBConcept {alzkb_id: $alzkb_id})
MATCH (o {%s: $target_value})
WHERE o:%s
MERGE (a)-[r:SAME_AS]->(o)
SET r.uri = 'owl:sameAs',
    r.match_method = $method,
    r.created_at = datetime()
"""

COUNT_ALZKB = "MATCH (a:AlzKBConcept) RETURN count(a) AS total"
COUNT_SAME_AS = "MATCH ()-[r:SAME_AS]->() RETURN count(r) AS total"


# ────────────────────────────────────────────────────────────────
# Bridge class
# ────────────────────────────────────────────────────────────────

class AlzKBBridge:
    """Downloads/parses AlzKB data and creates bridge nodes in Neo4j."""

    RELEASES_URL = ("https://api.github.com/repos/EpistasisLab/AlzKB/"
                    "releases/latest")

    def __init__(self, connector, config: Dict[str, Any]):
        self.connector = connector
        self.alzkb_config = config.get('alzkb', {})
        self.max_concepts = self.alzkb_config.get('max_concepts', 200)
        self.cache_dir = Path(self.alzkb_config.get('cache_dir',
                                                     'ontology/alzkb_cache'))
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def execute(self) -> Dict[str, Any]:
        """Main entry-point."""
        logger.info("=" * 60)
        logger.info("STEP 24 — AlzKB Bridge")
        logger.info("=" * 60)

        results = {
            'step': 24,
            'status': 'started',
            'timestamp': datetime.now().isoformat(),
        }

        try:
            # 1. Try downloading CYPHERL dump
            concepts = self._try_download_cypherl()

            if not concepts:
                logger.info("  Using manual curated AlzKB concepts (fallback)")
                concepts = MANUAL_ALZKB_CONCEPTS

            logger.info(f"  Working with {len(concepts)} AlzKB concepts")

            # 2. Save parsed concepts
            cache_path = self.cache_dir / 'alzkb_concepts.json'
            with open(cache_path, 'w') as f:
                json.dump(concepts, f, indent=2)
            logger.info(f"  Saved concepts to {cache_path}")

            # 3. Create AlzKBConcept nodes
            self._create_concepts(concepts)

            # 4. Create AlzKB internal relationships
            self._create_alzkb_relationships()

            # 5. Create SAME_AS edges
            same_as_count = self._create_same_as_edges()

            # 6. Try fuzzy matching for additional SAME_AS
            fuzzy_count = self._fuzzy_match_same_as(concepts)

            # 7. Verify
            concept_count = self.connector.run_query(COUNT_ALZKB)
            total_concepts = concept_count[0]['total'] if concept_count else 0

            same_as_result = self.connector.run_query(COUNT_SAME_AS)
            total_same_as = same_as_result[0]['total'] if same_as_result else 0

            # 8. Save report
            report = {
                'concepts_created': total_concepts,
                'same_as_edges': total_same_as,
                'manual_same_as': same_as_count,
                'fuzzy_same_as': fuzzy_count,
                'source': 'manual_curated' if not self._cypherl_downloaded else 'cypherl_parsed',
                'timestamp': datetime.now().isoformat(),
            }
            report_path = self.cache_dir / 'alzkb_bridge_report.json'
            with open(report_path, 'w') as f:
                json.dump(report, f, indent=2)

            results.update({
                'status': 'completed',
                'concepts_created': total_concepts,
                'same_as_edges': total_same_as,
                'report_path': str(report_path),
            })

            logger.info(f"✅ Step 24 complete — {total_concepts} AlzKBConcept "
                        f"nodes, {total_same_as} SAME_AS edges")

        except Exception as e:
            logger.error(f"Step 24 failed: {e}", exc_info=True)
            results['status'] = 'failed'
            results['error'] = str(e)

        return results

    # ── Download ─────────────────────────────────────────────

    _cypherl_downloaded = False

    def _try_download_cypherl(self) -> Optional[List[Dict]]:
        """Try to download and parse the CYPHERL dump."""
        cached = self.cache_dir / 'alzkb_concepts.json'
        if cached.exists():
            logger.info(f"  Using cached concepts from {cached}")
            with open(cached) as f:
                concepts = json.load(f)
            if concepts:
                return concepts

        logger.info("  Attempting to download AlzKB CYPHERL dump...")
        try:
            # Get latest release info
            req = Request(self.RELEASES_URL,
                          headers={'Accept': 'application/json',
                                   'User-Agent': 'ADNI-KG-Pipeline/1.0'})
            with urlopen(req, timeout=15) as resp:
                release = json.loads(resp.read().decode())

            # Look for CYPHERL asset or link in release body
            body = release.get('body', '')
            assets = release.get('assets', [])

            cypherl_url = None
            for asset in assets:
                name = asset.get('name', '').lower()
                if 'cypherl' in name or name.endswith('.cypherl'):
                    cypherl_url = asset.get('browser_download_url')
                    break

            # Some releases link to Zenodo in the body text
            if not cypherl_url:
                zenodo_match = re.search(r'https://zenodo\.org/\S+', body)
                if zenodo_match:
                    logger.info("  Found Zenodo link, but skipping large download")
                    return None

            if not cypherl_url:
                logger.info("  No CYPHERL asset found in latest release")
                return None

            logger.info(f"  Downloading: {cypherl_url}")
            req = Request(cypherl_url,
                          headers={'User-Agent': 'ADNI-KG-Pipeline/1.0'})
            with urlopen(req, timeout=120) as resp:
                content = resp.read()

            # Handle gzipped
            if cypherl_url.endswith('.gz'):
                content = gzip.decompress(content)

            text = content.decode('utf-8', errors='replace')
            concepts = parse_cypherl(text, self.max_concepts)
            self._cypherl_downloaded = True
            logger.info(f"  Parsed {len(concepts)} AD-relevant concepts")
            return concepts if concepts else None

        except (URLError, TimeoutError, json.JSONDecodeError) as e:
            logger.warning(f"  CYPHERL download failed: {e}")
            return None

    # ── Neo4j operations ─────────────────────────────────────

    def _create_concepts(self, concepts: List[Dict]) -> None:
        """Create AlzKBConcept nodes."""
        logger.info("  Creating AlzKBConcept nodes...")

        records = []
        for c in concepts:
            # Collect extra properties as JSON string
            extra = {k: v for k, v in c.items()
                     if k not in ('alzkb_id', 'label', 'source_type')}
            records.append({
                'alzkb_id': c['alzkb_id'],
                'label': c['label'],
                'source_type': c['source_type'],
                'properties': json.dumps(extra) if extra else '{}',
            })

        self.connector.run_query(MERGE_ALZKB_CONCEPT, {'concepts': records})
        logger.info(f"  Created {len(records)} AlzKBConcept nodes")

    def _create_alzkb_relationships(self) -> None:
        """Create internal AlzKB relationships."""
        logger.info("  Creating AlzKB internal relationships...")

        self.connector.run_query(
            MERGE_ALZKB_RELATIONSHIP,
            {'rels': MANUAL_ALZKB_RELATIONSHIPS}
        )
        logger.info(f"  Created {len(MANUAL_ALZKB_RELATIONSHIPS)} AlzKB relationships")

    def _create_same_as_edges(self) -> int:
        """Create SAME_AS edges using manual mapping rules."""
        logger.info("  Creating SAME_AS edges (manual mapping)...")
        count = 0

        for rule in SAME_AS_RULES:
            try:
                query = MERGE_SAME_AS_ONTOLOGY % (
                    rule['target_key'], rule['target_label']
                )
                self.connector.run_query(query, {
                    'alzkb_id': rule['alzkb_id'],
                    'target_value': rule['target_value'],
                    'method': rule['method'],
                })
                count += 1
            except Exception as e:
                logger.debug(f"  SAME_AS skipped for {rule['alzkb_id']}: {e}")

        logger.info(f"  Created {count} SAME_AS edges (manual)")
        return count

    def _fuzzy_match_same_as(self, concepts: List[Dict]) -> int:
        """Try fuzzy label matching for remaining AlzKBConcepts."""
        logger.info("  Attempting fuzzy SAME_AS matching...")
        count = 0

        # Get already-linked concepts
        linked = set()
        for rule in SAME_AS_RULES:
            linked.add(rule['alzkb_id'])

        for concept in concepts:
            if concept['alzkb_id'] in linked:
                continue

            label = concept['label'].lower()

            # Try matching OntologyConcept by label
            query = """
            MATCH (a:AlzKBConcept {alzkb_id: $alzkb_id})
            MATCH (o:OntologyConcept)
            WHERE toLower(o.label) = $label
            MERGE (a)-[r:SAME_AS]->(o)
            SET r.uri = 'owl:sameAs',
                r.match_method = 'fuzzy_label',
                r.created_at = datetime()
            RETURN count(r) AS cnt
            """
            try:
                result = self.connector.run_query(query, {
                    'alzkb_id': concept['alzkb_id'],
                    'label': label,
                })
                if result and result[0].get('cnt', 0) > 0:
                    count += result[0]['cnt']
            except Exception:
                pass

        logger.info(f"  Created {count} SAME_AS edges (fuzzy)")
        return count


# ────────────────────────────────────────────────────────────────
# CLI + pipeline integration
# ────────────────────────────────────────────────────────────────

def execute_alzkb_bridge(config: Dict[str, Any],
                         connector=None) -> Dict[str, Any]:
    """Pipeline entry-point for Step 24."""
    if connector is None:
        from utils.neo4j_connector import Neo4jConnector
        connector = Neo4jConnector(
            config['neo4j']['uri'],
            config['neo4j']['user'],
            config['neo4j']['password']
        )

    bridge = AlzKBBridge(connector, config)
    return bridge.execute()


if __name__ == '__main__':
    import yaml
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
    )

    config_path = Path(__file__).parent.parent / 'config.yaml'
    if config_path.exists():
        with open(config_path) as f:
            config = yaml.safe_load(f)
    else:
        config = {}

    result = execute_alzkb_bridge(config)
    print(json.dumps(result, indent=2, default=str))
