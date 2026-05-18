"""
Phase 1.5 — Step 7b Idempotency Test
=====================================
Tests hash-based change detection with a live Neo4j instance.

Prerequisites:
  - Neo4j running at bolt://localhost:7687
  - credentials in .env (NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)

Usage:
    python tests/test_idempotency.py

The module-level ``pytestmark`` below skips the file during ``pytest``
runs when ``NEO4J_PASSWORD`` is not set. Hash-determinism tests that do
not need a live DB are still skipped to keep this file self-consistent;
to exercise them, run the file directly via the ``__main__`` block at
the bottom or set ``NEO4J_PASSWORD`` for pytest collection.
"""
import sys
import os

import pytest

# Project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from steps.step7_batch_insert import compute_row_hash, BatchInserter
from utils.neo4j_connector import Neo4jConnector
from dotenv import load_dotenv

load_dotenv()

URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PWD = os.getenv("NEO4J_PASSWORD", "")


pytestmark = pytest.mark.skipif(
    not PWD,
    reason="live-Neo4j idempotency test; set NEO4J_PASSWORD to enable",
)


class FakeDiagnosis:
    """Minimal stand-in for the Diagnosis entity."""
    def __init__(self, diagnosis_id, description, patient_id=None, visit_id=None):
        self.diagnosis_id = diagnosis_id
        self.description = description
        self.patient_id = patient_id
        self.visit_id = visit_id

    def to_dict(self):
        return {k: v for k, v in self.__dict__.items() if v is not None}


def test_hash_determinism():
    """Verify that the hash function is deterministic."""
    row1 = {"diagnosis_id": "D001", "description": "Alzheimer Disease", "severity": 3}
    row2 = {"severity": 3, "diagnosis_id": "D001", "description": "Alzheimer Disease"}  # diff order
    assert compute_row_hash(row1) == compute_row_hash(row2), "Hash must be key-order independent"

    row3 = {"diagnosis_id": "D001", "description": "Alzheimer Disease", "severity": 4}
    assert compute_row_hash(row1) != compute_row_hash(row3), "Different data → different hash"
    print("✅ Hash determinism: PASS")


def test_internal_fields_excluded():
    """Verify that _-prefixed fields don't affect the hash."""
    row1 = {"diagnosis_id": "D001"}
    row2 = {"diagnosis_id": "D001", "_hash": "xyz", "_batch_id": "abc"}
    assert compute_row_hash(row1) == compute_row_hash(row2), "Internal fields must be excluded"
    print("✅ Internal fields excluded: PASS")


def test_idempotent_merge():
    """
    Insert the same data twice into Neo4j and verify that:
      (1) First insert creates the node with `created_at`.
      (2) Second insert (same data) does NOT update `updated_at`.
      (3) A third insert with changed data DOES update `updated_at`.
    """
    connector = Neo4jConnector(URI, USER, PWD)
    try:
        # Clean up test nodes
        connector.run_query("MATCH (d:Diagnosis {diagnosis_id: 'TEST_IDEM_001'}) DETACH DELETE d")
        connector.run_query(
            "MATCH (bi:BatchIngestion) WHERE bi.source_table = 'diagnoses' "
            "AND bi.batch_id STARTS WITH 'test_' DETACH DELETE bi"
        )

        # --- Run 1: initial insert ---
        inserter1 = BatchInserter(connector)
        inserter1.batch_id = "test_run1"  # deterministic for testing
        diagnoses = [FakeDiagnosis("TEST_IDEM_001", "Alzheimer Disease")]
        count1 = inserter1._insert_diagnoses_batch(diagnoses)
        print(f"  Run 1: wrote {count1} node(s)")

        # Fetch the node
        result1 = connector.run_query(
            "MATCH (d:Diagnosis {diagnosis_id: 'TEST_IDEM_001'}) "
            "RETURN d.data_hash AS hash, d.created_at AS created, "
            "d.updated_at AS updated, d.batch_id AS batch_id"
        )
        assert len(result1) == 1, f"Expected 1 node, got {len(result1)}"
        node1 = result1[0]
        assert node1['hash'] is not None, "data_hash must be set"
        assert node1['batch_id'] == 'test_run1', f"batch_id mismatch: {node1['batch_id']}"
        print(f"  Run 1: hash={node1['hash'][:16]}… created_at={node1['created']}")

        # --- Run 2: re-insert same data (should be no-op) ---
        inserter2 = BatchInserter(connector)
        inserter2.batch_id = "test_run2"
        count2 = inserter2._insert_diagnoses_batch(diagnoses)
        print(f"  Run 2: wrote {count2} node(s)")

        result2 = connector.run_query(
            "MATCH (d:Diagnosis {diagnosis_id: 'TEST_IDEM_001'}) "
            "RETURN d.data_hash AS hash, d.created_at AS created, "
            "d.updated_at AS updated, d.description AS desc"
        )
        node2 = result2[0]
        assert node2['hash'] == node1['hash'], "Hash must remain the same"
        # updated_at should NOT have changed (same hash → skip)
        assert node2['updated'] == node1.get('updated'), \
            f"updated_at must NOT change on re-insert: {node2['updated']} vs {node1.get('updated')}"
        print(f"  Run 2: hash unchanged, updated_at NOT modified → idempotent ✅")

        # --- Run 3: insert with changed data (should update) ---
        inserter3 = BatchInserter(connector)
        inserter3.batch_id = "test_run3"
        changed = [FakeDiagnosis("TEST_IDEM_001", "Mild Cognitive Impairment")]
        count3 = inserter3._insert_diagnoses_batch(changed)
        print(f"  Run 3: wrote {count3} node(s)")

        result3 = connector.run_query(
            "MATCH (d:Diagnosis {diagnosis_id: 'TEST_IDEM_001'}) "
            "RETURN d.data_hash AS hash, d.updated_at AS updated, "
            "d.description AS desc"
        )
        node3 = result3[0]
        assert node3['hash'] != node1['hash'], "Hash must change when data changes"
        assert node3['desc'] == "Mild Cognitive Impairment", "Description must be updated"
        assert node3['updated'] is not None, "updated_at must be set on real update"
        print(f"  Run 3: hash changed, description updated → change detection ✅")

        # --- Verify BatchIngestion meta-nodes ---
        bi_result = connector.run_query(
            "MATCH (bi:BatchIngestion) WHERE bi.batch_id STARTS WITH 'test_' "
            "RETURN bi.batch_id AS bid, bi.source_table AS tbl, bi.written_rows AS rows "
            "ORDER BY bi.batch_id"
        )
        assert len(bi_result) >= 3, f"Expected ≥3 BatchIngestion nodes, got {len(bi_result)}"
        print(f"  BatchIngestion meta-nodes: {len(bi_result)} found ✅")

        print("\n✅ ALL IDEMPOTENCY TESTS PASSED!")

    finally:
        # Cleanup
        connector.run_query("MATCH (d:Diagnosis {diagnosis_id: 'TEST_IDEM_001'}) DETACH DELETE d")
        connector.run_query(
            "MATCH (bi:BatchIngestion) WHERE bi.batch_id STARTS WITH 'test_' DETACH DELETE bi"
        )
        connector.close()


if __name__ == "__main__":
    test_hash_determinism()
    test_internal_fields_excluded()

    if not PWD:
        print("\n⚠️  NEO4J_PASSWORD not set — skipping live Neo4j idempotency test.")
        print("   Set NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD in .env to run full test.")
    else:
        print(f"\n--- Live Neo4j Test ({URI}) ---")
        test_idempotent_merge()
