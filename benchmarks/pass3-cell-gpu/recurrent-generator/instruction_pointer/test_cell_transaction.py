import io
import unittest
from types import SimpleNamespace

import numpy as np
import torch

from cell_transaction import MAGIC, Transaction, memory_frame


class TransactionTests(unittest.TestCase):
    def test_local_references_rebase_and_reset_at_chunk_boundary(self):
        results = np.array([[i, 14, 2, i] for i in range(1, 7)], dtype="<i8")
        proc = SimpleNamespace(stdin=io.BytesIO(), stdout=io.BytesIO(results.tobytes()))
        tx = Transaction(proc, 5)
        field = torch.tensor([[[-1, 0, 0, 2]]] * 3)
        local = torch.tensor([[[0, 0, 0, 0], [0, -1, 0, 0]]] * 3)
        reply = tx.compute_chain(15, (2, 3), (field, local))
        self.assertEqual(reply[:, 0].tolist(), [2, 4, 6])
        self.assertEqual(tx.computations, 6)
        wire = io.BytesIO(proc.stdin.getvalue())
        for ops_n, refs_n, expected in [(4, 6, [0, 2]), (2, 3, [0])]:
            self.assertEqual(
                np.frombuffer(wire.read(16), "<u4").tolist(), [MAGIC, ops_n, refs_n, 0]
            )
            ops = np.frombuffer(wire.read(40 * ops_n), "<i8").reshape(-1, 5)
            self.assertEqual(ops[-1, 4], refs_n)
            refs = np.frombuffer(wire.read(32 * refs_n), "<i8").reshape(-1, 4)
            self.assertEqual(refs[1::3, 1].tolist(), expected)
            self.assertTrue(np.all(refs[2::3, 1] == -1))
        self.assertFalse(wire.read())

    def test_ragged_tape_and_order(self):
        # Ordered requests cover a scalar computation, zero-parent proof and a
        # two-parent proof. Its named tuple must survive adjacent variable widths.
        response = np.array(
            [[1, 14, 2, -123], [2, 0, -1, 0], [3, 0, -1, 0]], dtype="<i8"
        )
        proc = SimpleNamespace(
            stdin=io.BytesIO(), stdout=io.BytesIO(response.tobytes())
        )
        tx = Transaction(proc, 3)
        tx.run = 5
        ops = np.array([[1, 0, 0, 2, 1], [0, 0, 1, -1, 1], [0, 0, 3, -1, 3]])
        refs = np.array([[-1, 3, 1, 0], [-2, 4, 1, -1], [5, 2, 9, -1]])
        result = tx.submit(ops, refs)
        self.assertTrue(torch.equal(result, torch.from_numpy(response)))
        wire = proc.stdin.getvalue()
        self.assertEqual(np.frombuffer(wire[:16], "<u4").tolist(), [MAGIC, 3, 3, 0])
        self.assertEqual(tx.sizes, {3: 1})
        tape = list(tx.offline_tape(5))
        self.assertEqual(tape[0]["parents"], [])
        self.assertEqual([p["address"]["token"] for p in tape[1]["parents"]], [-2, 5])
        self.assertEqual(list(tx.offline_tape(4)), [])

    def test_publication_rejects_offsets(self):
        row = np.array([[-1, 0, 0, 1, 0, 2]], dtype="<i8")
        stream = io.BytesIO(row.tobytes() + bytes(8))
        header = dict(typed_rows=1, typed_hashes=1, typed_retired=0, typed_accepted=0)
        with self.assertRaises(ValueError):
            memory_frame(stream, header)
