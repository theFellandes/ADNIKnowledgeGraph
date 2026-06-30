#!/usr/bin/env python3
"""
build_zenodo_deposit.py  —  assemble a NON-IDENTIFYING Zenodo deposit bundle for MAKO.

What it does (no live database needed, no network):
  * reads the already-generated aggregate metrics in outputs/metrics/*.json
  * extracts the graph SCHEMA (node labels, relationship types, ontology-concept
    inventory) from canonical_snapshot.json
  * copies the curated ontology MAPPING RULES (ontology/mappings/*.csv)
  * writes README.md, data_dictionary.md, LICENSE.txt, CODE.md and .zenodo.json
  * SCANS every file going into the bundle for ADNI participant identifiers
    (PTID pattern \\d{3}_S_\\d{4}, RID) and ABORTS if any are found
  * zips it to outputs/zenodo_deposit_<date>.zip

It deposits ONLY: schema, aggregate statistics, mapping rules, code pointers, docs.
It NEVER deposits participant-level ADNI data (forbidden by the LONI Data Use
Agreement). Your Neo4j graph stays on your machine.

Usage:
    python scripts/build_zenodo_deposit.py                # build into outputs/zenodo_deposit/ + zip
    python scripts/build_zenodo_deposit.py --no-zip       # folder only
    python scripts/build_zenodo_deposit.py --out PATH     # custom output dir
Then: edit .zenodo.json (fill in creators/ORCID/license), upload the .zip to
zenodo.org, get a DOI, and run scripts/run_fuji.py on that DOI.
"""
from __future__ import annotations
import argparse, json, re, shutil, sys, zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
METRICS_DIR = REPO / "outputs" / "metrics"
MAPPINGS_DIR = REPO / "ontology" / "mappings"
GITHUB_URL = "https://github.com/theFellandes/ADNIKnowledgeGraph"

# Aggregate JSONs that are safe to publish (counts / coverage / rules only).
# Explicitly EXCLUDES value_add_queries.json (can contain PTIDs from RETURN p.ptid),
# cross_check*.json and runner_summary.json (internal paths).
STAT_WHITELIST = [
    "canonical_snapshot.json", "semantic_density.json", "semantic_density_per_step.json",
    "tbox_abox.json", "fair_score.json", "fair_external.json",
    "alzkb_alignment.json", "alzkb_alignment_baseline.json", "cross_source_disease.json",
    "per_step_audit.json", "mapping_rules.json", "duplicity_check.json",
    "ablation_study.json", "cost_blind_study.json", "ontology_scorecard.json",
    "source_ontology_contribution.json", "graph_topology.json", "ontology_label_audit.json",
]

# Identifier patterns that must NEVER appear in a deposited file.
PTID_RE = re.compile(r"\b\d{3}_S_\d{4}\b")          # ADNI PTID e.g. 002_S_0413
IDKEY_RE = re.compile(r'"(ptid|rid|subject_id|participant_id)"\s*:', re.I)


def scan_for_identifiers(path: Path) -> list[str]:
    """Return a list of offending snippets if the file looks like it leaks IDs."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:  # pragma: no cover
        return [f"could not read ({e})"]
    hits = []
    for m in PTID_RE.finditer(text):
        hits.append(f"PTID '{m.group(0)}'")
    for m in IDKEY_RE.finditer(text):
        hits.append(f"id-key {m.group(0)}")
    return hits[:5]


def load_snapshot() -> dict:
    p = METRICS_DIR / "canonical_snapshot.json"
    if not p.exists():
        sys.exit(f"ERROR: {p} not found. Run `python -m metrics` (or the runner) first.")
    return json.loads(p.read_text(encoding="utf-8"))


def write_schema(snap: dict, out: Path) -> None:
    sdir = out / "schema"
    sdir.mkdir(parents=True, exist_ok=True)
    (sdir / "node_labels.json").write_text(json.dumps({
        "description": "Node labels in the MAKO knowledge graph and their cardinalities.",
        "distinct_node_labels": snap.get("distinct_node_labels"),
        "node_total": snap.get("node_total"),
        "label_cardinalities": snap.get("node_label_cardinalities", {}),
    }, indent=2), encoding="utf-8")
    (sdir / "relationship_types.json").write_text(json.dumps({
        "description": "Relationship types in the MAKO knowledge graph and their cardinalities.",
        "distinct_relationship_types": snap.get("distinct_relationship_types"),
        "edge_total": snap.get("edge_total"),
        "relationship_cardinalities": snap.get("relationship_cardinalities", {}),
    }, indent=2), encoding="utf-8")
    (sdir / "ontology_concepts.json").write_text(json.dumps({
        "description": "OntologyConcept inventory by source ontology (T-Box).",
        "ontology_concepts_total": snap.get("ontology_concepts_total"),
        "ontology_concepts_by_source": snap.get("ontology_concepts_by_source", {}),
        "alzkb_concepts": snap.get("alzkb_concepts"),
        "same_as_edges": snap.get("same_as_edges"),
    }, indent=2), encoding="utf-8")
    (sdir / "graph_summary.json").write_text(json.dumps({
        "node_total": snap.get("node_total"),
        "edge_total": snap.get("edge_total"),
        "edges_with_uri": snap.get("edges_with_uri"),
        "edge_uri_coverage": snap.get("edge_uri_coverage"),
        "node_ontology_coverage": snap.get("node_ontology_coverage"),
        "maps_to_edges": snap.get("maps_to_edges"),
        "snapshot_timestamp": snap.get("timestamp"),
        "note": "Aggregate schema-level summary. No participant-level data.",
    }, indent=2), encoding="utf-8")


def write_docs(snap: dict, out: Path, included_stats: list[str], included_maps: list[str]) -> None:
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    onto = snap.get("ontology_concepts_by_source", {})
    onto_line = ", ".join(f"{k} {v}" for k, v in onto.items())
    (out / "README.md").write_text(f"""# MAKO — schema, aggregate statistics, and ontology mapping rules

Derived, **non-identifying** artefacts from the *Multimodal Alzheimer's Knowledge graph
with Ontology grounding* (MAKO), built on the ADNI cohort. Bundle generated {built}.

## What is in this deposit
- `schema/` — node labels, relationship types, and the OntologyConcept inventory
  ({snap.get('ontology_concepts_total')} concepts: {onto_line}).
- `statistics/` — pre-computed aggregate metrics (counts, coverage, FAIR, validity,
  AlzKB alignment, per-step audit). Files: {', '.join(included_stats)}.
- `mappings/` — the {len(included_maps)} curated column-to-concept and relation mapping
  rule files (the consolidated index is `index.csv`).
- `data_dictionary.md` — the node labels and their key properties.
- `CODE.md` — pointer to the full pipeline source.

## What is NOT in this deposit
**No participant-level ADNI data.** Under the LONI Image and Data Archive Data Use
Agreement, participant data cannot be redistributed; it is also unnecessary here.
This bundle contains schema, aggregate statistics, and curated rules only. Every file
was scanned for participant identifiers before inclusion.

## Headline figures (from `statistics/canonical_snapshot.json`)
- nodes {snap.get('node_total'):,} · relationships {snap.get('edge_total'):,}
- edge-level URI coverage {snap.get('edge_uri_coverage')} · node ontology coverage {snap.get('node_ontology_coverage')}
- OntologyConcept nodes {snap.get('ontology_concepts_total')} across {len(onto)} source ontologies
- AlzKB cross-graph bridges: {snap.get('alzkb_concepts')} concepts, {snap.get('same_as_edges')} SAME_AS edges

## Source code
Full ETL + enrichment + metrics pipeline: {GITHUB_URL}

## Licence
Schema, statistics, and mapping rules: CC-BY-4.0 (edit `.zenodo.json` / `LICENSE.txt`
if you prefer another). Code is MIT in the repository above.
""", encoding="utf-8")

    labels = snap.get("node_label_cardinalities", {})
    rows = "\n".join(f"| `{lbl}` | {cnt:,} |" for lbl, cnt in sorted(labels.items(), key=lambda x: -x[1]))
    (out / "data_dictionary.md").write_text(f"""# MAKO data dictionary (schema-level)

Node labels and their cardinalities. **No participant values** — counts only.

| Node label | Count |
|---|---|
{rows}

Relationship types and cardinalities are in `schema/relationship_types.json`; the
OntologyConcept inventory is in `schema/ontology_concepts.json`. Each curated mapping
rule (in `mappings/`) carries: source table, source column, value pattern, target
ontology URI, human-readable label, rule kind, and a test-fixture id.
""", encoding="utf-8")

    (out / "CODE.md").write_text(f"""# Code

The complete pipeline (16-step ETL, the in-place semantic migration, the seven
enrichment passes, and the metrics/figures packages that compute every statistic in
`statistics/`) lives at:

  {GITHUB_URL}

For a citable code snapshot, create a GitHub *release* and enable the GitHub-Zenodo
integration (zenodo.org/account/settings/github) — Zenodo mints a separate DOI for the
tagged release, which you can cross-reference from this dataset's metadata
(`related_identifiers`).
""", encoding="utf-8")

    (out / "LICENSE.txt").write_text(
        "This deposit (schema, aggregate statistics, mapping rules, documentation) is\n"
        "released under the Creative Commons Attribution 4.0 International licence\n"
        "(CC-BY-4.0): https://creativecommons.org/licenses/by/4.0/\n\n"
        "It contains NO participant-level ADNI data. ADNI data are governed by the LONI\n"
        "Image and Data Archive Data Use Agreement (https://adni.loni.usc.edu).\n",
        encoding="utf-8")

    desc_html = (
        "<p>Derived, non-identifying artefacts from MAKO (Multimodal Alzheimer's "
        "Knowledge graph with Ontology grounding): the graph <strong>schema</strong> "
        "(node labels, relationship types, OntologyConcept inventory across "
        f"{len(onto)} source ontologies), <strong>aggregate statistics</strong> "
        "(counts, URI/ontology coverage, FAIR scorecard, structural-validity rubric, "
        "cross-vocabulary alignment to AlzKB, per-step audit), and the curated "
        "<strong>column-to-concept mapping rules</strong>.</p>"
        "<p><strong>No participant-level ADNI data is included</strong> (LONI Data Use "
        "Agreement); the underlying graph is not redistributed. Source code: "
        f"<a href=\"{GITHUB_URL}\">{GITHUB_URL}</a>.</p>"
    )
    (out / ".zenodo.json").write_text(json.dumps({
        "title": "MAKO: schema, aggregate statistics, and ontology mapping rules for a "
                 "multimodal Alzheimer's-disease knowledge graph",
        "upload_type": "dataset",
        "description": desc_html,
        "creators": [
            {"name": "REPLACE_ME, Author One", "affiliation": "REPLACE_ME",
             "orcid": "0000-0000-0000-0000"}
        ],
        "keywords": ["knowledge graph", "ontology grounding", "FAIR", "Alzheimer's disease",
                     "ADNI", "HPO", "SNOMED-CT", "UBERON", "LOINC", "Gene Ontology",
                     "AlzKB", "biomedical data integration"],
        "license": "cc-by-4.0",
        "related_identifiers": [
            {"identifier": GITHUB_URL, "relation": "isSupplementTo", "scheme": "url"}
        ],
        "notes": "Contains NO participant-level ADNI data (LONI Data Use Agreement). "
                 "Schema, aggregate statistics, and curated mapping rules only.",
    }, indent=2), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(REPO / "outputs" / "zenodo_deposit"))
    ap.add_argument("--no-zip", action="store_true")
    args = ap.parse_args()

    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    snap = load_snapshot()
    write_schema(snap, out)

    # statistics (whitelist + scan)
    stats_dir = out / "statistics"; stats_dir.mkdir()
    included_stats, leaks = [], []
    for name in STAT_WHITELIST:
        src = METRICS_DIR / name
        if not src.exists():
            continue
        hits = scan_for_identifiers(src)
        if hits:
            leaks.append((src, hits)); continue
        shutil.copy2(src, stats_dir / name); included_stats.append(name)

    # mappings (copy all, scan each)
    maps_dir = out / "mappings"; maps_dir.mkdir()
    included_maps = []
    for src in sorted(MAPPINGS_DIR.glob("*.csv")):
        hits = scan_for_identifiers(src)
        if hits:
            leaks.append((src, hits)); continue
        shutil.copy2(src, maps_dir / src.name); included_maps.append(src.name)

    write_docs(snap, out, included_stats, included_maps)

    # final safety sweep over EVERYTHING in the bundle
    for f in out.rglob("*"):
        if f.is_file():
            hits = scan_for_identifiers(f)
            if hits:
                leaks.append((f, hits))

    if leaks:
        print("ABORT: participant identifiers detected in files slated for deposit:")
        for f, hits in leaks:
            print(f"  - {f}: {', '.join(hits)}")
        print("Nothing was zipped. Remove/aggregate the offending file and re-run.")
        sys.exit(2)

    print(f"Built deposit folder: {out}")
    print(f"  schema/ (4 files)  statistics/ ({len(included_stats)})  mappings/ ({len(included_maps)})")
    print("  README.md  data_dictionary.md  CODE.md  LICENSE.txt  .zenodo.json")

    if not args.no_zip:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        zip_path = REPO / "outputs" / f"zenodo_deposit_{stamp}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(out.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(out))
        print(f"Zipped: {zip_path}  ({zip_path.stat().st_size/1024:.0f} KB)")
    print("\nNext: edit .zenodo.json (creators/ORCID/license), upload the .zip at "
          "zenodo.org/uploads/new, publish to get a DOI, then run scripts/run_fuji.py <DOI>.")


if __name__ == "__main__":
    main()
