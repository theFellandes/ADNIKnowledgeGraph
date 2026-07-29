"""Ontology label-correctness audit.

Resolvability is not correctness. ``fair_external.py`` checks that an asserted
ontology identifier *dereferences*; it does NOT check that it dereferences to
the *intended concept*. A transposed digit yields a valid-but-wrong code
(e.g. ``MONDO:0024647`` resolves fine -- to *urolithiasis*, not the
"Mild cognitive impairment" the mapping claims). This module closes that gap:
for every OBO-resolvable ``:OntologyConcept`` in the live graph it fetches the
authoritative label from EBI OLS4 and compares it to the label the graph
asserts, flagging mismatches.

Scope: ontologies resolvable via OLS4 (MONDO, DOID, HPO, UBERON, GO, SNOMED-CT).
OLS4 serves SNOMED CT International Edition term-by-term with no API key, so
SNOMED codes are audited here like any other; only the IRI form differs
(``http://snomed.info/id/{SCTID}`` rather than an OBO PURL). Note this checks
identifiers and labels, not content redistribution — no SNOMED term text is
persisted beyond the local resolution cache.

LOINC / ICD-10 have no OLS4 presence and remain ``skipped`` (verify those
against their own authorities separately).

CLI::

    python -m metrics.verify_ontology_labels \
        --uri bolt://localhost:7687 --user neo4j --password your_password
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# source_ontology -> (OLS4 ontology slug, IRI/obo_id prefix)
OBO_MAP = {
    "MONDO": ("mondo", "MONDO"),
    "DOID": ("doid", "DOID"),
    "HPO": ("hp", "HP"),
    "UBERON": ("uberon", "UBERON"),
    "GO": ("go", "GO"),
    "SNOMED-CT": ("snomed", "SNOMED"),
    "SNOMED": ("snomed", "SNOMED"),
}
SKIP = {"LOINC", "ICD-10", "ICD10"}
# Codes whose graph label is an intentional title-case/synonym variant of the OLS4
# canonical (Table-C in PHASE6_LABEL_AUDIT_2026-06-18.md) — never flag these as wrong.
WHITELIST_CODES = {"DOID:1307", "DOID:0080832", "MONDO:0004975", "UBERON:0001897"}

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
    # code like "MONDO:0004975", "HP:0000726", "SNOMED:26929004", or bare "0080832"
    num = code.split(":", 1)[1] if ":" in code else code
    if prefix == "SNOMED":
        # SNOMED has no OBO PURL; its canonical IRI is the snomed.info namespace.
        return f"http://snomed.info/id/{num}"
    return f"http://purl.obolibrary.org/obo/{prefix}_{num}"


def _fetch_label(slug: str, prefix: str, code: str, cache: dict, retries: int = 4,
                 allow_network: bool = True) -> str | None:
    key = f"{slug}:{code}"
    if key in cache:
        return cache[key]
    if not allow_network:
        # cache-only (offline) mode — uncached codes are reported 'unresolved',
        # never networked (so the gate can run net-less without the 4×retry hang).
        return None
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
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None  # definitive: the code is not in this release — don't retry
            time.sleep(4)
            continue
        except Exception:  # transport error (URLError, timeout, bad JSON) — retry
            time.sleep(4)
            continue
        try:
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


def run_audit(rows, allow_network: bool = True, whitelist: set | None = None) -> dict:
    """Audit (ont, code, label) rows against OLS4 canonical labels.

    Reusable by the CLI and by ``metrics.runner``. With ``allow_network=False``
    it runs cache-only (offline) — uncached OBO codes are reported ``unresolved``
    rather than networked, so it can run inside the metrics pipeline without net.
    Returns the report dict; ``report['mismatches']`` is the gate signal.
    """
    whitelist = whitelist or set()
    cache: dict = {}
    if CACHE_PATH.exists():
        cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))

    results, mismatches, skipped, unresolved = [], [], [], []
    for r in rows:
        ont = r["ont"]
        if ont in SKIP or ont not in OBO_MAP:
            skipped.append({"ont": ont, "code": r["code"], "label": r["label"]})
            continue
        slug, prefix = OBO_MAP[ont]
        auth = _fetch_label(slug, prefix, r["code"], cache, allow_network=allow_network)
        if auth is None:
            unresolved.append({"ont": ont, "code": r["code"], "intended": r["label"]})
            status = "unresolved"
        elif _labels_match(r["label"], auth) or r["code"] in whitelist:
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
        "offline": not allow_network,
        "checked": len([r for r in results if r["status"] != "unresolved"]),
        "mismatches": mismatches,
        "unresolved": unresolved,
        "skipped_non_obo": skipped,
        "all": results,
    }
    OUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def _query_rows(uri: str, user: str, password: str) -> list[dict]:
    from neo4j import GraphDatabase  # project dependency

    driver = GraphDatabase.driver(uri, auth=(user, password))
    with driver.session() as s:
        rows = s.run(
            "MATCH (c:OntologyConcept) "
            "WHERE c.code IS NOT NULL AND c.label IS NOT NULL "
            "RETURN c.source_ontology AS ont, c.code AS code, c.label AS label "
            "ORDER BY ont, code"
        ).data()
    driver.close()
    return rows


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m metrics.verify_ontology_labels")
    p.add_argument("--uri", default="bolt://localhost:7687")
    p.add_argument("--user", default="neo4j")
    p.add_argument("--password", default="your_password")
    p.add_argument("--offline", action="store_true",
                   help="cache-only: never call OLS4 (uncached codes → unresolved, not networked)")
    args = p.parse_args(argv)

    rows = _query_rows(args.uri, args.user, args.password)
    report = run_audit(rows, allow_network=not args.offline, whitelist=WHITELIST_CODES)

    print(f"checked={report['checked']} mismatches={len(report['mismatches'])} "
          f"unresolved={len(report['unresolved'])} skipped(non-OBO)={len(report['skipped_non_obo'])}"
          f"{' [offline]' if report['offline'] else ''}")
    for m in report["mismatches"]:
        print(f"  MISMATCH {m['ont']} {m['code']}: graph='{m['intended']}' OLS4='{m['authoritative']}'")
    for u in report["unresolved"]:
        print(f"  unresolved {u['ont']} {u['code']} (intended '{u['intended']}')")
    # Gate behaviour: non-zero exit on any wrong code.
    return 1 if report["mismatches"] else 0


if __name__ == "__main__":
    sys.exit(main())
