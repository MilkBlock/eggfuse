import unittest
from types import SimpleNamespace

import torch

from actor import InstructionActor, row_features
from cell_kv_model import CellKV, public_values
from cell_kv_runtime import Instances, teacher_labels
from cell_kv_probes import swap_addresses


class KVTest(unittest.TestCase):
    def setUp(self):
        self.w = SimpleNamespace(
            root=0,
            primitives=3,
            layouts=[
                [],
                [],
                [],
                [(0, 0, [(-1, 0)]), (1, 1, [(0, 2)]), (2, 2, [(1, 1), (0, 2)])],
            ],
            menu=lambda _: [0, 3],
        )

    def test_complete_token_distribution_and_gradient(self):
        from torch import nn

        torch.manual_seed(7)
        net = CellKV.__new__(CellKV)
        nn.Module.__init__(net)
        net.actor = InstructionActor()
        net.arm = "D"
        net.read_ports_at_template = True
        codes = torch.randn(2, 32, requires_grad=True)
        net.cache = torch.randn(3, 32), codes, torch.randn(1, 32)
        w = SimpleNamespace(
            layouts=[[(0, 0, [(-1, 0)])], [(1, 0, [])]],
            roles=[(0,), ()],
            cat=SimpleNamespace(inputs={("generated", 0): [1], ("generated", 1): []}),
        )
        ports = [
            ((7, 2, 1), 7, 0, 0, (17, 19), False, ()),
            ((7, 4, 1), 7, 0, 0, (), False, ()),
            ((-5, 0, 0), -5, -1, 0, (23,), False, ()),
        ]
        s = dict(run=1, epoch=2, response=(1, 2, 0), menu=[0, 1], ports=ports)
        mem = net.state(w, s)
        terms = [net.token_loss(w, mem, (0, (p[0],))) for p in ports] + [
            net.token_loss(w, mem, (1, ()))
        ]
        torch.testing.assert_close((-torch.stack(terms)).exp().sum(), torch.tensor(1.0))
        terms[0].backward()
        for p in [
            codes,
            net.actor.query.weight,
            net.actor.input_content.weight,
            net.actor.latent.weight,
        ]:
            self.assertGreater(float(p.grad.norm()), 0)
        import numpy as np

        self.assertEqual(
            net.generate(w, dict(s, menu=[1], ports=[]), np.random.default_rng(3), 2),
            [(1, ()), (1, ())],
        )

    def test_standalone_features(self):
        vals = [(), (0,), ((1 << 64) - 1, 0, 4), (9, 8), (9, 8)]
        torch.testing.assert_close(
            public_values(vals), row_features(vals, 32, "cpu"), rtol=0, atol=0
        )

    def test_higher_ownership_and_exact_publication(self):
        m = Instances(self.w)
        m.begin(8, 3, ((-3, 0, 1),))
        m.owned[9] = (8, 1)
        m.owned[10] = (8, 2)
        m.wait_exports[10, 5] = 8

        def publish(uid, op, v):
            f = dict(
                run=3,
                epoch=7,
                rules=[(0, 0)],
                retired=[],
                accepted=[],
                updates=[
                    (
                        dict(token=uid, op=op),
                        dict(version=v, table=0, hashes=[7], forwarded=False),
                    )
                ],
            )
            m.update(f)
            return m.snapshot(self.w, f)

        publish(8, 2, 2)
        s = publish(9, 1, 3)
        self.assertEqual(len(s["ports"]), 1)
        self.assertFalse(m.completed)
        publish(10, 3, 4)
        self.assertFalse(m.completed)
        s = publish(10, 5, 5)
        self.assertEqual({p[1] for p in s["ports"]}, {8})
        self.assertEqual(m.completed, {8})
        publish(9, 1, 10)
        self.assertEqual(m.pins[9, 1], 3)
        m.update(dict(retired=[dict(token=10, op=5)], updates=[]))
        self.assertNotIn((10, 5), m.exposed)

    def test_offline_target_requires_all_static_wires(self):
        def q(uid, rid, parents):
            return dict(
                token=uid,
                run=uid,
                rule=rid,
                parents=[
                    dict(address=dict(token=p, op=op), version=1) for p, op in parents
                ],
            )

        qs = [q(1, 0, [(-1, 0)]), q(2, 1, [(1, 2)]), q(3, 2, [(2, 1), (1, 2)])]
        self.assertEqual(teacher_labels(self.w, qs), {1: (3, [1, 2, 3])})
        qs[-1]["parents"][1]["address"]["op"] = 99
        self.assertFalse(teacher_labels(self.w, qs))

    def test_address_permutation_preserves_aliases(self):
        r = (-3, 0, 1)
        s = dict(
            ports=[
                (r, -3, -1, 0, (7,), False, ()),
                ((5, 2, 2), 5, 3, 1, (9,), False, (r,)),
            ]
        )
        new = swap_addresses(s)["ports"]
        self.assertEqual(new[0][-1], (new[1][0],))
        self.assertNotEqual(new[1][0], r)


if __name__ == "__main__":
    unittest.main()
