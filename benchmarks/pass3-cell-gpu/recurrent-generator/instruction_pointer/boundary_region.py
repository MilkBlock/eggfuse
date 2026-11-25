"""Concrete backward slices of signed, versioned teacher edges. Evaluation-only layouts."""

from entry_closure import named


def ancestors(qmap, owner):
    seen = set()
    work = [owner]
    while work:
        k = work.pop()
        if k in seen or k not in qmap:
            continue
        seen.add(k)
        work.extend(named(p)[0] for p in qmap[k]["parents"])
    return seen


def cuts(tape, chain):
    left, right = [named(p)[0] for p in tape.q[chain[0]]["parents"]]
    a, b = ancestors(tape.q, left), ancestors(tape.q, right)
    bootstrap = {k for k in a | b if tape.q[k]["run"] == 1}
    # Retain the already accepted initialization receipt as an earlier cut too.
    return dict(
        original=set(),
        left_parent={left},
        right_parent={right},
        both_parents={left, right},
        left_ancestry=a,
        right_ancestry=b,
        both_ancestries=a | b,
        after_init=(a | b) - bootstrap,
    )


def region(t, chain, absorbed):
    tokens = sorted(set(chain) | absorbed, key=lambda k: (t.q[k]["run"], k))
    pos = {k: i for i, k in enumerate(tokens)}
    stages = sorted({t.q[k]["run"] for k in tokens})
    groups = {r: i for i, r in enumerate(stages)}
    external = {}
    types = []
    unit = []
    problems = []
    uses = []
    for k in tokens:
        q = t.q[k]
        rid = q["rule"]
        op = t.program["recipe"]["rules"][rid]
        atoms = [a for a in op["query"] if "table" in a["call"]]
        wires = []
        for i, p in enumerate(q["parents"]):
            src, pc, v = ref = named(p)
            if src in pos:
                wire = (pos[src], pc)
                if str(pc) not in t.rules.rules[t.q[src]["rule"]]["outputs"]:
                    problems.append([k, i, "undeclared_output", list(ref)])
                if t.q[src]["run"] >= q["run"]:
                    problems.append([k, i, "unsealed", list(ref)])
                if t.snap.version(src, pc, t.q[src]["run"] + 1) != v:
                    problems.append([k, i, "first_published_version_differs", list(ref)])
            else:
                if ref not in external:
                    external[ref] = len(external)
                    types.append(t.rules.inputs[rid][i])
                wire = (-1, external[ref])
            wires.append(wire)
            uses.append([pos[k], i, wire, atoms[i]["call"]["table"], atoms[i]["args"]])
        unit.append((rid, groups[q["run"]], wires))
    late = [ref for ref in external if t.snap.version(*ref[:2], stages[0]) != ref[2]]
    return dict(
        tokens=tokens,
        unit=unit,
        external=list(external),
        types=types,
        runs=stages,
        late=late,
        problems=problems,
        uses=uses,
    )
