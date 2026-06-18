"""Ontology label-correctness audit.

Resolvability is not correctness. ``fair_external.py`` checks that an asserted
ontology identifier *dereferences*; it does NOT check that it dereferences to
the *intended concept*. A transposed digit yields a valid-but-wrong code
(e.g. ``MONDO:0024647`` resolves fine -- to *urolithiasis*, not the
"Mild cognitive impairment" the mapping claims). This module closes that gap:
for every OBO-resolvable ``:OntologyConcept`` in the live graph it fetches the
authoritative label from EBI OLS4 and compares it to the label the graph
asserts, flagging mismatches.

Scope: OBO ontologies resolvable via OLS4 (MONDO, DOID, HPO, UBERON, GO).
SNOMED-CT / LOINC / ICD-10 are licence- or service-gated and are listed as
``skipped`` (verify those against their own authorities separately).

CLI::

    python -m metrics.verify_ontology_labels \
        --uri bolt://localhost:7687 --user neo4j --password your_password
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# source_ontology -> (OLS4 ontology slug, OBO IRI prefix)
OBO_MAP = {
    "MONDO": ("mondo", "MONDO"),
    "DOID": ("doid", "DOID"),
    "HPO": ("hp", "HP"),
    "UBERON": ("uberon", "UBERON"),
    "GO": ("go", "GO"),
}
SKIP = {"SNOMED-CT", "LOINC", "ICD-10", "ICD10"}

CACHE_PATH = Path(__file__).resolve().parents[1] / "ontology" / "ols4_label_cache.json"
OUT_PATH = Path(__file__).resolve().parents[1] / "outputs" / "metrics" / "ontology_label_audit.json"


def _norm(s: str) -> str:
    s = (s or "").lower().replace("'", "").replace("’", "")
    for ch in "-/,()":
        s = s.replace(ch, " ")
    return " ".join(s.split())


def _labels_match(intended: str, authoritative: str) -> bool:
    a, b = _norm(intended), _norm(authoritative)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    ta, tb = set(a.split()), set(b.split())
    inter = ta & tb
    return len(inter) / max(1, min(len(ta), len(tb))) >= 0.5


def _obo_iri(prefix: str, code: str) -> str:
    # code like "MONDO:0004975", "HP:0000726", or bare "0080832"
    num = code.split(":", 1)[1] if ":" in code else code
    return f"http://purl.obolibrary.org/obo/{prefix}_{num}"


def _fetch_label(slug: str, prefix: str, code: str, cache: dict, retries: int = 4) -> str | None:
    key = f"{slug}:{code}"
    if key in cache:
        return cache[key]
    iri = _obo_iri(prefix, code)
    url = (
        f"https://www.ebi.ac.uk/ols4/api/ontologies/{slug}/terms?iri="
        + urllib.parse.quote(iri, safe="")
    )
    obo_id_want = f"{prefix}:{code.split(':',1)[1] if ':' in code else code}"
    for _ in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=45) as resp:
                data = json.load(resp)
            terms = data.get("_embedded", {}).get("terms", [])
            label = None
            for t in terms:  # pick the term whose obo_id matches (guard against cross-imports)
                if (t.get("obo_id") or "").upper() == obo_id_want.upper():
                    label = t.get("label")
                    break
            if label is None and terms:
                label = terms[0].get("label")
            cache[key] = label
            return label
        except Exception:
            time.sleep(4)
    return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m metrics.verify_ontology_labels")
    p.add_argument("--uri", default="bolt://localhost:7687")
    p.add_argument("--user", default="neo4j")
    p.add_argument("--password", default="your_password")
    args = p.parse_args(argv)

    from neo4j import GraphDatabase  # project dependency

    driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
    with driver.session() as s:
        rows = s.run(
            "MATCH (c:OntologyConcept) "
            "WHERE c.code IS NOT NULL AND c.label IS NOT NULL "
            "RETURN c.source_ontology AS ont, c.code AS code, c.label AS label "
            "ORDER BY ont, code"
        ).data()
    driver.close()

    cache = {}
    if CACHE_PATH.exists():
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))

    results = []
    mismatches = []
    skipped = []
    unresolved = []
    for r in rows:
        ont = r["ont"]
        if ont in SKIP or ont not in OBO_MAP:
            skipped.append({"ont": ont, "code": r["code"], "label": r["label"]})
            continue
        slug, prefix = OBO_MAP[ont]
        auth = _fetch_label(slug, prefix, r["code"], cache)
        if auth is None:
            unresolved.append({"ont": ont, "code": r["code"], "intended": r["label"]})
            status = "unresolved"
        elif _labels_match(r["label"], auth):
            status = "match"
        else:
            status = "MISMATCH"
            mismatches.append(
                {"ont": ont, "code": r["code"], "intended": r["label"], "authoritative": auth}
            )
        results.append(
            {"ont": ont, "code": r["code"], "intended": r["label"],
             "authoritative": auth, "status": status}
        )

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "checked": len([r for r in results if r["status"] != "unresolved"]),
        "mismatches": mismatches,
        "unresolved": unresolved,
        "skipped_non_obo": skipped,
        "all": results,
    }
    OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"checked={report['checked']} mismatches={len(mismatches)} "
          f"unresolved={len(unresolved)} skipped(non-OBO)={len(skipped)}")
    for m in mismatches:
        print(f"  MISMATCH {m['ont']} {m['code']}: graph='{m['intended']}' OLS4='{m['authoritative']}'")
    for u in unresolved:
        print(f"  unresolved {u['ont']} {u['code']} (intended '{u['intended']}')")
    return 0


if __name__ == "__main__":
    sys.exit(main())
