"""Validate saved two-Run predictions using their source program contract."""
import json
from pathlib import Path

import numpy as np

from .audit import audit
from .compiler import projection_recipe


def verify_crossrun(plan, a, b, requests, make, finish):
    """Audit decoded CPU records for the make/finish equivalence-join experiment.

    A/B columns store key and value. Request columns store the A id, B id and
    tag. Stage dictionaries contain active, pointers and fields. Every stage-2
    witness is checked against the actual active stage-1 slot it references.
    Single graphs and batches are accepted. Returns counts and per-graph results.
    """
    plan = plan if isinstance(plan, dict) else json.loads(Path(plan).read_text())
    routes = projection_recipe(plan)
    expected = (((0, 0), (1, 0), (0, 1), (0, 2), (1, 2)),
                ((0, 0), (0, 1), (1, 2), (0, 3), (0, 4)))
    if routes != expected:
        raise ValueError("This verifier requires the Pair(i,j,k,x,y), Result(i,j,t,x,y) routes")
    # Check the LHS too: the same RHS wiring can accompany a different join.
    checks = (("make", {frozenset((("A", 1), ("B", 1)))}),
              ("finish", {frozenset((("Pair", i), ("Request", i))) for i in (0, 1)}))
    for stage, required in checks:
        rule = plan["rules"][stage]
        actual = {frozenset((rule["inputs"][side], col) for side, col in equality)
                  for equality in rule["equalities"]}
        if actual != required:
            raise ValueError(f"Unsupported {stage} join predicates")
    a, b, requests = (np.asarray(x) for x in (a, b, requests))
    if a.ndim == 2:
        a, b, requests = a[None], b[None], requests[None]
    def batch(stage):
        arrays = {name: np.asarray(stage[name]) for name in ("active", "pointers", "fields")}
        if arrays["active"].ndim == 1:
            arrays = {name: value[None] for name, value in arrays.items()}
        return arrays
    return audit(a, b, requests, batch(make), batch(finish))
