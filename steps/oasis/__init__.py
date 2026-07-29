"""OASIS-2 cross-cohort transfer experiment (reviewer #2 / T10).

Self-contained, ISOLATED from the canonical ADNI pipeline. These modules build a
tiny OASIS-2 labeled property graph on a scratch Neo4j instance (bolt 7688) so the
four phases can run on a non-ADNI cohort and emit per-label A-Box coverage.

See: Thesis/Article/tasks/OASIS2_GENERALISABILITY_IMPLEMENTATION_PLAN_2026-06-30.md
"""
