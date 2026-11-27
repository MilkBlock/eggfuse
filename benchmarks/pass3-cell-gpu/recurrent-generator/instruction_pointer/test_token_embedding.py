import unittest
from types import SimpleNamespace

import torch

from cell_kv_model import public_values
from token_embedding import TokenEmbedding


class EmbeddingTest(unittest.TestCase):
    def inputs(self, variant):
        torch.manual_seed(72)
        net = TokenEmbedding.__new__(TokenEmbedding)
        torch.nn.Module.__init__(net)
        net.variant = variant
        nodes = torch.randn(4, 32)
        net.cache = (nodes, None, None)
        w = SimpleNamespace(
            layouts=[[(0, 0, [])]],
            cat=SimpleNamespace(
                inputs={("generated", 0): [1, 2]}, outputs={(("generated", 0), 0): 3}
            ),
        )
        refs = [(10, 0, 1), (20, 0, 1), (30, 0, 2)]
        ports = [
            (
                ref,
                ref[0],
                -1 if i < 2 else 0,
                0,
                (),
                False,
                tuple(refs[:2]) if i == 2 else (),
            )
            for i, ref in enumerate(refs)
        ]
        args = (
            dict(zip(refs, range(3))),
            [torch.tensor([i]) for i in range(3)],
            torch.arange(3),
            torch.randn(3, 32),
            torch.randn(3, 32),
        )
        return net, w, ports, args

    def test_parent_permutation(self):
        for v in ("current", "structure", "mixed", "interface"):
            net, w, ports, args = self.inputs(v)
            before = net.instance_embedding(w, ports, *args)
            ports[-1] = (*ports[-1][:-1], tuple(reversed(ports[-1][-1])))
            after = net.instance_embedding(w, ports, *args)
            self.assertEqual(torch.equal(before[0][-1], after[0][-1]), v != "interface")

    def test_structure_only_has_no_instance_value(self):
        net, w, ports, args = self.inputs("structure")
        owners, ext = net.instance_embedding(w, ports, *args)
        b, e = net.instance_embedding(w, ports, *args[:-1], args[-1] + 5)
        torch.testing.assert_close(b, owners)
        torch.testing.assert_close(e, ext)

    def test_row_encoding_collision(self):
        a, b = public_values([(9,), ((1 << 45) + 9,)])
        self.assertTrue(torch.equal(a, b))


if __name__ == "__main__":
    unittest.main()
