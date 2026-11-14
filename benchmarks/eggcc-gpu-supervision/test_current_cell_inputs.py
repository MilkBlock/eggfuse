import unittest
import numpy as np
import mlx.core as mx
import test_neural_device_candidates as fixtures
from device_current_cell_inputs import current_inputs


class CurrentInputs(unittest.TestCase):
    def test_generated_cell_is_read_without_historical_latent(self):
        _, _, state, frames, target = fixtures.DeviceCandidates().prepared()
        a = current_inputs(state, frames, mx)
        changed = dict(state, tokens=mx.full_like(state['tokens'], float('nan')),
                       token_dirty=mx.ones_like(state['present']))
        b = current_inputs(changed, frames, mx)
        self.assertTrue(bool(a['mask'][target]))
        self.assertGreater(float(mx.max(mx.abs(a['fields'][target]))), 0.)
        np.testing.assert_array_equal(a['fields'], b['fields'])
        np.testing.assert_array_equal(a['mask'], b['mask'])
        self.assertTrue(bool(b['complete']))

    def test_query_consumes_current_embeddings(self):
        from device_current_cell_inputs import current_candidates
        from neural_device_candidates import compile_candidates
        from audit_snapshot_queries import device
        from neural_cell_transition import CellTransition
        recipe, local, state, frames, _ = fixtures.DeviceCandidates().prepared()
        inputs = current_inputs(state, frames, mx)
        model = CellTransition(inputs['fields'].shape[1], 32)
        plan = device(compile_candidates(local, recipe['rules'][0]))
        def run(s):
            return current_candidates(s, frames, plan, model.encode,
                                      mx.array(True), mx.array(True), mx)
        a = run(state)
        b = run(dict(state, tokens=mx.full_like(state['tokens'], float('nan'))))
        self.assertTrue(bool(a['complete']))
        np.testing.assert_array_equal(a['tokens'], b['tokens'])
        np.testing.assert_array_equal(a['binding_roots'], b['binding_roots'])
        self.assertTrue(bool(mx.all(mx.isfinite(b['tokens']))))

    def test_unsettled_and_hidden_cells(self):
        _, _, state, frames, target = fixtures.DeviceCandidates().prepared()
        unsettled = dict(state)
        unsettled['settled'] = mx.where(mx.arange(len(state['present'])) == target,
                                       False, state['settled'])
        a = current_inputs(unsettled, frames, mx)
        self.assertFalse(bool(a['complete']))
        self.assertFalse(bool(a['mask'][target]))
        hidden = dict(unsettled, visible=mx.where(mx.arange(len(state['present'])) == target,
                                                 False, state['visible']))
        b = current_inputs(hidden, frames, mx)
        self.assertTrue(bool(b['complete']))
        np.testing.assert_array_equal(b['fields'][target], 0.)


if __name__ == '__main__':
    unittest.main()
