import json
from pathlib import Path
import tempfile
import unittest

from ripsat_view.egraph import layout_graph, snapshot_graph


class StructuralIntegers(unittest.TestCase):
    def test_snapshot_marker_indices_do_not_alias_program_parameters(self):
        def graph(index, cost):
            state = dict(values=[dict(sort="i64", literal=str(n)) for n in (index, cost)] +
                                [dict(sort="Expr", literal=None)],
                         rows=[dict(op="RipenInput_5_",args=[0],result=2),
                               dict(op="Cost",args=[2,1,1],result=1)])
            with tempfile.TemporaryDirectory() as d:
                p = Path(d)/"snapshot.json"
                p.write_text(json.dumps(state))
                return snapshot_graph(p)
        g = graph(94,785)
        self.assertEqual(g.dot(), graph(25,9812).dot())
        self.assertEqual(g.nodes,[("IntParam", (), 0, False), ("RipenInput", (), 1, True),
                                  ("Cost", (1,0,0), 0, False)])

    def test_layout_parameter_sharing(self):
        def graph(values):
            sort = {"name":"i64"}
            args = [dict(literal=n,sort=sort) for n in values] + [{"slot":0}]
            rule = dict(slots=[dict(sort=sort)],query=[dict(call={"primitive":"+"},args=args)],effects=[])
            return layout_graph([(0,0,[])],[rule],set()).dot()
        self.assertEqual(graph([17,38]), graph([62,4096]))
        self.assertNotEqual(graph([17,17]),graph([17,38]))
