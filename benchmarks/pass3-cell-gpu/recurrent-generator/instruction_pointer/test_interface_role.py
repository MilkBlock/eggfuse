import unittest
from types import SimpleNamespace

import torch

from actor import InstructionActor
from interface_role_model import RoleRead, layouts, operand_contract
from operand_read_model import words


class TestInterfaceRole(unittest.TestCase):
    def test_provenance_through_named_projection(self):
        input_rule = {
            "query": [
                {"call": {"table": "Seed"}, "args": [{"slot": i} for i in range(4)]}
            ],
            "effects": [
                {"op": "copy", "dst": 4, "arg": {"slot": 2}},
                {
                    "op": "let",
                    "kind": "construct",
                    "call": {"table": "Mid"},
                    "args": [{"slot": 4}, {"slot": 0}],
                },
            ],
        }
        mid = {
            "query": [
                {
                    "call": {"table": "Mid"},
                    "args": [{"slot": 0}, {"slot": 0}, {"slot": 1}],
                }
            ],
            "effects": [],
        }
        w = SimpleNamespace(
            prog={"recipe": {"rules": [input_rule, mid]}},
            contract={
                "rules": [
                    {"outputs": {"8": {"effect": 1, "producer": "effect", "table": 0}}},
                    {"outputs": {}},
                ]
            },
            tabs=["Mid"],
        )
        valid = [(0, 0, [(-1, 0)]), (1, 1, [(0, 8)])]
        self.assertEqual(operand_contract(w, valid), (2, 0))
        self.assertEqual(operand_contract(w, [valid[0], (1, 1, [(0, 1)])]), (-1, -1))
        input_rule["effects"][0] = {"op": "let", "kind": "compute", "dst": 4}
        self.assertEqual(operand_contract(w, valid), (-1, -1))

    def test_physical_permutations_and_learned_read(self):
        for width in (3, 4, 6):
            train, held = layouts(width)
            self.assertFalse(set(train) & set(held))
            for p in train + held:
                self.assertEqual(set(p), set(range(width)))
        net = RoleRead.__new__(RoleRead)
        torch.nn.Module.__init__(net)
        torch.manual_seed(20)
        net.actor = InstructionActor()
        net.arm_name = "C"
        net.audit = True
        net.hard = False
        net.type_codes = torch.randn(2, 32)
        net.entry_tables = [0, 1]
        net.port_types = net.type_codes
        net.descriptors = torch.randn(2, 2, 32)
        net.columns = torch.tensor([[0, 1], [1, 2]])
        fields, roles = words([(22, 11, 22, 5), (9, 2, 2)])
        valid = torch.tensor([[True] * 4, [True] * 3 + [False]])
        q = torch.randn(2, 2, 32, requires_grad=True)
        net.physical = ("train", 0)
        a = net.payload(q, fields, roles, valid, [0, 1])
        for layout in (("held", 0), ("held", 1)):
            net.physical = layout
            b = net.payload(q, fields, roles, valid, [0, 1])
            torch.testing.assert_close(a, b, atol=2e-6, rtol=1e-5)
        loss = b.square().sum()
        for t in (
            *net.role_trace[:4],
            net.actor.query.weight,
            net.actor.input_role.weight,
        ):
            self.assertGreater(
                float(torch.autograd.grad(loss, t, retain_graph=True)[0].norm()), 0
            )
