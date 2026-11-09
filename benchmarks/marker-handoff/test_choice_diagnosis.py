#!/usr/bin/env python3
"""Regression checks against saved exports; never execute a workload."""
import copy
from contextlib import redirect_stdout
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import choice_diagnosis as d

ROOT = Path(sys.argv.pop(1))


class Acceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.left = d.load(ROOT / 'native-legacy.json')
        cls.right = d.load(ROOT / 'run-legacy/state.json')
        cls.schemas = d.load(ROOT / 'sum-legacy/program.json')['source_core']['tables']

    def changed(self, modify):
        state = copy.deepcopy(self.right)
        modify(state)
        return d.check_pair(self.left, state, self.schemas)

    def test_saved_choices_pass_semantic_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            out = Path(tmp) / 'result.json'
            self.assertEqual(d.main(ROOT, out), 0)
            report = d.load(out)
            self.assertEqual(report['status'], 'pass')
            self.assertEqual(len(report['comparisons']), 4)
            self.assertTrue(all(r['status'] == 'pass' for r in report['comparisons'].values()))

    def test_changed_selected_cost_is_a_difference(self):
        def change(s):
            tc = next(r['values'][-1] for r in s['rows'] if r['table'] == 'ExtractedExpr')
            row = next(r for r in s['rows'] if r['table'] == 'TCPair' and r['values'][-1] == tc)
            row['values'][1]['value'] += 1
        self.assertEqual(self.changed(change)['status'], 'difference')

    def test_illegal_selected_candidate_is_a_difference(self):
        def change(s):
            row = next(r for r in s['rows'] if r['table'] == 'ExtractedExpr')
            candidates = {d.key(r['values'][1]) for r in s['rows']
                          if r['table'] == 'PotentialExtractedExpr' and r['values'][0] == row['values'][0]}
            row['values'][-1] = next(r['values'][-1] for r in s['rows']
                                     if r['table'] == 'TCPair' and d.key(r['values'][-1]) not in candidates)
        self.assertEqual(self.changed(change)['status'], 'difference')

    def test_division_is_not_treated_as_commutative(self):
        def change(s):
            op = next(r['values'][-1] for r in s['rows'] if r['table'] == 'Div')
            row = next(r for r in s['rows'] if r['table'] == 'TermBop'
                       and r['values'][0] == op and r['values'][1] != r['values'][2])
            row['values'][1], row['values'][2] = row['values'][2], row['values'][1]
        self.assertEqual(self.changed(change)['status'], 'inconclusive')

    def test_changed_core_visibility_is_a_difference(self):
        def change(s):
            row = next(r for r in s['rows'] if r['table'] == 'Int')
            row['subsumed'] = not row['subsumed']
        self.assertEqual(self.changed(change)['status'], 'difference')

    def test_missing_or_unrecognized_states_do_not_pass(self):
        self.assertEqual(d.check_pair(self.left, {'rows': []}, self.schemas)['status'], 'inconclusive')
        self.assertEqual(d.check_pair(self.left, {}, self.schemas)['status'], 'inconclusive')
        partial = {'rows': [next(r for r in self.right['rows'] if r['table'] == 'Int')], 'anchors': []}
        self.assertEqual(d.check_pair(partial, partial, self.schemas)['status'], 'inconclusive')
        def change(s):
            s['rows'].append({'table': 'UnreviewedTermConsumer', 'values': [], 'subsumed': False})
        self.assertEqual(self.changed(change)['status'], 'inconclusive')

    def test_unrooted_graph_is_inconclusive(self):
        v = {'sort': 'E', 'eq': 'unrooted'}
        state = {'rows': [{'table': 'F', 'values': [v, v], 'subsumed': False}], 'anchors': []}
        schemas = [{'name': 'F', 'kind': 'constructor', 'schema': [{'name': 'E'}, {'name': 'E'}]}]
        self.assertEqual(d.check_pair(state, state, schemas)['status'], 'inconclusive')

    def test_unreviewed_source_reports_inconclusive(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            root = Path(tmp)
            for name in ('native-source.json', 'native-legacy.json', 'native-values.json',
                         'run-legacy/state.json', 'run-values/state.json'):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('{"rows":[]}')
            (root / 'sum-legacy').mkdir()
            (root / 'sum-legacy/program.json').write_text('{"source_core":{"tables":[]}}')
            out = root / 'result.json'
            self.assertEqual(d.main(root, out), 2)
            self.assertIn('outside the reviewed', d.load(out)['reason'])

    def test_missing_files_report_inconclusive(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            out = Path(tmp) / 'result.json'
            self.assertEqual(d.main(Path(tmp), out), 2)
            self.assertEqual(d.load(out)['status'], 'inconclusive')

    def test_python_optimized_mode_cannot_disable_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'result.json'
            run = subprocess.run([sys.executable, '-O', str(Path(d.__file__)), str(ROOT), str(out)],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 2, run.stderr)
            self.assertEqual(d.load(out)['status'], 'inconclusive')
            self.assertIn('without python -O', d.load(out)['reason'])


if __name__ == '__main__':
    unittest.main()
