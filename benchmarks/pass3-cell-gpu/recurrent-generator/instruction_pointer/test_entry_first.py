from collections import Counter
from types import SimpleNamespace
import unittest
import numpy as np
from entry_closure import Rules, Tape
from entry_rollout import Entries


class EntryFirstTest(unittest.TestCase):
    def test_rule_needing_another_external_table_stays_at_boundary(self):
        def spec(tabs, outputs):
            return dict(
                inputs=[dict(table=t) for t in tabs],
                outputs={
                    str(pc): dict(table=t, presence="conditional") for pc, t in outputs
                },
            )

        r = Rules(dict(rules=[spec([1], [(8, 2)]), spec([1, 2], []), spec([2, 3], [])]))
        counts = Counter()
        steps = list(r.extensions(r.root(0), counts))
        self.assertEqual(steps, [(1, 1, ((-1, 0), (0, 8)))])
        self.assertEqual(counts["needs_additional_external_table"], 1)

    def test_required_return_must_be_visible_at_first_publication(self):
        src = SimpleNamespace(
            q={1: dict(run=3, parents=[])},
            schedule={2: [3, 5, 9]},
            snap=SimpleNamespace(
                version=lambda t, pc, run: 7 if run == 4 and pc == 8 else None
            ),
            index={(5, 2, ((1, 8, 7),)): 42, (9, 2, ((1, 9, 7),)): 43},
        )
        self.assertEqual(Tape.extend(src, (1,), (2, 1, ((0, 8),))), (1, 42))
        self.assertIsNone(Tape.extend(src, (1,), (2, 1, ((0, 9),))))
        src.index = {(9, 2, ((1, 8, 7),)): 43}
        self.assertIsNone(Tape.extend(src, (1,), (2, 1, ((0, 8),))))

    def test_only_exact_completed_positions_leave_a_posting_page(self):
        obj = SimpleNamespace(
            count=Counter(), proven=lambda *args: {(3,): {1, 4, 8}, (1,): {6}}
        )
        post = np.array([7, 1, 3, 4, 9, 0, 2, 5, 6, 8])
        rows = list(
            Entries.uncovered(
                obj,
                None,
                0,
                (0, 1),
                np.array([[3], [1], [0]]),
                post,
                np.array([1, 5, 5]),
                np.array([4, 5, 0]),
            )
        )
        kept = [
            (int(i), int(post[p]))
            for owners, positions in rows
            for i, p in zip(owners, positions)
        ]
        self.assertEqual(kept, [(0, 3), (0, 9), (1, 0), (1, 2), (1, 5), (1, 8)])
        self.assertEqual(obj.count["proven_candidate_positions_skipped"], 3)


class SearchProbeTest(unittest.TestCase):
    def test_multi_parent_proofs_stream_past_probe_without_reordering(self):
        from entry_search_probe import Sink

        rows = np.array(
            [[(1, 8, 3), (2, 0, 4)], [(2, 0, 4), (1, 8, 3)]], dtype=np.int64
        )
        completed = {4: {tuple(map(tuple, rows[0]))}}
        a, b = Sink({}, completed), Sink(completed, completed)
        a.issue(4, None, rows, None)
        b.issue(4, None, rows[1:], None)
        self.assertEqual(a.residual[4].digest(), b.residual[4].digest())
        self.assertEqual(a.advertised[4] - b.advertised[4], 1)
