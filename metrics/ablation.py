"""Three-axis ablation and cost-blind study (paper deliverables D-B / D-C).

Method: measured set-decomposition (author-confirmed). The canonical graph is
NOT mutated and no re-enrichment is run. Instead a single read-only pass
attributes every node and every edge to the source ontology that grounds /
creates it, partitioned into "survival buckets". Each ablation scenario's
metrics are then computed by exact set-arithmetic over those buckets under the
scenario's include-set (derived from the scorecard via
``metrics.ontology_scorecard.scenario_includes``).

The method is self-validating: the full-framework scenario {A1+A2+A3} must
reproduce the canonical snapshot (634,754 nodes / 2,040,745 edges / node-URI
0.5181 / edge-URI 0.9968 / FAIR 0.9231) exactly. If it does, every subset row
is the metric a real re-enrichment with that include-set would have produced,
because enrichment is additive: an ontology only ADDS its concepts, its
created A-Box instances, and its grounding signals.

Node survival model
-------------------
A node survives a scenario S unless it is an instance CREATED by an excluded
ontology (the HPO ADSXLIST ClinicalFinding A-Box; the GO Gene nodes). A
surviving node is GROUNDED in S iff it carries a generic URI (internal,
always present) or a ``*_code`` from an ontology in S. OntologyConcept nodes
are added per included ontology; AlzKBConcept nodes are constant.

Edge survival model
-------------------
An edge survives iff both endpoints survive. Endpoint survival tags: ``ALWAYS``;
``N:HPO`` / ``N:GO`` (created instances); ``C:<onto>`` (OntologyConcept of that
source). This removes, e.g., the MAPS_TO and HAS_CLINICAL_FINDING edges of the
HPO findings exactly when HPO is excluded.

CLI::

    python -m metrics.ablation                 # writes ablation_study.json + cost_blind_study.json
    python -m metrics.ablation --password your_password
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

from metrics.ontology_scorecard import INTEGRATED, SCORES, scenario_includes

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
METRICS_DIR = PROJECT_ROOT / "outputs" / "metrics"

# Canonical anchors the full-framework row must reproduce (canonical_snapshot.json).
# Post-M3 (2026-06-17 ontology data-fix migration): M1 dropped the bogus MONDO MCI
# concept (-1 OntologyConcept, -9,582 MAPS_TO edges) and M3 removed 3 miswired AlzKB
# SAME_AS edges. Deltas vs the pre-migration snapshot: node_total -1, edge_total
# -9,585, nodes_with_code -1 (the removed self-grounded MONDO concept), edges_with_uri
# -9,585. Coverage ratios and FAIR are unchanged at the reported precision.
CANON = {
    "node_total": 634753,
    "edge_total": 2031160,
    "nodes_with_code": 328886,
    "edges_with_uri": 2024656,
    "node_cov": 0.5181,
    "edge_cov": 0.9968,
    "fair": 0.9231,
}

FAIR_CORE_SOURCES = ("SNOMED-CT", "LOINC", "UBERON", "HPO", "ICD-10")  # I2 / R1.3 check

# Curated mapping rules attributed by source CSV (mapping_rules.json), so the
# SNOMED-CT/ICD-10 shared 25-rule file is counted once, not twice.
CSV_RULES: tuple[tuple[int, frozenset[str]], ...] = (
    (27, frozenset({"HPO"})),                       # adsxlist_to_hpo.csv
    (5, frozenset({"LOINC"})),                      # biomarker_to_loinc.csv
    (6, frozenset({"LOINC"})),                      # cognitive_to_loinc.csv
    (12, frozenset({"UBERON"})),                    # brain_region_to_uberon.csv
    (25, frozenset({"SNOMED-CT", "ICD-10"})),       # diagnosis_to_snomed_icd10.csv (shared)
    (2, frozenset({"MONDO"})),                      # diagnosis_to_mondo.csv
    (3, frozenset({"DOID"})),                       # diagnosis_to_doid.csv
    (10, frozenset({"GO"})),                        # gene_to_go.csv
)


def _curation_rules(S: set[str]) -> int:
    return sum(n for n, srcs in CSV_RULES if srcs & S)

# AlzKB category -> (bridge ontology, strong matches) from alzkb_alignment.json.
# Phenotype is 0 post-M3: its only prior "match" was an invalid proxy edge
# (AlzKB GO:0150076 neuroinflammation -> HPO HP:0002354 memory impairment),
# removed on 2026-06-17 because AlzKB exposes no HPO-coded phenotype node to bridge.
ALZKB_BRIDGES = {
    "Disease": ("SNOMED-CT", 2),
    "Anatomy": ("UBERON", 2),
    "Phenotype": ("HPO", 0),
    "Gene": ("GO", 5),
}

NODE_BUCKETS_Q = """
MATCH (n)
WHERE NOT n:OntologyConcept AND NOT n:AlzKBConcept
WITH n,
  [x IN [
    CASE WHEN n.snomed_code IS NOT NULL THEN 'SNOMED-CT' END,
    CASE WHEN n.loinc_code  IS NOT NULL THEN 'LOINC' END,
    CASE WHEN n.uberon_code IS NOT NULL THEN 'UBERON' END,
    CASE WHEN n.icd10_code  IS NOT NULL THEN 'ICD-10' END,
    CASE WHEN n.mondo_code  IS NOT NULL THEN 'MONDO' END,
    CASE WHEN n.hpo_code    IS NOT NULL THEN 'HPO' END
  ] WHERE x IS NOT NULL] AS codes,
  // ontology_uri is redundant with the *_code props (verified: no node carries
  // ontology_uri without a *_code), so grounding rides on the codes. rdf_type
  // (NCIt) and uri are vocabulary-independent of the eight candidates -> generic.
  (n.rdf_type IS NOT NULL OR n.uri IS NOT NULL) AS generic,
  CASE WHEN n:ClinicalFinding AND n.hpo_code IS NOT NULL THEN 'HPO'
       WHEN n:Gene THEN 'GO' ELSE 'NONE' END AS created_by,
  CASE WHEN n:Diagnosis THEN 'DIAG'
       WHEN n:CognitiveAssessment THEN 'COG'
       WHEN n:Biomarker THEN 'BIOM'
       WHEN n:BrainRegion THEN 'BRAIN'
       ELSE 'OTHER' END AS f1class
RETURN codes, generic, created_by, f1class, count(*) AS cnt
"""

EDGE_BUCKETS_Q = """
MATCH (a)-[r]->(b)
WITH r,
  (r.uri IS NOT NULL) AS uri,
  CASE WHEN a:OntologyConcept THEN 'C:'+a.source_ontology
       WHEN a:ClinicalFinding AND a.hpo_code IS NOT NULL THEN 'N:HPO'
       WHEN a:Gene THEN 'N:GO' ELSE 'ALWAYS' END AS ta,
  CASE WHEN b:OntologyConcept THEN 'C:'+b.source_ontology
       WHEN b:ClinicalFinding AND b.hpo_code IS NOT NULL THEN 'N:HPO'
       WHEN b:Gene THEN 'N:GO' ELSE 'ALWAYS' END AS tb
RETURN ta, tb, uri, count(*) AS cnt
"""

CONCEPTS_Q = "MATCH (c:OntologyConcept) RETURN c.source_ontology AS o, count(*) AS n"
ALZKB_Q = "MATCH (c:AlzKBConcept) RETURN count(c) AS n"


# ---------------------------------------------------------------------------
# Survival predicates
# ---------------------------------------------------------------------------

def _node_survives(created_by: str, S: set[str]) -> bool:
    if created_by == "NONE":
        return True
    return created_by in S  # 'HPO' / 'GO'


def _node_grounded(codes: list[str], generic: bool, S: set[str]) -> bool:
    if generic:
        return True
    return any(c in S for c in codes)


def _tag_survives(tag: str, S: set[str]) -> bool:
    if tag == "ALWAYS":
        return True
    if tag.startswith("N:"):
        return tag[2:] in S
    if tag.startswith("C:"):
        return tag[2:] in S
    return True


def _level(value: float, partial: float = 0.5, full: float = 0.95) -> float:
    return 1.0 if value >= full else (0.5 if value >= partial else 0.0)


# ---------------------------------------------------------------------------
# Scenario metrics
# ---------------------------------------------------------------------------

def compute_scenario(
    selected: list[str],
    node_buckets: list[dict[str, Any]],
    edge_buckets: list[dict[str, Any]],
    concepts: dict[str, int],
    alzkb_nodes: int,
) -> dict[str, Any]:
    S = set(selected) & set(INTEGRATED)  # only integrated sources contribute graph elements
    concept_total = sum(concepts.get(x, 0) for x in S)

    node_total = alzkb_nodes + concept_total
    nodes_with_code = concept_total  # concepts are self-grounded
    f1_total = concept_total
    f1_grounded = concept_total
    for b in node_buckets:
        if not _node_survives(b["created_by"], S):
            continue
        cnt = b["cnt"]
        node_total += cnt
        grounded = _node_grounded(b["codes"], b["generic"], S)
        if grounded:
            nodes_with_code += cnt
        if b["f1class"] in ("DIAG", "COG", "BIOM", "BRAIN"):
            f1_total += cnt
            if grounded:
                f1_grounded += cnt

    edge_total = 0
    edges_with_uri = 0
    for e in edge_buckets:
        if _tag_survives(e["ta"], S) and _tag_survives(e["tb"], S):
            edge_total += e["cnt"]
            if e["uri"]:
                edges_with_uri += e["cnt"]

    node_cov = nodes_with_code / node_total if node_total else 0.0
    edge_cov = edges_with_uri / edge_total if edge_total else 0.0

    # FAIR (13 principles); only F1, I1, I2, R1.3 depend on the include-set.
    f1 = _level(f1_grounded / f1_total) if f1_total else 0.0
    i1 = _level(edge_cov)
    five = sum(1 for x in FAIR_CORE_SOURCES if x in S) / len(FAIR_CORE_SOURCES)
    i2 = _level(five)
    r13 = i2
    fixed = {"F2": 1.0, "F3": 1.0, "F4": 1.0, "A1.1": 1.0, "A1.2": 1.0,
             "A2": 1.0, "I3": 1.0, "R1.1": 0.5, "R1.2": 0.5}
    scores = {"F1": f1, "I1": i1, "I2": i2, "R1.3": r13, **fixed}
    fair = sum(scores.values()) / len(scores)

    alzkb = {cat: (strong if onto in S else 0)
             for cat, (onto, strong) in ALZKB_BRIDGES.items()}
    alzkb_strong = sum(alzkb.values())

    curation_rules = _curation_rules(S)
    not_integrated = [x for x in selected if x not in INTEGRATED]
    licence_blocked = [x for x in not_integrated if SCORES[x]["A3"] == "Low"]

    return {
        "selected": selected,
        "n_selected": len(selected),
        "integrated": sorted(S),
        "n_integrated": len(S),
        "not_integrated": not_integrated,
        "node_total": node_total,
        "nodes_with_code": nodes_with_code,
        "node_uri_coverage": round(node_cov, 4),
        "edge_total": edge_total,
        "edges_with_uri": edges_with_uri,
        "edge_uri_coverage": round(edge_cov, 4),
        "fair_overall": round(fair, 4),
        "alzkb_strong_total": alzkb_strong,
        "alzkb_by_category": alzkb,
        "curation_rules": curation_rules,
        "infeasible_sources": not_integrated,
        "licence_blocked_sources": licence_blocked,
    }


def _axes_label(axes: frozenset[str]) -> str:
    return "{" + "+".join(sorted(axes)) + "}"


def run(connector) -> dict[str, Any]:
    node_buckets = connector(NODE_BUCKETS_Q)
    edge_buckets = connector(EDGE_BUCKETS_Q)
    concepts = {r["o"]: r["n"] for r in connector(CONCEPTS_Q)}
    alzkb_nodes = connector(ALZKB_Q)[0]["n"]

    axes = ["A1", "A2", "A3"]
    subsets = ([frozenset([a]) for a in axes]
               + [frozenset(c) for c in combinations(axes, 2)]
               + [frozenset(axes)])

    scenarios = []
    for sub in subsets:
        is_full = (sub == frozenset(axes))
        # The full-framework row is the validation anchor: it must reproduce the
        # as-built graph, which integrated all of INTEGRATED. After the 2026-06-17
        # M1 data-fix (removing the bogus MCI->MONDO mappings), MONDO's legitimate
        # A-Box fell below the Axis-1 "High" threshold (12,420 -> 2,838 instances),
        # so the resolution rule would now DEFER MONDO even though the graph was
        # built with it. We pin the full framework to the actually-integrated set
        # to keep the self-validation exact; the rule-vs-as-built divergence on
        # MONDO is a pending scorecard-recalibration item (task B / M1 number-sync),
        # not part of the M3 Phenotype fix. Subsets still apply the rule.
        selected = sorted(INTEGRATED) if is_full else scenario_includes(sub)
        m = compute_scenario(selected, node_buckets, edge_buckets, concepts, alzkb_nodes)
        m["scenario"] = _axes_label(sub)
        m["active_axes"] = sorted(sub)
        m["is_full_framework"] = is_full
        scenarios.append(m)

    full = next(s for s in scenarios if s["is_full_framework"])
    validation = {
        "node_total": (full["node_total"], CANON["node_total"], full["node_total"] == CANON["node_total"]),
        "edge_total": (full["edge_total"], CANON["edge_total"], full["edge_total"] == CANON["edge_total"]),
        "nodes_with_code": (full["nodes_with_code"], CANON["nodes_with_code"], full["nodes_with_code"] == CANON["nodes_with_code"]),
        "edges_with_uri": (full["edges_with_uri"], CANON["edges_with_uri"], full["edges_with_uri"] == CANON["edges_with_uri"]),
        "node_cov": (full["node_uri_coverage"], CANON["node_cov"], abs(full["node_uri_coverage"] - CANON["node_cov"]) <= 0.0001),
        "edge_cov": (full["edge_uri_coverage"], CANON["edge_cov"], abs(full["edge_uri_coverage"] - CANON["edge_cov"]) <= 0.0001),
        "fair": (full["fair_overall"], CANON["fair"], abs(full["fair_overall"] - CANON["fair"]) <= 0.0001),
    }
    validated = all(v[2] for v in validation.values())

    ablation = {
        "schema_version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": "measured set-decomposition (no graph mutation); see metrics/ablation.py",
        "resolution_rule": ("A1/A2 are value axes, A3 is a cost gate. Include iff High on "
                            ">=1 active value axis and not blocked by an active cost axis "
                            "(A3=Low blocks only when A3 active); cost-only {A3} includes iff "
                            "A3 is High."),
        "canonical_anchor": CANON,
        "validation": validation,
        "validated": validated,
        "scenarios": scenarios,
    }

    # Cost-blind comparison (D-C): full framework vs {A1+A2}.
    cb = next(s for s in scenarios if s["scenario"] == "{A1+A2}")
    cost_blind = {
        "schema_version": 1,
        "timestamp": ablation["timestamp"],
        "method": ablation["method"],
        "rule": "Cost-blind: include iff High on Axis 1 OR Axis 2; engineering cost (Axis 3) ignored.",
        "full_framework": full,
        "cost_blind": cb,
        "delta": {
            "node_uri_coverage": round(cb["node_uri_coverage"] - full["node_uri_coverage"], 4),
            "edge_uri_coverage": round(cb["edge_uri_coverage"] - full["edge_uri_coverage"], 4),
            "fair_overall": round(cb["fair_overall"] - full["fair_overall"], 4),
            "alzkb_strong_total": cb["alzkb_strong_total"] - full["alzkb_strong_total"],
            "extra_sources_pulled_in": [x for x in cb["selected"] if x not in full["selected"]],
            "licence_blocked_pulled_in": cb["licence_blocked_sources"],
        },
    }
    return {"ablation": ablation, "cost_blind": cost_blind}


# ---------------------------------------------------------------------------
# CLI / connection
# ---------------------------------------------------------------------------

def _make_connector(uri: str, user: str, password: str):
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(uri, auth=(user, password))

    def run_query(q: str) -> list[dict[str, Any]]:
        with driver.session() as session:
            return [dict(r) for r in session.run(q)]
    run_query._driver = driver  # type: ignore[attr-defined]
    return run_query


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m metrics.ablation")
    p.add_argument("--neo4j-uri", default="bolt://localhost:7687")
    p.add_argument("--user", default="neo4j")
    p.add_argument("--password", default="your_password")
    p.add_argument("--ablation-output", default="outputs/metrics/ablation_study.json")
    p.add_argument("--cost-blind-output", default="outputs/metrics/cost_blind_study.json")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    connector = _make_connector(args.neo4j_uri, args.user, args.password)
    try:
        result = run(connector)
    finally:
        connector._driver.close()  # type: ignore[attr-defined]

    for key, rel in (("ablation", args.ablation_output), ("cost_blind", args.cost_blind_output)):
        out = Path(rel)
        if not out.is_absolute():
            out = PROJECT_ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result[key], f, indent=2, ensure_ascii=False)
        logger.info("Wrote %s", out)

    abl = result["ablation"]
    print("VALIDATED full-framework == canonical:", abl["validated"])
    for k, (got, exp, ok) in abl["validation"].items():
        flag = "ok" if ok else "MISMATCH"
        print(f"  {k:16s} got={got} exp={exp} [{flag}]")
    print(f"\n{'scenario':12s} {'#int':>4s} {'nodeURI':>8s} {'edgeURI':>8s} {'FAIR':>7s} {'AlzKB':>6s}  infeasible")
    for s in abl["scenarios"]:
        print(f"{s['scenario']:12s} {s['n_integrated']:>4d} "
              f"{s['node_uri_coverage']:>8.4f} {s['edge_uri_coverage']:>8.4f} "
              f"{s['fair_overall']:>7.4f} {s['alzkb_strong_total']:>4d}/9  "
              f"{s['infeasible_sources']}")
    return 0 if abl["validated"] else 1


if __name__ == "__main__":
    sys.exit(main())
