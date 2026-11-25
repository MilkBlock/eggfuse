"""Replay one preselected high-EAR region through native layout feedback offline."""

from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

from receipt_bake import save
from receipt_takeover import replay_many
from recursive_train import binary, read
from structure_recipe import native_unit


def native_witness(e, data, event):
    n, k, branches, entry, token, ts, (_, plan) = event
    groups = defaultdict(list)
    for t in ts:
        groups[e.t.q[t]["run"]].append(e.t.q[t]["rule"])
    previous = None
    stages = {}
    for i, (run, rules) in enumerate(groups.items()):
        if previous is not None and e.next_group(previous, tuple(sorted(set(rules)))) != run:
            return {"status": "requires_independent_schedules", "entry": entry, "tokens": ts}
        stages[run] = i
        previous = run
    # Offline lowering only. Native layout-feedback attaches at the first
    # scheduled step; the tested online policy instead launches at publication.
    steps = [
        (e.t.q[t]["rule"], stages[e.t.q[t]["run"]], [(src, 0, pc) for src, pc in wires])
        for t, (_, wires) in zip(ts, plan, strict=True)
    ]
    with TemporaryDirectory() as tmp:
        p = Path(tmp) / "region.json"
        save(p, [native_unit(steps, ts, e.t)])
        try:
            result = replay_many(
                e.t.folder, binary(data), p, [(0, ts)], e.t.tape, read(e.t.folder / "capture.json")
            )
        except ValueError as ex:
            return {"status": "failed", "reason": str(ex)[:2000], "entry": entry, "tokens": ts}
    return {
        "status": "pass",
        "entry": entry,
        "first_run": min(groups),
        "last_run": max(groups),
        "evidence": token,
        "bindings": k,
        "teacher_effective_ops": n,
        "direct_branches": branches,
        "tokens": ts,
        "native": result,
    }
