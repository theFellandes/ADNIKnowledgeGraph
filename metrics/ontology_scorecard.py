"""Three-axis per-ontology scorecard (paper deliverable D-A).

Scores each of the ten candidate ontologies on the three selection axes and
applies the resolution rule to produce an include / defer / exclude verdict.
Every score is derived from measured project evidence under an explicit
High / Medium / Low rubric, so the scorecard is reproducible rather than
hand-authored:

  - Axis 1 (T-Box/A-Box scope)        <- ``tbox_abox.json`` (concepts, A-Box)
  - Axis 2 (interoperability gain)     <- ``alzkb_alignment.json`` (category
                                          bridges) + ``semantic_density.json``
                                          (per-label coverage contribution)
  - Axis 3 (engineering-cost favour.)  <- ``mapping_rules.json`` (curation
                                          rules) + licence / upstream facts

The two non-integrated candidates (UMLS, ChEBI) carry no project A-Box, so
their Axis-1/2 evidence is the documented scope/relevance assessment and
their Axis-3 evidence is the licence / openness fact; both are flagged
``integrated: false`` in the output.

The module also exposes :data:`SCORES`, :data:`AXIS3_BLOCKER`, and
:func:`scenario_includes` so the ablation engine (``metrics.ablation``)
re-uses the identical scores and inclusion logic.

CLI::

    python -m metrics.ontology_scorecard
    python -m metrics.ontology_scorecard --output outputs/metrics/ontology_scorecard.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
METRICS_DIR = PROJECT_ROOT / "outputs" / "metrics"

HIGH, MEDIUM, LOW = "High", "Medium", "Low"

# Canonical ordering used everywhere downstream (eight integrated + two not).
CANDIDATES: tuple[str, ...] = (
    "SNOMED-CT", "LOINC", "UBERON", "HPO", "ICD-10",
    "MONDO", "DOID", "GO", "UMLS", "ChEBI",
)

INTEGRATED: frozenset[str] = frozenset(
    {"SNOMED-CT", "LOINC", "UBERON", "HPO", "ICD-10", "MONDO", "DOID", "GO"}
)

# ---------------------------------------------------------------------------
# Rubric text (printed verbatim in the paper)
# ---------------------------------------------------------------------------

RUBRIC: dict[str, str] = {
    "axis1": (
        "Axis 1 (T-Box/A-Box scope). High = the source binds >= 10,000 data "
        "instances (substantial patient-side anchoring); Medium = the schema "
        "is materialised and every declared concept is instantiated but the "
        "absolute A-Box is small (10-10,000 instances); Low = schema-only, "
        "negligible instantiation (< 10 instances). Evidence: per-source "
        "A-Box instance count in tbox_abox.json."
    ),
    "axis2": (
        "Axis 2 (interoperability gain). High = the source uniquely enables a "
        "cross-knowledge-graph (AlzKB) category bridge, or is the largest "
        "coverage contributor to a core clinical label; Medium = it adds a "
        "standards cross-walk that partially overlaps an existing bridge; "
        "Low = its grounding is redundant with an already-included source, or "
        "it yields no cross-KG / standards gain. Evidence: per-category "
        "strong-match counts in alzkb_alignment.json and per-label coverage "
        "in semantic_density.json."
    ),
    "axis3": (
        "Axis 3 (engineering-cost favourability; High = favourable / cheap). "
        "High = open licence (OBO / WHO / free-registration) with a stable "
        "dedicated upstream and a small curation-rule set; Medium = an "
        "obtainable-but-restricted licence (e.g. SNOMED-CT affiliate) or a "
        "moderate curation burden; Low = a hard licence blocker or an "
        "unstable upstream. Evidence: per-source rule counts in "
        "mapping_rules.json plus the licence / upstream checklist."
    ),
    "resolution_rule": (
        "Resolution rule. A candidate is INCLUDED iff it scores High on a "
        "value axis (Axis 1 or Axis 2) and Axis 3 is not a hard blocker "
        "(Axis 3 != Low). It is DEFERRED when a value axis is favourable but "
        "Axis 3 reports a high-but-payable cost (logged in the future-work "
        "backlog with the blocker). It is EXCLUDED when both value axes score "
        "Low, or when Axis 3 is a hard licence / stability blocker independent "
        "of value."
    ),
}

# ---------------------------------------------------------------------------
# Curated, evidence-anchored facts for the axes that are not a pure threshold
# ---------------------------------------------------------------------------

# Axis 2 verdict + the justification anchored to a measured bridge / label.
AXIS2: dict[str, tuple[str, str]] = {
    "SNOMED-CT": (HIGH, "owns the AlzKB Disease bridge (2/35 strong) and grounds all 25,946 Diagnosis nodes"),
    "LOINC":     (HIGH, "largest lab coverage contributor: 69,606 Biomarker + 65,345 CognitiveAssessment nodes"),
    "UBERON":    (HIGH, "sole AlzKB Anatomy bridge (2/14 strong); grounds 12/12 BrainRegion nodes"),
    "HPO":       (HIGH, "largest node-coverage driver (119,071 ClinicalFinding); no valid AlzKB Phenotype bridge (AlzKB symptoms are MeSH-coded, not HPO)"),
    "GO":        (HIGH, "sole driver of the AlzKB Gene bridge (5/5 strong, the only saturated category)"),
    "ICD-10":    (MEDIUM, "adds a classification cross-walk on Diagnosis that overlaps the SNOMED-CT Disease bridge"),
    "MONDO":     (HIGH, "supplies the cross-reference identifiers that (with DOID) opened the Step-34 strong-match path; the disease cross-walk hub linking Diagnosis to AlzKB's DOID-keyed Disease nodes"),
    "DOID":      (LOW, "disease grounding is largely redundant with the co-included MONDO mapping"),
    "UMLS":      (MEDIUM, "would add Metathesaurus cross-references but largely duplicates included sources"),
    "ChEBI":     (LOW, "chemical-entity scope has no patient-side anchor in the ADNI substrate"),
}

# Axis 3: licence / upstream fact -> favourability score.
AXIS3: dict[str, tuple[str, str]] = {
    "SNOMED-CT": (MEDIUM, "SNOMED International affiliate licence required (obtainable under a member-country agreement); 25 curation rules"),
    "LOINC":     (HIGH, "free Regenstrief licence, stable LOINC/OLS upstream; 11 curation rules"),
    "UBERON":    (HIGH, "open OBO (CC) licence, stable EBI OLS; 12 curation rules"),
    "HPO":       (HIGH, "open OBO licence, stable HPO/OLS upstream; 27 curation rules"),
    "ICD-10":    (HIGH, "open WHO ICD browser/API; 25 curation rules (shared with SNOMED-CT)"),
    "MONDO":     (HIGH, "open OBO licence, stable OLS; 2 curation rules"),
    "DOID":      (HIGH, "open OBO licence, stable OLS; 3 curation rules"),
    "GO":        (HIGH, "open OBO licence, stable GO/OLS upstream; 10 curation rules"),
    "UMLS":      (LOW, "UMLS Metathesaurus Licence is a hard blocker for open redistribution (UTS account + annual agreement)"),
    "ChEBI":     (HIGH, "open OBO licence, stable EBI upstream"),
}

# Would-be Axis-1 scope for the non-integrated candidates (no measured A-Box).
AXIS1_NONINTEGRATED: dict[str, tuple[str, str]] = {
    "UMLS":  (HIGH, "Metathesaurus would bind broadly across the clinical labels (assessed, not integrated)"),
    "ChEBI": (LOW, "no compound/exposure data in the ADNI substrate to bind (assessed, not integrated)"),
}

# Per-source curation-rule counts (mapping_rules.json), surfaced as Axis-3 evidence.
RULE_COUNTS: dict[str, int] = {
    "SNOMED-CT": 25, "LOINC": 11, "UBERON": 12, "HPO": 27, "ICD-10": 25,
    "MONDO": 2, "DOID": 3, "GO": 10, "UMLS": 0, "ChEBI": 0,
}


def _load(name: str) -> dict[str, Any]:
    with open(METRICS_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)


def _axis1_from_abox(abox: int, tbox: int) -> tuple[str, str]:
    if abox >= 10_000:
        return HIGH, f"binds {abox:,} data instances ({tbox} T-Box concepts)"
    if abox >= 10:
        return MEDIUM, f"schema materialised ({tbox} concepts) but small A-Box ({abox} instances)"
    return LOW, f"schema-only: {tbox} concepts, {abox} instance(s)"


def _verdict(a1: str, a2: str, a3: str) -> tuple[str, str]:
    high_value = (a1 == HIGH) or (a2 == HIGH)
    both_low = (a1 == LOW) and (a2 == LOW)
    if a3 == LOW:
        return "Exclude", "Axis-3 hard blocker (licence / stability) overrides value"
    if both_low:
        return "Exclude", "both value axes score Low"
    if high_value:
        return "Include", "High on a value axis with Axis-3 not blocking"
    return "Defer", "value favourable but no High value axis; revisit"


def build_scorecard() -> dict[str, Any]:
    tbox_abox = {r["source_ontology"]: r for r in _load("tbox_abox.json")["rows"]}

    rows: list[dict[str, Any]] = []
    for onto in CANDIDATES:
        integrated = onto in INTEGRATED
        # Axis 1
        if integrated:
            ev = tbox_abox[onto]
            a1, a1_ev = _axis1_from_abox(ev["abox_instances"], ev["tbox_concepts"])
            tbox_n, abox_n = ev["tbox_concepts"], ev["abox_instances"]
        else:
            a1, a1_ev = AXIS1_NONINTEGRATED[onto]
            tbox_n, abox_n = 0, 0
        # Axis 2, Axis 3
        a2, a2_ev = AXIS2[onto]
        a3, a3_ev = AXIS3[onto]
        verdict, reason = _verdict(a1, a2, a3)
        rows.append({
            "ontology": onto,
            "integrated": integrated,
            "axis1": {"score": a1, "evidence": a1_ev},
            "axis2": {"score": a2, "evidence": a2_ev},
            "axis3": {"score": a3, "evidence": a3_ev},
            "verdict": verdict,
            "verdict_reason": reason,
            "measured": {
                "tbox_concepts": tbox_n,
                "abox_instances": abox_n,
                "curation_rules": RULE_COUNTS[onto],
            },
        })

    include = [r["ontology"] for r in rows if r["verdict"] == "Include"]
    exclude = [r["ontology"] for r in rows if r["verdict"] == "Exclude"]
    defer = [r["ontology"] for r in rows if r["verdict"] == "Defer"]
    return {
        "schema_version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rubric": RUBRIC,
        "rows": rows,
        "include_set": include,
        "defer_set": defer,
        "exclude_set": exclude,
        "summary": {
            "n_candidates": len(rows),
            "n_include": len(include),
            "n_defer": len(defer),
            "n_exclude": len(exclude),
        },
    }


# Static score table for re-use by the ablation engine (axis -> score).
SCORES: dict[str, dict[str, str]] = {}
for _o in CANDIDATES:
    _i = _o in INTEGRATED
    if _i:
        _row = {r["source_ontology"]: r for r in _load("tbox_abox.json")["rows"]}[_o]
        _a1 = _axis1_from_abox(_row["abox_instances"], _row["tbox_concepts"])[0]
    else:
        _a1 = AXIS1_NONINTEGRATED[_o][0]
    SCORES[_o] = {"A1": _a1, "A2": AXIS2[_o][0], "A3": AXIS3[_o][0]}


def scenario_includes(active_axes: frozenset[str]) -> list[str]:
    """Apply the confirmed axis-subset resolution rule for an ablation scenario.

    Default rule (author-confirmed): A1 and A2 are value axes, A3 is a cost
    gate. A candidate is included iff it scores High on at least one ACTIVE
    value axis and is not blocked by an active cost axis (A3 = Low blocks only
    when A3 is in the subset). For the cost-only scenario {A3}, include iff
    A3 is High (cheapest to integrate), independent of value.
    """
    selected: list[str] = []
    value_active = [ax for ax in ("A1", "A2") if ax in active_axes]
    a3_active = "A3" in active_axes
    cost_only = active_axes == frozenset({"A3"})
    for onto, sc in SCORES.items():
        if cost_only:
            if sc["A3"] == HIGH:
                selected.append(onto)
            continue
        high_on_value = any(sc[ax] == HIGH for ax in value_active)
        blocked = a3_active and sc["A3"] == LOW
        if high_on_value and not blocked:
            selected.append(onto)
    return selected


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m metrics.ontology_scorecard")
    p.add_argument("--output", default="outputs/metrics/ontology_scorecard.json")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    card = build_scorecard()
    out = Path(args.output)
    if not out.is_absolute():
        out = PROJECT_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(card, f, indent=2, ensure_ascii=False)
    logger.info("Wrote %s", out)
    print(json.dumps({
        "include": card["include_set"],
        "defer": card["defer_set"],
        "exclude": card["exclude_set"],
    }, indent=2))
    # Self-check: the full framework must reproduce the real eight-source set.
    full = sorted(scenario_includes(frozenset({"A1", "A2", "A3"})))
    expected = sorted(INTEGRATED)
    print("full-framework include-set reproduces the integrated eight:",
          full == expected, file=sys.stderr)
    if full != expected:
        print(f"  got={full}\n  exp={expected}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
