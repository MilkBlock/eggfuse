import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import torch

from cell_transaction import STATUS
from next_cell_corpus import collect
from next_cell_train import combine
from query_fit import batch


class NextCellTest(unittest.TestCase):
    def test_alias_ce_uses_the_whole_cell_and_padding_preserves_probability(self):
        # First target is either of two parent addresses under template 0.
        # Second target has no parents and uses template 1.
        meta = np.zeros((3, 2, 7), np.float32)
        meta[:, :, 2] = -1
        meta[:2, :, 5:] = 1
        meta[2, 0, 5:] = 1
        x = dict(
            features=np.array([[0.0], [0.5], [-1.0]], np.float32),
            paths=np.array([[[1], [2]], [[1], [-2]], [[-1], [0]]], np.int32),
            meta=meta,
            offsets=np.array([0, 2, 3]),
        )
        net = torch.nn.Linear(1, 1, bias=False)
        with torch.no_grad():
            net.weight.fill_(1)
        s = combine([x, x])
        m, _ = batch(net, s, np.arange(4), "cpu")
        template = torch.sigmoid(torch.tensor(0.5))
        torch.testing.assert_close(
            m.logsumexp(1).exp(), torch.stack([template, 1 - template] * 2)
        )
        (-m.logsumexp(1).mean()).backward()
        self.assertTrue(torch.isfinite(net.weight.grad).all())
        x["meta"][0, 0, 6] = 0
        with self.assertRaisesRegex(ValueError, "domain"):
            combine([x])

    def test_receipt_evidence_and_physical_state_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "program"
            folder.mkdir()
            prog = b'{"recipe":{"tables":[],"rules":[]}}'
            (folder / "program.json").write_bytes(prog)
            (root / "buffer").mkdir()
            accepted = STATUS.index("accepted")
            binding = STATUS.index("binding")
            frame = dict(run=1, epoch=1, retired=[], updates=[], accepted=[], rules=[])
            events = [
                dict(
                    frame=frame,
                    context=[0],
                    semantic_state="before",
                    generated=[[1, False, []], [2, False, []], [3, False, []]],
                    response=[[1, accepted], [2, binding], [3, accepted]],
                    signed_gain=[1, 0, 0],
                    stable=False,
                    omitted=[],
                    assisted=[],
                    assisted_response=[],
                )
            ]
            shard = dict(
                branch=2,
                program=hashlib.sha256(prog).hexdigest(),
                events=events,
                scheduler=[[1, 1, True, False, []]],
            )
            files = []
            for name, ctx in [("one", 0), ("again", 0), ("changed", 1)]:
                events[0]["context"] = [ctx]
                f = root / "buffer" / (name + ".gz")
                with gzip.open(f, "wt") as fp:
                    json.dump(shard, fp)
                files.append(f)
            states, counts = collect(files, folder)
            self.assertEqual(counts["pure_signed"], 9)
            self.assertEqual(len(states), 2)
            for _, groups in states.values():
                self.assertEqual([c.rule for cs in groups.values() for c in cs], [1])


if __name__ == "__main__":
    unittest.main()
