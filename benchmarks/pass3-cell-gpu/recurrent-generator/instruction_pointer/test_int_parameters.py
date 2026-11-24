import unittest

import torch

from int_parameters import StructuralBake, link_layouts
from ripsat_layout import signatures
from semantic_catalog import SemanticActor, SemanticCatalog
from ripsat_policy import GraphBank

I64 = {"name": "i64", "kind": "i64"}


def lit(x):
    return {"literal": x, "sort": I64}


def example(p, q, address):
    def rule(amount, limit):
        return dict(metadata=dict(name=f"cost {amount} {limit}", source_set="terms", seminaive=True),
                    slots=[dict(name=f"tmp{amount}", sort=I64, definition="query")],
                    query=[dict(call={"table": "RipenInput_0_"}, args=[lit(address), {"slot": 0}]),
                           dict(call={"primitive": "<"}, args=[lit(amount), lit(limit)])],
                    effects=[dict(op="copy", kind="copy", arg=lit(amount), dst=0)])
    return dict(recipe=dict(rules=[rule(p, q), rule(q, p)],
                            tables=[dict(name="RipenInput_0_", kind="constructor", schema=[I64,I64])]),
                merge_programs=dict(programs=[]))


class IntegerParameters(unittest.TestCase):
    layout = ((0, 0, ((-1, 0),)), (1, 1, ((-1, 0),)))

    def test_payload_address_and_roundtrip(self):
        prog = example(1, 10**16, 1)
        shape = StructuralBake(prog)
        changed = StructuralBake(example(-9, 123, 55))
        self.assertEqual(shape.key(self.layout), changed.key(self.layout))
        steps, values, markers = shape.describe(self.layout)
        self.assertEqual(values, (("i64", 1), ("i64", 10**16)))
        self.assertEqual(markers, (("i64", 1),))
        self.assertEqual([s[3] for s in steps], [[0,1],[1,0]])
        self.assertNotEqual(shape.key(self.layout), StructuralBake(example(1,1,1)).key(self.layout))
        first = shape.rules[0].instantiate(changed.rules[0].values, changed.rules[0].markers)
        self.assertEqual(first[2:4], [example(-9,123,55)["recipe"]["rules"][0][k] for k in ("query","effects")])
        with self.assertRaises(ValueError):
            shape.rules[0].instantiate([("u64",1),("i64",2)], markers)

    def test_cross_step_alias_only_changes_structure(self):
        p = example(1, 2, 1)
        a = StructuralBake(p)
        p["recipe"]["rules"][1] = example(3, 4, 1)["recipe"]["rules"][0]
        b = StructuralBake(p)
        self.assertEqual(a.rules[1].key, b.rules[1].key)
        self.assertNotEqual(a.key(self.layout), b.key(self.layout))

    def test_runtime_link_uses_concrete_target_and_checks_aliases(self):
        donor = example(1, 2, 1)
        # Distinguish the second primitive structurally for unambiguous dispatch.
        donor["recipe"]["rules"][1]["metadata"]["source_set"] = "later"
        target = example(6, 8, 9)
        target["recipe"]["rules"][1]["metadata"]["source_set"] = "later"
        manifest = dict(signatures=signatures(donor), layouts=[self.layout],
                        **StructuralBake(donor).manifest([self.layout]))
        self.assertEqual(len(list(link_layouts(target, manifest))), 1)
        target["recipe"]["rules"][1] = example(7, 8, 9)["recipe"]["rules"][1]
        target["recipe"]["rules"][1]["metadata"]["source_set"] = "later"
        self.assertFalse(list(link_layouts(target, manifest)))
        target = example(6, 8, 9)
        target["recipe"]["rules"][1]["metadata"]["source_set"] = "later"
        target["recipe"]["rules"].append(target["recipe"]["rules"][0])
        self.assertFalse(list(link_layouts(target, manifest)))

    def test_actual_gnn_inputs_are_invariant(self):
        cats = [SemanticCatalog(example(*v), integer_parameters=True)
                for v in ((1, 10**16, 1), (7, 8, 8), (7, 7, 8))]
        actor = SemanticActor(sorted({k for cat in cats for factors in cat.factors for k in factors}))
        def batch(cat):
            bank = GraphBank([self.layout], cat, actor.template_graph(cat).detach())
            return bank.batch([0], "cpu")
        a,b,c = map(batch,cats)
        for left, right in zip(a,b):
            self.assertTrue(torch.equal(left,right))
        self.assertFalse(torch.equal(a[0],c[0]))
        self.assertFalse(cats[0].constants)
        # Preserve concrete historical model input when replaying old checkpoints.
        self.assertTrue(SemanticCatalog(example(1,2,1)).constants)
