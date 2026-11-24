import unittest
from collections import Counter
from types import SimpleNamespace

import torch

from txn_policy import ReadPlan, ResponseStream, TransactionNet, plans


class TransactionPolicyTest(unittest.TestCase):
    def test_read_plans_bind_only_operands_available_before_partner(self):
        rd = SimpleNamespace(
            order=lambda _: [0, 1, 2],
            iface=SimpleNamespace(
                roles=[[("X", (3, 1)), ("Y", (2, 3)), ("Z", (7, 2))]],
                rules=[
                    {
                        "query": [
                            {
                                "call": {"primitive": "+"},
                                "args": [{"slot": 1}, {"slot": 2}, {"slot": 7}],
                            }
                        ]
                    }
                ],
            ),
        )
        self.assertEqual(plans(rd, 0, 1), [])
        self.assertEqual(plans(rd, 0, 2), [ReadPlan(0, ((0, 1), (1, 0)), 0)])

    def test_plan_orders_transaction_local_dependencies(self):
        rd = SimpleNamespace(
            order=lambda _: (0, 1),
            iface=SimpleNamespace(
                roles=[[("L", (0, 1)), ("R", (8,))]],
                rules=[
                    {
                        "query": [
                            {
                                "call": {"primitive": "*"},
                                "args": [{"slot": 1}, {"literal": 2}, {"slot": 7}],
                            },
                            {
                                "call": {"primitive": "+"},
                                "args": [{"slot": 0}, {"slot": 7}, {"slot": 8}],
                            },
                        ]
                    }
                ],
            ),
        )
        self.assertEqual(plans(rd, 0, 1), [])
        op = plans(rd, 0, 1, chains=True)[0]
        self.assertEqual(op.steps, ((0, ((0, 1), None)), (1, ((0, 0), ("local", 0)))))

    def test_response_guides_bucket_and_failed_computation_preserves_baseline(self):
        net = TransactionNet()
        with torch.no_grad():
            net.planes.weight.zero_()
            net.planes.weight[:, 0] = 1
        stream = ResponseStream.__new__(ResponseStream)
        stream.study = SimpleNamespace(net=net, mode="always")
        stream.choices = {1: [ReadPlan(2, ((0, 1),), 0)]}
        stream.joint_index = {}
        stream.rule = 3
        stream.semi = False
        stream.stats = Counter()
        stream.roles = [[(20, 2)], [(31, 3), (32, 3), (33, 3)]]
        stream.links = [[], [(0, 0, 1)]]
        row = torch.ones(3, 2, 24)
        row[1, 0, 0] = -1
        stream.tables = [None, (None, None, None, row)]
        stream.rd = SimpleNamespace(
            index=SimpleNamespace(
                encoder=lambda x: x[:, :24],
                rows={p: (None, None, [2, 2]) for role in stream.roles for p in role},
            )
        )
        stream.port_refs = lambda d: torch.tensor([[20, 2, 9]])

        def look(status, hash_i64):
            def compute(rule, atom, refs):
                self.assertEqual((rule, atom), (3, 2))
                self.assertEqual(refs.tolist(), [[[20, 2, 9, 1]]])
                return torch.tensor([[1, status, atom, hash_i64]])

            stream.transaction = SimpleNamespace(compute=compute)
            return torch.cat(
                [v for _, v in stream.children(torch.tensor([[0]]), 1, 1)]
            ).tolist()

        self.assertEqual(look(14, -1), [0, 2])  # most significant response bit is set
        self.assertEqual(look(14, 0), [1])
        self.assertEqual(look(1, 0), [0, 1, 2])
