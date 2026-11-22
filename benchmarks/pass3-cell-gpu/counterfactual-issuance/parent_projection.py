"""Measure which external multi-parent commits could draw witnesses from one producer."""
from collections import Counter


def identity(ref):
    row = ref["row"]
    if "Fact" in row:
        fact = row["Fact"]
        return ("fact", fact["cell"], fact["op"], ref["version"])
    return ("function", row["Function"], ref["version"])


def projection_profile(data):
    roots = data["root_recipe"]
    internal = {serial for serial, *_ in data["strict_named"]["signed_commits"]}
    allocations = {cell: ordinal for cell, ordinal, *_ in roots["fresh"]}
    sources = {}
    totals = Counter()
    families = Counter()
    gaps = Counter()
    for ordinal, _, serial, rule, _, _, refs, _ in roots["commits"]:
        parents = frozenset(map(identity, refs))
        if len(parents) >= 2 and serial not in internal:
            totals["external_multi_parent_commits"] += 1
            owners = {allocations[p[1]] for p in parents
                      if p[0] == "fact" and p[1] in allocations}
            options = []
            least_missing = len(parents)
            for owner in sorted(owners):
                if owner not in sources:
                    continue
                producer, inherited = sources[owner]
                missing = sum(p not in inherited and
                              (p[0] != "fact" or allocations.get(p[1]) != owner)
                              for p in parents)
                least_missing = min(least_missing, missing)
                if missing == 0:
                    options.append(producer)
            gaps[len(parents), least_missing] += 1
            if options:
                totals["one_prior_frame_covers_addresses"] += 1
                # Count the consumer once even if several owners are eligible.
                families[(rule, tuple(sorted(set(options))))] += 1
        sources[ordinal] = (rule, parents)
    return dict(totals=totals, missing_by_arity=[
        dict(arity=arity, missing=missing, count=count)
        for (arity, missing), count in sorted(gaps.items())
    ], families=[
        dict(consumer=rule, producers=options, count=count)
        for (rule, options), count in families.most_common()
    ])


def prior_port_coverage(data, targets):
    """Measure address observability before each target Run, independent of its labels."""
    from itertools import groupby

    roots = data["root_recipe"]
    returns = {}
    for ordinal, _, effect, cell, op, version, _ in roots["pair_returns"]:
        returns.setdefault(ordinal, []).append((effect, ("fact", cell, op, version)))
    counts = {rule: Counter() for rule in targets}
    exported = {}
    cited = set()
    previous_epoch = None
    for epoch, commits in groupby(roots["commits"], key=lambda row: row[5]):
        if previous_epoch is not None and epoch < previous_epoch:
            raise ValueError("source epoch regressed")
        previous_epoch = epoch
        batch = list(commits)
        # Score first. No RHS in this batch can inform this batch's query.
        for _, _, _, rule, _, _, refs, _ in batch:
            if rule not in counts:
                continue
            ordered = sorted(refs, key=lambda ref: ref["atom"])
            if [ref["atom"] for ref in ordered] != [0, 1]:
                counts[rule]["without_two_named_inputs"] += 1
                continue
            left, right = map(identity, ordered)
            if left in exported and right in exported:
                category = ("shared_return_frame" if exported[left] & exported[right]
                            else "separate_return_frames")
            elif all(port in exported or port in cited for port in (left, right)):
                category = "requires_prior_input_citation"
            else:
                category = "missing_from_traced_history"
            counts[rule][category] += 1
        for ordinal, _, _, _, _, _, refs, _ in batch:
            cited.update(map(identity, refs))
            for _, address in returns.get(ordinal, ()):
                exported.setdefault(address, set()).add(ordinal)
    return {rule: dict(row) for rule, row in counts.items() if row}
