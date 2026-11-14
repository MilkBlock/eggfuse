import itertools
import unittest
import numpy as np
import mlx.core as mx
from neural_snapshot_candidates import candidate_indices, relational_edges, import_interfaces, binding_key
from reference_union_family import Reference
from test_neural_cell_chains import recipe


class SnapshotCandidates(unittest.TestCase):
    def test_complete_cartesian_without_binding_filter(self):
        pools = [[2, 4], [1, 5, 7]]
        indices, mask = candidate_indices(pools, 0, 6, 3)
        np.testing.assert_array_equal(np.array(indices)[:, :2], list(itertools.product(*pools)))
        np.testing.assert_array_equal(np.array(mask), [[True, True, False]] * 6)
        ix, _ = candidate_indices(pools, 2, 3, 2)
        np.testing.assert_array_equal(ix, np.array(indices)[2:5, :2])

    def test_relation_encoding_invariant_to_identity_renumbering(self):
        mx.random.seed(8)
        roles = mx.random.normal((3, 3, 64))
        labels = mx.array([[0, 1, -1], [1, 2, -1], [3, 1, -1]])
        renamed = mx.array([[100, 5, -1], [5, 8, -1], [200, 5, -1]])
        ix = mx.array([[0, 1], [1, 2]])
        np.testing.assert_allclose(relational_edges(labels, roles, ix), relational_edges(renamed, roles, ix), atol=1e-6)
        # Check the GPU pair contraction independently, including padding.
        expected = np.zeros((2, 2, 2, 64), np.float32)
        r, v, indices = np.array(roles), np.array(labels), np.array(ix)
        for n, sources in enumerate(indices):
            for a, i in enumerate(sources):
                for b, j in enumerate(sources):
                    terms = [r[i, p] * r[j, q] for p in range(3) for q in range(3) if v[i, p] >= 0 and v[i, p] == v[j, q]]
                    if terms:
                        expected[n, a, b] = np.sum(terms, axis=0)/np.sqrt(len(terms))
        np.testing.assert_allclose(relational_edges(labels, roles, ix), expected, atol=1e-6)

    def test_snapshot_candidates_include_negatives_and_all_oracle_matches(self):
        r = recipe(); rule = r['rules'][0]
        rule['query'].append(dict(call=dict(table='F'), args=[dict(slot=1), dict(slot=2)]))
        rule['slots'][2]['definition'] = 'query'; rule['effects'] = []
        snapshot = dict(rows=[dict(table='F', values=[dict(sort='E', eq=str(a)), dict(sort='E', eq=str(b))], subsumed=False) for a, b in [(0, 1), (1, 2), (3, 4)]])
        rows, ids, pools, _, _, _ = import_interfaces(r, snapshot)
        ix, _ = candidate_indices([pools['F']]*2, 0, 9, 2)
        keys = [binding_key(rule, chosen, rows, ids) for chosen in np.array(ix)]
        self.assertEqual(sum(k is None for k in keys), 8)
        expected = {tuple(sorted(b.items())) for b in Reference(r, rows, ids).matches(rule)}
        self.assertEqual({k for k in keys if k is not None}, expected)


if __name__ == '__main__':
    unittest.main()
