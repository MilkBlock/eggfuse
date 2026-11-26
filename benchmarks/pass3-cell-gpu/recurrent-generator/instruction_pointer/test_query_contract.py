import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch

from query_environment import QueryMemory
from query_fit import batch
from response_plan import ResponseMemory


class QueryContractTests(unittest.TestCase):
    def test_native_order_and_visibility(self):
        m = QueryMemory.__new__(QueryMemory)
        with (
            tempfile.TemporaryDirectory() as dir_,
            patch.object(ResponseMemory, "update") as publish,
        ):
            m.observer_path = Path(dir_) / "events"
            m.observer_path.write_text("[4,17,true,false,[[2,13,false],[1,0,true]]]\n")
            m.reader = None
            try:
                frame = dict(
                    run=4,
                    epoch=17,
                    rules=[[2, 13], [1, 0]],
                    updates=[],
                    retired=[],
                    accepted=[],
                )
                m.update(frame)
                publish.assert_called_once_with(frame)
                self.assertEqual(m.rule_ids, [2, 1])
                self.assertEqual(m.rule_features[:, 0].tolist(), [0, 1])
                self.assertGreater(m.rule_features[0, 1], m.rule_features[1, 1])
                m.reader.seek(0)
                with self.assertRaisesRegex(ValueError, "disagrees"):
                    m.update(dict(frame, epoch=18))
            finally:
                m.reader.close()

    def test_disjoint_class_mass_and_projection_posterior(self):
        # Three verified leaves in a two-level fixture; the last class has one member.
        s = dict(
            features=np.zeros((2, 99), np.float32),
            offsets=np.array([0, 2, 3]),
            paths=np.array([[[1], [1]], [[1], [-1]], [[-1], [0]]], np.int32),
            meta=np.zeros((3, 2, 7), np.float32),
        )
        s["meta"][:, :, 2] = -1
        s["meta"][:, :, 5:] = 1
        net = torch.nn.Linear(99, 1, bias=False)
        matrix, p = batch(net, s, np.array([0, 1]), "cpu")
        torch.testing.assert_close(matrix.logsumexp(1).exp(), torch.tensor([0.5, 0.5]))
        s["meta"][0, 1, :5] = [0.2, 0, 0.4, 1, 1]
        _, p = batch(net, s, np.array([0]), "cpu")
        self.assertAlmostEqual(p[0, 1].item(), 0.4 + 0.6 * 0.8 * 0.5, places=6)


if __name__ == "__main__":
    unittest.main()
