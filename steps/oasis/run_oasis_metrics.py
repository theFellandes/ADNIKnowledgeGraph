"""Run the metrics suite on the OASIS-2 scratch graph (P3).

Mirrors the ADNI metrics flow, but pointed at the scratch instance (7688) and
writing under outputs/oasis/. Runs the metrics that are meaningful for a non-ADNI
cohort:

    --density            per-label A-Box coverage  (THE deliverable: per_label[])
    --tbox-abox          T-Box vs A-Box weight per source ontology

The offline label gate (--label-correctness) is OPT-IN via --with-label-gate. It is
ADNI-cache-specific: it checks every OntologyConcept the step20 catalogue creates
against ontology/ols4_label_cache.json (offline). On the OASIS graph most of those
T-Box concepts are UNUSED (no phenotype/anatomy-region/gene A-Box) and are simply
absent from the seed cache -> "unresolved", plus one known ADNI label-drift nit
(HP:0000708). That is a cache-coverage artifact, not an OASIS grounding error, and it
also writes to the CANONICAL outputs/metrics/ path, so it is excluded by default.

ADNI-specific metrics (validity 7-assertion gate, AlzKB alignment, FAIR-as-shipped)
are NOT run: they assume ADNI structure / AlzKB SAME_AS that OASIS does not have.

Outputs -> outputs/oasis/metrics/{semantic_density,tbox_abox,...}.json

Usage::

    python -m steps.oasis.run_oasis_metrics
    python -m steps.oasis.run_oasis_metrics --uri bolt://localhost:7688
"""

from __future__ import annotations

import argparse
import sys

from metrics.runner import main as runner_main

DEFAULT_URI = "bolt://localhost:7688"  # scratch — NOT 7687
DEFAULT_USER = "neo4j"
DEFAULT_PASSWORD = "your_password"
DEFAULT_OUTDIR = "outputs/oasis"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m steps.oasis.run_oasis_metrics")
    p.add_argument("--uri", default=DEFAULT_URI)
    p.add_argument("--user", default=DEFAULT_USER)
    p.add_argument("--password", default=DEFAULT_PASSWORD)
    p.add_argument("--output-dir", default=DEFAULT_OUTDIR)
    p.add_argument("--with-label-gate", action="store_true",
                   help="also run the offline label gate (ADNI-cache-specific; writes to outputs/metrics/)")
    p.add_argument("--allow-7687", action="store_true")
    args = p.parse_args(argv)

    if "7687" in args.uri and not args.allow_7687:
        raise SystemExit(f"REFUSING to run against {args.uri} (canonical ADNI graph). Use 7688.")

    runner_argv = ["--density", "--tbox-abox"]
    if args.with_label_gate:
        runner_argv.append("--label-correctness")
    runner_argv += [
        "--neo4j-uri", args.uri,
        "--user", args.user,
        "--password", args.password,
        "--output-dir", args.output_dir,
    ]
    return runner_main(runner_argv)


if __name__ == "__main__":
    sys.exit(main())
