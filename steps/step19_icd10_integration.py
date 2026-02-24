"""
Step 19: ICD-10 Integration
============================
Creates OntologyConcept nodes for ICD-10 codes, builds IS_A hierarchy,
and links Diagnosis nodes via CLASSIFIED_AS relationships.

Resolution order:
  1. WHO ICD REST API (OAuth2) → cache to ontology/icd10_cache.json
  2. Static mapping fallback → ontology/icd10_mappings.json

Usage:
    python -m steps.step19_icd10_integration --neo4j-password your_password
"""

import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional

from utils.neo4j_connector import Neo4jConnector

logger = logging.getLogger(__name__)

# Paths
ONTOLOGY_DIR = Path(__file__).parent.parent / "ontology"
STATIC_MAPPING_FILE = ONTOLOGY_DIR / "icd10_mappings.json"
CACHE_FILE = ONTOLOGY_DIR / "icd10_cache.json"


# ══════════════════════════════════════════════════════════════════════
# WHO ICD API Client
# ══════════════════════════════════════════════════════════════════════

class WHOICDApiClient:
    """WHO ICD-10 REST API client with OAuth2 and caching."""

    TOKEN_URL = "https://icdaccessmanagement.who.int/connect/token"
    BASE_URL = "https://id.who.int/icd/release/10"

    def __init__(self, client_id: str, client_secret: str, release: str = "2019"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.release = release
        self._token: Optional[str] = None
        self._token_expires: float = 0
        self._cache: Dict[str, Any] = {}
        self._load_cache()

    def _load_cache(self):
        """Load cached API responses."""
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, "r") as f:
                    self._cache = json.load(f)
                logger.info(f"  Loaded {len(self._cache)} cached ICD-10 entries")
            except Exception:
                self._cache = {}

    def _save_cache(self):
        """Persist cache to disk."""
        ONTOLOGY_DIR.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump(self._cache, f, indent=2)

    def _get_token(self) -> Optional[str]:
        """Get OAuth2 access token via client_credentials grant."""
        if self._token and time.time() < self._token_expires:
            return self._token

        try:
            import urllib.request
            import urllib.parse

            data = urllib.parse.urlencode({
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "icdapi_access",
            }).encode()

            req = urllib.request.Request(self.TOKEN_URL, data=data)
            req.add_header("Content-Type", "application/x-www-form-urlencoded")

            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
                self._token = result["access_token"]
                self._token_expires = time.time() + result.get("expires_in", 3600) - 60
                logger.info("  ✅ WHO ICD API: OAuth2 token acquired")
                return self._token
        except Exception as e:
            logger.warning(f"  ⚠️  WHO ICD API token failed: {e}")
            return None

    def get_code(self, code: str) -> Optional[Dict[str, Any]]:
        """
        Look up an ICD-10 code. Returns {code, label, parent, definition}
        or None if unavailable.
        """
        # Check cache first
        if code in self._cache:
            return self._cache[code]

        token = self._get_token()
        if not token:
            return None

        try:
            import urllib.request

            url = f"{self.BASE_URL}/{self.release}/{code}"
            req = urllib.request.Request(url)
            req.add_header("Authorization", f"Bearer {token}")
            req.add_header("Accept", "application/json")
            req.add_header("Accept-Language", "en")
            req.add_header("API-Version", "v2")

            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())

            result = {
                "code": code,
                "label": data.get("title", {}).get("@value", code),
                "parent": self._extract_parent(data),
                "definition": data.get("definition", {}).get("@value", ""),
                "resolved_via": "WHO_API",
            }
            self._cache[code] = result
            self._save_cache()
            return result

        except Exception as e:
            logger.debug(f"  WHO API lookup for {code} failed: {e}")
            return None

    def _extract_parent(self, data: dict) -> str:
        """Extract parent code from API response."""
        parents = data.get("parent", [])
        if isinstance(parents, list) and parents:
            # Parent URL like http://id.who.int/icd/release/10/2019/G30
            parent_url = parents[0]
            return parent_url.rsplit("/", 1)[-1] if "/" in parent_url else ""
        return ""


# ══════════════════════════════════════════════════════════════════════
# Static Mapping Loader
# ══════════════════════════════════════════════════════════════════════

def load_static_mappings() -> Dict[str, Dict[str, Any]]:
    """Load ICD-10 mappings from static JSON file."""
    if not STATIC_MAPPING_FILE.exists():
        logger.warning(f"  Static mapping file not found: {STATIC_MAPPING_FILE}")
        return {}
    with open(STATIC_MAPPING_FILE, "r") as f:
        data = json.load(f)
    concepts = data.get("concepts", {})
    # Add resolved_via marker
    for code in concepts:
        concepts[code]["resolved_via"] = "static_mapping"
    logger.info(f"  Loaded {len(concepts)} ICD-10 codes from static mapping")
    return concepts


# ══════════════════════════════════════════════════════════════════════
class ICD10Integrator:
    """Creates ICD-10 OntologyConcept nodes and relationships."""

    def __init__(self, connector: Neo4jConnector, config: Dict[str, Any] = None):
        self.connector = connector
        self.config = config or {}

    def execute(self) -> Dict[str, Any]:
        """Run full ICD-10 integration."""
        results = {
            "concepts_created": 0,
            "is_a_edges": 0,
            "classified_as_edges": 0,
            "resolution_method": "unknown",
        }

        # ── 1. Resolve ICD-10 codes ──────────────────────────────────
        codes = self._resolve_codes()
        if not codes:
            logger.error("  ❌ No ICD-10 codes resolved — aborting")
            return results
        results["resolution_method"] = next(iter(codes.values())).get("resolved_via", "?")

        # ── 2. Create OntologyConcept nodes ──────────────────────────
        results["concepts_created"] = self._create_concepts(codes)

        # ── 3. Build IS_A hierarchy ──────────────────────────────────
        results["is_a_edges"] = self._create_hierarchy(codes)

        # ── 4. Create CLASSIFIED_AS edges from Diagnosis ─────────────
        results["classified_as_edges"] = self._create_classified_as()

        # ── Summary ──────────────────────────────────────────────────
        logger.info("")
        logger.info("=" * 60)
        logger.info("STEP 19 — ICD-10 INTEGRATION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"  Resolution method:    {results['resolution_method']}")
        logger.info(f"  Concepts created:     {results['concepts_created']}")
        logger.info(f"  IS_A edges created:   {results['is_a_edges']}")
        logger.info(f"  CLASSIFIED_AS edges:  {results['classified_as_edges']}")
        logger.info("=" * 60)

        return results

    def _resolve_codes(self) -> Dict[str, Dict[str, Any]]:
        """Resolve all needed ICD-10 codes via API or static fallback."""
        # Determine which ICD-10 codes exist in our graph
        icd_codes = set()
        res = self.connector.run_query(
            "MATCH (d:Diagnosis) WHERE d.icd10_code IS NOT NULL "
            "RETURN DISTINCT d.icd10_code AS code"
        )
        for r in res:
            icd_codes.add(r["code"])
        logger.info(f"  Found {len(icd_codes)} distinct ICD-10 codes in graph")

        # Try WHO API first
        api_client = None
        client_id = self.config.get("who_icd_client_id", "")
        client_secret = self.config.get("who_icd_client_secret", "")
        if client_id and client_secret:
            api_client = WHOICDApiClient(client_id, client_secret)

        resolved: Dict[str, Dict[str, Any]] = {}

        if api_client:
            logger.info("  Trying WHO ICD API...")
            for code in icd_codes:
                result = api_client.get_code(code)
                if result:
                    resolved[code] = result

            if resolved:
                logger.info(f"  ✅ Resolved {len(resolved)}/{len(icd_codes)} via WHO API")
                # Fill any missing from static
                missing = icd_codes - set(resolved.keys())
                if missing:
                    static = load_static_mappings()
                    for code in missing:
                        if code in static:
                            resolved[code] = static[code]

        # Fallback to static if API failed or no creds
        if not resolved:
            logger.info("  WHO API unavailable, using static mapping...")
            static = load_static_mappings()
            for code in icd_codes:
                if code in static:
                    resolved[code] = static[code]
            # Also add parent codes not in icd_codes
            parents_to_add = set()
            for code_data in resolved.values():
                parent = code_data.get("parent", "")
                if parent and parent not in resolved:
                    parents_to_add.add(parent)
            for parent in parents_to_add:
                if parent in static:
                    resolved[parent] = static[parent]

        logger.info(f"  Total resolved: {len(resolved)} ICD-10 concepts")
        return resolved

    def _create_concepts(self, codes: Dict[str, Dict[str, Any]]) -> int:
        """MERGE OntologyConcept nodes for ICD-10 codes."""
        logger.info("  Creating ICD-10 OntologyConcept nodes...")
        count = 0
        for code, data in codes.items():
            query = """
                MERGE (o:OntologyConcept {uri: $uri})
                ON CREATE SET
                    o.code = $code,
                    o.label = $label,
                    o.source_ontology = 'ICD-10',
                    o.definition = $definition,
                    o.resolved_via = $resolved_via
                ON MATCH SET
                    o.label = $label,
                    o.definition = $definition
                RETURN o.uri AS uri
            """
            params = {
                "uri": f"icd10:{code}",
                "code": code,
                "label": data.get("label", code),
                "definition": data.get("definition", ""),
                "resolved_via": data.get("resolved_via", "unknown"),
            }
            try:
                self.connector.run_query(query, params)
                count += 1
                logger.debug(f"    MERGE OntologyConcept icd10:{code}")
            except Exception as e:
                logger.error(f"    ❌ Failed to create concept {code}: {e}")
        logger.info(f"  ✅ Created/updated {count} ICD-10 OntologyConcept nodes")
        return count

    def _create_hierarchy(self, codes: Dict[str, Dict[str, Any]]) -> int:
        """Create IS_A edges between ICD-10 concepts."""
        logger.info("  Building ICD-10 IS_A hierarchy...")
        count = 0
        for code, data in codes.items():
            parent = data.get("parent", "")
            if not parent or parent not in codes:
                continue  # Skip if parent not in our set

            query = """
                MATCH (child:OntologyConcept {uri: $child_uri})
                MATCH (parent:OntologyConcept {uri: $parent_uri})
                MERGE (child)-[r:IS_A]->(parent)
                ON CREATE SET r.uri = 'rdfs:subClassOf'
                RETURN type(r) AS t
            """
            try:
                res = self.connector.run_query(query, {
                    "child_uri": f"icd10:{code}",
                    "parent_uri": f"icd10:{parent}",
                })
                if res:
                    count += 1
            except Exception as e:
                logger.error(f"    ❌ IS_A {code} → {parent} failed: {e}")

        logger.info(f"  ✅ Created {count} IS_A edges")
        return count

    def _create_classified_as(self) -> int:
        """Create CLASSIFIED_AS edges from Diagnosis → ICD-10 OntologyConcept."""
        logger.info("  Creating CLASSIFIED_AS edges (Diagnosis → ICD-10)...")
        query = """
            MATCH (d:Diagnosis)
            WHERE d.icd10_code IS NOT NULL
            WITH d, 'icd10:' + d.icd10_code AS uri
            MATCH (o:OntologyConcept {uri: uri})
            MERGE (d)-[r:CLASSIFIED_AS]->(o)
            ON CREATE SET r.uri = 'skos:closeMatch'
            RETURN count(r) AS created
        """
        try:
            res = self.connector.run_query(query)
            count = res[0]["created"] if res else 0
            logger.info(f"  ✅ Created {count:,} CLASSIFIED_AS edges")
            return count
        except Exception as e:
            logger.error(f"  ❌ CLASSIFIED_AS creation failed: {e}")
            return 0


# ══════════════════════════════════════════════════════════════════════
# Pipeline entry point
# ══════════════════════════════════════════════════════════════════════

def execute_icd10_integration(
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    config: Dict[str, Any] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Main execution function for Step 19."""
    # Load WHO ICD creds from .env if not in config
    if config is None:
        config = {}
    if not config.get("who_icd_client_id"):
        try:
            from utils.env_loader import load_config
            full_config = load_config()
            config["who_icd_client_id"] = full_config.get("who_icd_client_id", "")
            config["who_icd_client_secret"] = full_config.get("who_icd_client_secret", "")
        except Exception:
            pass

    connector = Neo4jConnector(neo4j_uri, neo4j_user, neo4j_password)
    try:
        integrator = ICD10Integrator(connector, config)
        return integrator.execute()
    except Exception as e:
        logger.error(f"Step 19 failed: {e}")
        raise
    finally:
        connector.close()


# ══════════════════════════════════════════════════════════════════════
# Standalone execution
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Step 19: ICD-10 Integration")
    parser.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    parser.add_argument("--neo4j-user", default="neo4j")
    parser.add_argument("--neo4j-password", default="your_password")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )

    results = execute_icd10_integration(
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
    )
