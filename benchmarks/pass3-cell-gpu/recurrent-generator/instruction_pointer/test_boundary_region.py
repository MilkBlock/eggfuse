import unittest
from types import SimpleNamespace

from boundary_region import ancestors, region
from boundary_study import entry_probe


def request(token, rule, run, refs):
    return dict(
        token=token,
        rule=rule,
        run=run,
        parents=[dict(address=dict(token=t, op=pc), version=v) for t, pc, v in refs],
    )


class BoundaryTests(unittest.TestCase):
    def test_same_run_siblings_and_named_versions(self):
        q = {
            1: request(1, 0, 1, [(-1, 0, 0)]),
            2: request(2, 0, 1, [(-1, 0, 0)]),
            3: request(3, 1, 4, [(1, 0, 1), (2, 0, 3)]),
        }
        atom = dict(call=dict(table="T"), args=[dict(slot=0)])
        t = SimpleNamespace(
            q=q,
            rules=SimpleNamespace(inputs=[[0], [0, 0]], rules=[dict(outputs={"0": {}})] * 2),
            program=dict(recipe=dict(rules=[dict(query=[atom]), dict(query=[atom, atom])])),
            snap=SimpleNamespace(version=lambda t, pc, run: 0 if t < 0 else 1),
        )
        r = region(t, [3], {1, 2})
        self.assertEqual(r["external"], [(-1, 0, 0)])
        self.assertEqual([s[1] for s in r["unit"]], [0, 0, 1])
        self.assertEqual(r["problems"], [[3, 1, "first_published_version_differs", [2, 0, 3]]])
        self.assertEqual(ancestors(q, 3), {1, 2, 3})

    def test_root_alone_is_insufficient_for_first_group(self):
        r = dict(unit=[(1, 0, [(-1, 0)]), (2, 0, [(-1, 1)])])
        row = entry_probe(r, dict(run=4), {}, [request(1, 1, 4, [])], {}, None, None, {}, None)
        self.assertEqual(row["status"], "no")
        self.assertEqual(row["rule"], 2)


if __name__ == "__main__":
    unittest.main()
