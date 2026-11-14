"""Compare training edge construction with the GPU kernel on identical sources.

This checks representation parity, not completeness of runtime source coverage.
"""
import unittest
from types import SimpleNamespace
import numpy as np
import mlx.core as mx
from multi_entry_ridge import template
from neural_cell_chains import pack_sources
from neural_snapshot_candidates import relational_edges


class EdgeParity(unittest.TestCase):
    def test_local_encoding_ignores_representative_names(self):
        from multi_entry_ridge import encode
        roles = np.random.default_rng(91).normal(size=(3, 64)).astype(np.float32)
        def token(roots):
            return encode([(i, {}, ('Expr', r)) for i, r in enumerate(roots)],
                          roles, 'class-balanced')
        np.testing.assert_array_equal(token([5, 8, 5]), token([1, 2, 1]))
        self.assertGreater(float(np.max(np.abs(token([5, 8, 5]) -
                                               token([1, 1, 1])))), 1e-4)
        # An unchanged local partition is not a proof about external incidence.
        # A merge with a neighbor changes cross-Cell edges even if the local
        # token's internal partition is unchanged.
        r = mx.array(roles[:1][None, :, :].repeat(2, axis=0))
        sources = mx.array([[0, 1]])
        before = relational_edges(mx.array([[5], [8]]), r, sources)
        after = relational_edges(mx.array([[5], [5]]), r, sources)
        self.assertGreater(float(mx.max(mx.abs(before - after))), 1e-4)

    def test_shared_roots_repeated_sources_and_padding(self):
        rng = np.random.default_rng(2026)
        rules = []
        for name, width in [('F', 3), ('G', 2)]:
            rules.append(dict(slots=[dict(sort=dict(kind='eq', name='Expr'),
                                          definition='query') for _ in range(width)],
                              query=[dict(call=dict(table=name),
                                          args=[dict(slot=i) for i in range(width)])], effects=[]))
        for _ in range(32):
            roots = rng.integers(0, 4, size=5).tolist()
            sources = [(rules[0], roots[:3]), (rules[1], roots[3:]),
                       (rules[0], roots[:3])]
            ref = SimpleNamespace(root=lambda v: v, scalar_values={})
            expected = pack_sources(sources, [True, False, True], ref, 4, 3)
            labels = np.full((4, 3), -1, np.int32)
            roles = np.zeros((4, 3, 64), np.float32)
            for i, (rule, values) in enumerate(sources):
                labels[i, :len(values)] = values
                roles[i, :len(values)] = template(rule)[0]
            actual = relational_edges(mx.array(labels), mx.array(roles),
                                      mx.array([[0, 1, 2, 3]]))
            np.testing.assert_allclose(np.array(actual)[0], expected['edges'],
                                       atol=2e-7, rtol=2e-6)


if __name__ == '__main__':
    unittest.main()
