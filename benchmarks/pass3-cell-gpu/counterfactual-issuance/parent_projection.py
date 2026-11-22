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
