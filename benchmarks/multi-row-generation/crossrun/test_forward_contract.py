"""Run the actual GPU decoders and inspect both the generated and visible token."""
from pathlib import Path
import unittest

import mlx.core as mx
import mlx.nn as nn
import numpy as np

from cross_model import CrossRun, inputs, project, projection_recipe, scores_to_fields
from stream_model import StreamGenerator


ROOT = Path(__file__).resolve().parent
PLAN = projection_recipe(ROOT / 'compiler/plan.json')


def materialize(tree):
    mx.eval(tree)
    if isinstance(tree, (tuple, list)):
        return tuple(materialize(item) for item in tree)
    return np.array(tree)


def assert_same(tree, other):
    if isinstance(tree, tuple):
        assert len(tree) == len(other)
        for x, y in zip(tree, other):
            assert_same(x, y)
    else:
        np.testing.assert_array_equal(tree, other)


def force_field_head(head, mode):
    # Predict an exact alternative symbol in every group whatever the latent.
    bias = np.zeros(16, np.float32)
    for offset, width in ((0, 8), (8, 4), (12, 4)):
        bias[offset + (width-1 if mode else 0)] = 100.0
    head.weight = mx.zeros_like(head.weight)
    head.bias = mx.array(bias)


class Tap(nn.Module):
    def __init__(self, linear, observe):
        super().__init__()
        self.linear = linear
        self.observe = observe

    def __call__(self, visible):
        self.observe(visible)
        return self.linear(visible)


class ForwardContract(unittest.TestCase):
    def setUp(self):
        if not mx.metal.is_available():
            self.fail('these checks require the Metal GPU')
        mx.set_default_device(mx.gpu)
        mx.random.seed(1103)
        self.a = mx.array([[[3, 1], [3, 1], [5, 0], [7, 2]]])
        self.b = mx.array([[[3, 2], [3, 2], [5, 1], [6, 0]]])
        self.request = mx.array([[[0, 0, 1], [0, 0, 2], [2, 2, 0], [3, 3, 3]]])
        self.sp = mx.array([[i//2, i%2] for i in range(8)])
        self.pp = self.sp + mx.array([0, 2])

    def test_make_reproduces_original_row_sequence_and_token(self):
        original = StreamGenerator('feedback')
        cross = CrossRun('learned', PLAN)
        cross.make.update(original.parameters())
        ar, br, x = inputs(self.a, self.b)
        reference = original(x, self.sp, self.pp, 4, 2)
        h, live, left, right, fields, emitted = cross.make.produce(
            x, (ar, br), self.sp, self.pp, PLAN[0], False)
        for value, key in ((h,'latent'), (live,'active_logits'),
                           (mx.stack((left,right),2),'pointer_logits'),
                           (fields,'field_logits'), (emitted,'token')):
            assert_same(materialize(value), materialize(reference[key]))
        # Decode independently from the heads, then reconstruct every token byte.
        h, live, left, right, fields, emitted = materialize((h,live,left,right,fields,emitted))
        decisions = [live,left,right,fields[...,:8],fields[...,8:12],fields[...,12:]]
        symbols = [np.eye(head.shape[-1], dtype=np.float32)[head.argmax(-1)] for head in decisions]
        np.testing.assert_array_equal(emitted, np.concatenate([h,*symbols], axis=-1))
        self.assertEqual(emitted.shape, (1,8,90))

    def test_projection_keeps_selected_wrong_parent(self):
        ar, br, _ = inputs(self.a, self.b)
        left = mx.eye(4)[mx.array([[0,1,2]])]
        right = mx.eye(4)[mx.array([[0,0,3]])]
        # A0 and A1 are tied on fields; A2 and B3 have unequal keys.
        pairs = project(ar, br, (left, right), PLAN[0])
        np.testing.assert_array_equal(materialize(pairs), [[[0,0,3,1,2],[1,0,3,1,2],[2,3,5,0,0]]])
        # A deliberately wrong Request remains selected. The projector does not
        # suppress the row or search for the Request that matches A1.
        pair_choice = mx.eye(3)[mx.array([[0,1,2]])]
        request_choice = mx.eye(4)[mx.array([[1,0,3]])]
        result = project(pairs, self.request, (pair_choice, request_choice), PLAN[1])
        np.testing.assert_array_equal(materialize(result), [[[0,0,2,1,2],[1,0,1,1,2],[2,3,3,0,0]]])

    def test_field_head_perturbation(self):
        for arm in ('learned', 'static', 'aux'):
            cross = CrossRun(arm, PLAN)
            def forward(head_mode, training_heads=False):
                force_field_head(cross.make.fields.layers[-1], head_mode)
                force_field_head(cross.finish.fields, head_mode)
                return materialize(cross(self.a,self.b,self.request,training_heads=training_heads))
            before, after = forward(False), forward(True)
            if arm == 'learned':
                for stage in (0, 1):
                    a = scores_to_fields(mx.array(before[0][stage][3]))
                    b = scores_to_fields(mx.array(after[0][stage][3]))
                    self.assertTrue(np.all(materialize(a) != materialize(b)))
                self.assertTrue(np.any(before[1][...,74:] != after[1][...,74:]))
            else:
                assert_same(before, after)
            if arm == 'aux':
                trained0, trained1 = forward(False,True), forward(True,True)
                self.assertTrue(np.any(trained0[0][0][3] != trained1[0][0][3]))
                self.assertTrue(np.any(trained0[0][1][3] != trained1[0][1][3]))
                assert_same(trained0[1], after[1])
                assert_same(trained1[1], after[1])

    def test_exact_consumer_visibility(self):
        for arm in ('learned','static','aux'):
            cross = CrossRun(arm, PLAN)
            observed = []
            cross.finish.pair = Tap(cross.finish.pair, observed.append)
            for mask in ('none','parents','parents_latent'):
                stages, emitted = cross(self.a,self.b,self.request,mask=mask)
                visible = materialize(observed.pop())
                full = materialize(emitted)
                expected = full.copy()
                if mask != 'none':
                    expected[...,66:74] = 0
                if mask == 'parents_latent':
                    expected[...,:64] = 0
                np.testing.assert_array_equal(visible,expected)
                if mask == 'none':
                    source_token = full
                else:
                    np.testing.assert_array_equal(full,source_token)
                decoded = [materialize(mx.argmax(x,axis=-1)) for x in stages[0][:3]]
                decoded.extend(np.moveaxis(materialize(scores_to_fields(stages[0][3])), -1, 0))
                offset = 64
                for width, selected in zip((2,4,4,8,4,4), decoded):
                    np.testing.assert_array_equal(full[...,offset:offset+width],np.eye(width)[selected])
                    offset += width


if __name__ == '__main__':
    unittest.main()
