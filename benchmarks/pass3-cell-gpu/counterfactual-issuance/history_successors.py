"""Measure the boundary of a continuation from an actual rule-518 result."""
from collections import Counter, defaultdict
from itertools import groupby

from parent_projection import identity


def profile(data, target, acceptances, receipts):
    roots = data["root_recipe"]
    internal = {r[0] for r in data["strict_named"]["signed_commits"]}
    internal.update(r[0] for r in roots["pair_children"] or [])
    first_seen = {}
    for epoch, _, _, role, cell, op, version, _ in receipts:
        key = "fact", cell, op, version
        first_seen[key] = min(epoch, first_seen.get(key, epoch))
    outputs = defaultdict(list)
    for epoch, owner, slot, role, cell, op, version, _ in roots["history_returns"]:
        if role == 1:
            outputs[owner].append(("fact",cell,op,version))
    producers = defaultdict(list)
    families = defaultdict(Counter)
    for epoch, batch in groupby(roots["commits"], key=lambda r:r[5]):
        batch = list(batch)
        for _, _, serial, consumer, _, _, refs, _ in batch:
            parents = {identity(ref) for ref in refs}
            options = []
            for p in parents:
                for source_epoch, inherited in producers.get(p, ()):
                    missing = parents - inherited - {p}
                    if not missing:
                        options.append(0)
                    elif all(first_seen.get(k, source_epoch) < source_epoch for k in missing):
                        options.append(1)
                    else:
                        options.append(2)
            if options:
                credit = ("wired","extra_preexisting","extra_unobserved")[min(options)]
                if serial in internal:
                    credit = "already_internal"
                families[consumer][credit] += 1
        for owner, _, _, rule, _, _, refs, _ in batch:
            if rule != target:
                continue
            pair = tuple(identity(r) for r in sorted(refs,key=lambda r:r["atom"]))
            if (epoch,tuple(p[1:] for p in pair)) not in acceptances:
                continue
            for port in set(outputs[owner]):
                producers[port].append((epoch, frozenset(pair)))
    return {str(rule):dict(v) for rule,v in sorted(families.items())}


def validate_tail(data, root, tail, max_depth):
    roots = data["root_recipe"]
    attempts, children = roots["history_tail"]
    by_serial = {r[2]: r for r in roots["commits"]}
    by_ordinal = {r[0]: r for r in roots["commits"]}
    outputs = {(o,(cell,op,v)) for _,o,_,role,cell,op,v,_ in roots["history_returns"] if role == 1}
    depths = {}
    for serial, owner in sorted(children,key=lambda entry:by_serial[entry[0]][0]):
        child = by_serial[serial]
        parent = by_ordinal[owner]
        depth = 1 if parent[3]==root else depths.get(owner,max_depth)+1
        if (child[0] in depths or depth>max_depth or child[3] != tail or parent[5] >= child[5]
                or [p["atom"] for p in child[6]] != [1] or
                (owner,identity(child[6][0])[1:]) not in outputs):
            raise ValueError("invalid signed successor")
        depths[child[0]] = depth
    omitted = roots.get("history_tail_misses") or []
    target_commits={(r[5],identity(r[6][0])[1:]) for r in roots["commits"] if r[3]==tail}
    seen_misses=set()
    for epoch, port, owner in omitted:
        key=epoch,tuple(port)
        if (key in seen_misses or key in target_commits or (owner,tuple(port)) not in outputs
                or by_ordinal[owner][5]>=epoch
                or (by_ordinal[owner][3]!=root and owner not in depths)):
            raise ValueError("invalid discharge of failed signed successor")
        seen_misses.add(key)
    from ept import KINDS
    effective = Counter()
    changed = set()
    for events in data["ept"]:
        for kind, ordinal, *_ in events:
            if ordinal in depths:
                effective[KINDS[kind]] += 1
                changed.add(ordinal)
    return dict(
        omitted_paid_misses=len(omitted),
        scale=roots.get("history_scale"),
        attempted=attempts,
        committed=len(depths),
        by_depth=dict(Counter(depths.values())),
        children_changing_state=len(changed),
        child_effective_ops={k:effective[k] for k in KINDS},
    )
