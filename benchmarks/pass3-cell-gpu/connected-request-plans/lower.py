"""Find a connected independent-parent plan allowing compiler-determined requests between choices."""
from collections import deque


def slots(args):
    return frozenset(v["slot"] for v in args if "slot" in v)


def lower(rule):
    atoms = rule["query"]
    keys = [slots(a["args"][:-1]) for a in atoms]
    fields = [slots(a["args"]) for a in atoms]
    relations = [i for i, a in enumerate(atoms) if "table" in a["call"]]
    goal = frozenset().union(*fields)

    def closure(bound):
        while True:
            result = bound.union(*(f for k, f in zip(keys, fields) if k <= bound))
            if result == bound:
                return result
            bound = result

    first = closure(frozenset())
    queue = deque([(first, ())])
    seen = {first}
    while queue:
        bound, picks = queue.popleft()
        if bound == goal:
            return wire(atoms, keys, fields, picks)
        for i in relations:
            if fields[i] <= bound or (picks and not fields[i] & bound):
                continue
            extended = closure(bound | fields[i])
            if extended not in seen:
                seen.add(extended)
                queue.append((extended, picks + (i,)))
    return None


def wire(atoms, keys, fields, picks):
    # Derive just one connected key before each pick. Everything else, including
    # equality checks on already-bound results, remains a source obligation.
    done, bound, order = set(), set(), []
    for pos, parent in enumerate(picks):
        if pos and not fields[parent] & bound:
            derived = {s: () for s in bound}
            while True:
                changed = False
                for i in range(len(atoms)):
                    if i in done or i == parent or not keys[i] <= derived.keys():
                        continue
                    path = tuple(dict.fromkeys(j for s in sorted(keys[i]) for j in derived[s])) + (i,)
                    for s in fields[i]:
                        if s not in derived or (len(path), path) < (len(derived[s]), derived[s]):
                            derived[s] = path
                            changed = True
                if not changed:
                    break
            bridge = min((derived[s] for s in fields[parent] if s in derived), key=lambda p: (len(p), p))
            for i in bridge:
                if i not in done:
                    assert keys[i] <= bound and i not in picks
                    order.append(("request", i))
                    done.add(i)
                    bound.update(fields[i])
        assert not pos or fields[parent] & bound
        order.append(("pick", parent))
        done.add(parent)
        bound.update(fields[parent])
    while len(done) < len(atoms):
        i = next(i for i in range(len(atoms)) if i not in done and keys[i] <= bound)
        order.append(("suffix", i))
        done.add(i)
        bound.update(fields[i])
    return order


def validate(rule, order):
    bound, seen = set(), set()
    parents = 0
    for op, i in order:
        assert i not in seen
        seen.add(i)
        a = rule["query"][i]
        fields = slots(a["args"])
        if op == "pick":
            assert "table" in a["call"] and (parents == 0 or fields & bound)
            parents += 1
        else:
            assert slots(a["args"][:-1]) <= bound and op in ("request", "suffix")
        bound.update(fields)
    assert seen == set(range(len(rule["query"])))
    return parents
