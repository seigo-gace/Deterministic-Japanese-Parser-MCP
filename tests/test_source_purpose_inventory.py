"""Tests for the read-only source-purpose inventory bootstrap."""
import unittest

from tools.audit_source_purpose_inventory import inventory


class SourcePurposeInventoryTest(unittest.TestCase):
    def test_no_claim_of_field_or_runtime_coverage(self):
        rows = inventory({"sources": [{
            "source_id": "example", "source_roles": ["pronunciation", "orthography"],
            "rights_lane": "S", "public_runtime_eligible": False,
            "parser_family": "skk",
        }]})
        self.assertEqual([r["source_role"] for r in rows], ["orthography", "pronunciation"])
        self.assertTrue(all(r["field_path"] == "UNKNOWN" for r in rows))
        self.assertTrue(all(r["consumed_records"] == "UNKNOWN" for r in rows))
        self.assertTrue(all(r["logical_destination"] == "UNKNOWN" for r in rows))
        self.assertTrue(all(r["public_runtime_eligible"] == "false" for r in rows))

    def test_duplicate_source_id_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate source_id"):
            inventory({"sources": [{"source_id": "x"}, {"source_id": "x"}]})

    def test_role_labels_are_not_unverified_semantic_assignments(self):
        rows = inventory({"sources": [{"source_id": "x", "source_roles": ["lexical-relation"]}]})
        self.assertEqual(rows[0]["gap_status"], "NEEDS_FIELD_AND_RUNTIME_EVIDENCE")
        self.assertEqual(rows[0]["japanese_reading_need"], "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
