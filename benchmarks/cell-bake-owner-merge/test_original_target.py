import json
from pathlib import Path
import tempfile
import unittest
from original_target import summarize


class OriginalTargetTests(unittest.TestCase):
    def check(self, change=None):
        baseline=dict(program_sha256='same',runs=2,graph_owned_heap_requested_before=1001)
        memory=dict(program_sha256='same',runs=2,graph_owned_teardown_bytes=510,graph_fields=[])
        checked=dict(program_sha256='same',runs=2,completed_owners=True,
                     every_run_graph_and_ordered_audits_equal=True,run_checks=[{},{}],
                     graph_owned_heap_requested_before=990,graph_owned_heap_requested_after=510)
        if change:change(memory,checked)
        with tempfile.TemporaryDirectory() as directory:
            paths=[Path(directory)/str(i) for i in range(3)]
            for path,data in zip(paths,[baseline,memory,checked]):path.write_text(json.dumps(data))
            return summarize(*paths)

    def test_target_keeps_original_denominator(self):
        result=self.check()
        self.assertEqual(result['target_graph_bytes'],300)
        self.assertEqual(result['remaining_bytes_to_target'],210)
        self.assertEqual(result['fraction_of_original'],510/1001)

    def test_different_source_is_not_comparable(self):
        with self.assertRaises(ValueError):
            self.check(lambda m,c:m.update(program_sha256='different'))

    def test_partial_or_false_acceptance_is_rejected(self):
        with self.assertRaises(ValueError):
            self.check(lambda m,c:c.update(run_checks=[{}]))
        with self.assertRaises(ValueError):
            self.check(lambda m,c:c.update(every_run_graph_and_ordered_audits_equal=False))
