"""External FAIR cross-check for the MAKO knowledge graph.

The paper's FAIR score (metrics/fair_score.py -> outputs/metrics/fair_score.json)
is a *self-assessment* against a project-defined rubric. A reviewer will,
rightly, discount a graph that "passes its own test." This script provides an
INDEPENDENT signal that does not reuse that rubric at all: it takes the actual
ontology identifiers the graph asserts (from ontology/mappings/*.csv) and asks
public authorities whether each identifier really resolves to a live ontology
term.

That directly exercises the FAIR principles a bespoke rubric cannot self-certify:
  F1  identifiers are globally unique and resolvable
  A1  identifiers are retrievable over an open protocol
  I1/I2  values use a formal, accessible, shared (FAIR) vocabulary

Resolvers (all public, no API key):
  HPO/UBERON/GO/MONDO/DOID -> EBI OLS4 term API (ontology of record)
  SNOMED-CT                -> SNOMED International public Snowstorm browser
  LOINC                    -> loinc.org term page
  ICD-10(-CM)              -> NLM Clinical Tables search service

Output: outputs/metrics/fair_external.json + a console summary.
Run:    python metrics/fair_external.py
"""
from __future__ import annotations
import csv
import glob
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP_DIR = os.path.join(ROOT, "ontology", "mappings")
OUT = os.path.join(ROOT, "outputs", "metrics", "fair_external.json")

# Ontologies the paper claims as the eight included sources. Others in the
# CSVs (NCIt, NCBI, Biolink, RO) are scaffolding / not claimed as sources.
CLAIMED = {"HPO", "UBERON", "GO", "MONDO", "DOID", "SNOMED-CT", "LOINC", "ICD-10"}
OBO_OLS = {"HPO": "hp", "UBERON": "uberon", "GO": "go", "MONDO": "mondo", "DOID": "doid"}
PER_ONT_CAP = 100          # cap requests per ontology to bound runtime
TIMEOUT = 15
UA = {"User-Agent": "MAKO-FAIR-external-check/1.0 (thesis reproducibility audit)"}


def _get(url, accept="application/json"):
    """GET -> (http_status:int, body:str|None). Never raises."""
    req = urllib.request.Request(url, headers={**UA, "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read(200_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:                       # noqa: BLE001
        return -1, f"{type(e).__name__}: {e}"[:120]


def norm_id(ontology: str, uri: str):
    """Pull the bare local id out of a CURIE-ish target_uri cell."""
    u = uri.strip()
    pats = {
        "HPO": r"HP[:_](\d{7})", "UBERON": r"UBERON[:_](\d{7})",
        "GO": r"GO[:_](\d{7})", "MONDO": r"MONDO[:_](\d{7})",
        "DOID": r"DOID[:_](\d+)",
    }
    if ontology in pats:
        m = re.search(pats[ontology], u, re.I)
        return m.group(1) if m else None
    if ontology == "SNOMED-CT":
        m = re.search(r"(\d{6,})", u)
        return m.group(1) if m else None
    if ontology == "LOINC":
        m = re.search(r"(\d+-\d)", u)
        return m.group(1) if m else None
    if ontology == "ICD-10":
        tail = u.split(":")[-1].strip().upper()      # CURIE form icd10:G30.9
        return tail if re.match(r"[A-Z]\d{2}(?:\.\d+)?$", tail) else None
    return None


def resolve(ontology: str, local: str):
    """Return (status_label, detail, resolvable_bool) from a public authority."""
    if ontology in OBO_OLS:
        ont = OBO_OLS[ontology]
        prefix = {"HPO": "HP", "UBERON": "UBERON", "GO": "GO",
                  "MONDO": "MONDO", "DOID": "DOID"}[ontology]
        obo = f"{prefix}:{local}"
        url = (f"https://www.ebi.ac.uk/ols4/api/ontologies/{ont}/terms"
               f"?obo_id={urllib.parse.quote(obo)}")
        st, body = _get(url)
        if st == 200 and body:
            try:
                j = json.loads(body)
                terms = j.get("_embedded", {}).get("terms", [])
                if not terms:
                    return "not_found", f"OLS4 0 hits for {obo}", False
                purl = f"http://purl.obolibrary.org/obo/{prefix}_{local}"
                cand = [t for t in terms if t.get("iri") == purl] or terms
                cand = [t for t in cand if t.get("is_defining_ontology")] or cand
                t0 = cand[0]
                obs = bool(t0.get("is_obsolete"))
                return ("obsolete" if obs else "resolves",
                        f"OLS4 {obo} ({t0.get('label')})"
                        + (" (OBSOLETE)" if obs else ""), not obs)
            except Exception:                    # noqa: BLE001
                return "error", "OLS4 parse error", False
        if st == 404:
            return "not_found", f"OLS4 404 for {obo}", False
        return "error", f"OLS4 HTTP {st}", False

    if ontology == "SNOMED-CT":
        url = ("https://browser.ihtsdotools.org/snowstorm/snomed-ct/browser/"
               f"MAIN/concepts/{local}")
        st, body = _get(url)
        if st == 200 and body and '"conceptId"' in body:
            active = '"active":true' in body.replace(" ", "")
            return ("resolves" if active else "inactive",
                    f"Snowstorm {local}" + ("" if active else " (inactive)"), active)
        if st == -1:
            return "error", f"SNOMED {local}: {body}", False
        # 401/403/404/405/406 etc.: no open key-free resolution path for SNOMED.
        return "licence_gated", (f"SNOMED {local}: no open key-free API "
                                 f"(HTTP {st}); affiliate licence required"), False

    if ontology == "LOINC":
        url = f"https://loinc.org/{local}/"
        st, _ = _get(url, accept="text/html")
        if st == 200:
            return "resolves", f"loinc.org/{local}", True
        if st == 404:
            return "not_found", f"loinc.org 404 for {local}", False
        return "error", f"loinc.org HTTP {st}", False

    if ontology == "ICD-10":
        url = ("https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search"
               f"?sf=code&terms={urllib.parse.quote(local)}&maxList=5")
        st, body = _get(url)
        if st == 200 and body:
            try:
                arr = json.loads(body)
                codes = [c[0].upper() for c in (arr[3] or [])]
                if local.upper() in codes:
                    return "resolves", f"NLM ICD-10-CM {local}", True
                if any(c.startswith(local.upper()) for c in codes):
                    return "resolves", (f"{local} WHO category, CM leaves "
                                        f"{codes[:3]}"), True
                return "not_found", f"NLM ICD-10-CM: {local} not in {codes}", False
            except Exception:                    # noqa: BLE001
                return "error", "NLM parse error", False
        return "error", f"NLM HTTP {st}", False

    return "unsupported", ontology, False


def collect():
    """{ontology: [(local_id, source_uri, csv), ...]} deduped, capped."""
    found: dict[str, dict] = {}
    for path in sorted(glob.glob(os.path.join(MAP_DIR, "*.csv"))):
        name = os.path.basename(path)
        try:
            with open(path, newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    ont = (row.get("target_ontology") or "").strip()
                    uri = (row.get("target_uri") or "").strip()
                    if ont not in CLAIMED or not uri:
                        continue
                    local = norm_id(ont, uri)
                    if not local:
                        continue
                    found.setdefault(ont, {})
                    found[ont].setdefault(local, (uri, name))
        except Exception as e:                   # noqa: BLE001
            print(f"  (skip {name}: {e})")
    return {o: [(k, v[0], v[1]) for k, v in d.items()] for o, d in found.items()}


def main():
    pool = collect()
    results, summary = {}, {}
    print("External URI-resolvability check (independent of fair_score.py)\n")
    for ont in sorted(pool):
        items = pool[ont][:PER_ONT_CAP]
        rows, ok = [], 0
        for local, uri, src in items:
            label, detail, good = resolve(ont, local)
            ok += int(good)
            rows.append({"id": local, "source_uri": uri, "csv": src,
                         "status": label, "detail": detail, "resolvable": good})
            time.sleep(0.05)
        n = len(items)
        rate = round(ok / n, 4) if n else None
        total = len(pool[ont])
        summary[ont] = {"tested": n, "of_distinct": total, "resolvable": ok,
                        "resolvable_rate": rate}
        results[ont] = rows
        bar = f"{ok}/{n}"
        print(f"  {ont:<10} {bar:>6}  ({rate if rate is not None else 'n/a'})"
              f"   [{total} distinct ids in mappings]")

    tested = sum(s["tested"] for s in summary.values())
    good = sum(s["resolvable"] for s in summary.values())
    obo_tested = sum(summary[o]["tested"] for o in OBO_OLS if o in summary)
    obo_ok = sum(summary[o]["resolvable"] for o in OBO_OLS if o in summary)
    # SNOMED-CT has no open key-free API (affiliate licence), so a resolvability
    # rate over open authorities excludes it -- its absence IS the Axis-3 signal.
    open_o = [o for o in summary if o != "SNOMED-CT"]
    open_tested = sum(summary[o]["tested"] for o in open_o)
    open_ok = sum(summary[o]["resolvable"] for o in open_o)
    payload = {
        "schema_version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "purpose": ("Independent external resolvability check of the ontology "
                    "identifiers the graph asserts; complements (does not reuse) "
                    "outputs/metrics/fair_score.json."),
        "resolvers": {
            "HPO/UBERON/GO/MONDO/DOID": "EBI OLS4 term API (obo_id lookup)",
            "SNOMED-CT": "SNOMED International public Snowstorm browser",
            "LOINC": "loinc.org term page (HTTP 200)",
            "ICD-10": "NLM Clinical Tables ICD-10-CM search service",
        },
        "fair_principles_exercised": ["F1", "A1", "I1", "I2"],
        "per_ontology_summary": summary,
        "overall": {
            "ids_tested": tested, "ids_resolvable": good,
            "resolvable_rate": round(good / tested, 4) if tested else None,
            "obo_resolvable_rate": round(obo_ok / obo_tested, 4) if obo_tested else None,
            "open_authority_resolvable_rate": (round(open_ok / open_tested, 4)
                                               if open_tested else None),
            "snomed_note": ("SNOMED-CT excluded from the open-authority rate: it "
                            "exposes no open key-free resolution API (affiliate "
                            "licence). That gap is itself the evidence for its "
                            "Axis-3 = Medium score in Table III."),
        },
        "results": results,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    print(f"\n  OPEN authorities (excl. SNOMED): {open_ok}/{open_tested} "
          f"({payload['overall']['open_authority_resolvable_rate']})")
    print(f"  OBO via OLS4: {obo_ok}/{obo_tested} "
          f"({payload['overall']['obo_resolvable_rate']})")
    print(f"  ALL incl. SNOMED: {good}/{tested} "
          f"({payload['overall']['resolvable_rate']})")
    print(f"\n  written -> {os.path.relpath(OUT, ROOT)}")
    # surface any non-resolving ids explicitly -- these are real findings
    bad = [(o, r["id"], r["status"], r["detail"])
           for o, rs in results.items() for r in rs if not r["resolvable"]]
    if bad:
        print(f"\n  {len(bad)} identifier(s) did NOT cleanly resolve:")
        for o, i, s, d in bad:
            print(f"    {o:<10} {i:<12} {s:<12} {d}")


if __name__ == "__main__":
    main()
