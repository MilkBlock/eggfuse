import struct
import unittest
from collections import Counter
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import torch

from protocol_learning import LearningPolicy, LearningStream
from protocol_model import value_inputs


class TypedValues(unittest.TestCase):
    @staticmethod
    def features(values):
        return value_inputs(
            SimpleNamespace(
                rows=torch.zeros(len(values), 4),
                value_ends=np.cumsum([len(v) for v in values], dtype=np.uint64),
                values=np.frombuffer(b"".join(values), dtype=np.uint8),
            )
        )

    def test_all_wire_kinds_and_absent_observation(self):
        values = [
            struct.pack("<BQ", 0, 7),
            struct.pack("<Bq", 1, -2),
            struct.pack("<BQ", 2, 1 << 63),
            struct.pack("<BQ", 3, 0),
            struct.pack("<BQ", 4, 0),
            struct.pack("<BQQBQQ", 5, 0, 1, 1, 0, 0),
            b"",
        ]
        out = self.features(values)
        torch.testing.assert_close(out[:6, :6], torch.eye(6))
        self.assertEqual(float(out[-1].abs().sum()), 0)
        for i, value in enumerate(values):
            torch.testing.assert_close(self.features([value])[0], out[i])

    def test_payload_past_the_numeric_prefix_changes_features(self):
        prefix = struct.pack("<BQ", 3, 32) + b"z" * 31
        x = self.features([prefix + b"a", prefix + b"b"])
        self.assertFalse(torch.equal(x[0], x[1]))

    def test_status_only_frame(self):
        x = value_inputs(
            SimpleNamespace(rows=torch.zeros(3, 4), value_ends=np.empty(0, np.uint64))
        )
        self.assertEqual(len(x), 3)
        self.assertEqual(int(x.count_nonzero()), 0)


class PortMemory(unittest.TestCase):
    def test_duplicate_reads_share_an_observation_and_a_new_version_rebinds(self):
        study = object.__new__(LearningPolicy)
        study.ports = {}
        study.boundaries = []
        study.address_mask = 9751
        study.feedback = lambda raw: raw[:, :16]
        addr = torch.tensor([[32, 1, 5]])
        client = Mock(capacity=8, verdicts=Counter())
        value = struct.pack("<Bq", 1, 12)
        client.collect.return_value = SimpleNamespace(
            rows=torch.tensor([[1, 14, -1, 0]]),
            value_ends=np.array([9]),
            values=np.frombuffer(value, np.uint8),
        )
        stream = object.__new__(LearningStream)
        stream.transaction = client
        stream.study = study
        stream.rule = 2
        stream.roles = [[(32, 1)]]
        stream.stats = Counter()
        stream.port_refs = lambda depth: addr
        stream.read_values(0, torch.tensor([[0], [0]]))
        stream.read_values(0, torch.tensor([[0]]))
        self.assertEqual(client.enqueue.call_count, 1)
        self.assertIn(study.memory_address(32, 1), study.ports)
        study.record_boundaries = False
        study.arm = "B"
        study.run_snapshot(
            {"rules": []},
            (np.array([[32, 1, 0, 6, 0, 1]]), None, [], None),
            None,
            None,
            client,
            stream.stats,
            float("inf"),
        )
        self.assertFalse(study.ports)
        addr[0, 2] = 6
        stream.read_values(0, torch.tensor([[0]]))
        self.assertEqual(client.enqueue.call_count, 2)
        self.assertEqual(client.enqueue.call_args.args[1][0, 2], 6)


if __name__ == "__main__":
    unittest.main()
