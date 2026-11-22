"""Attribute externally issued root serials to actual committed source bindings."""
from collections import Counter


def rank(data, recipe):
    roots = data["root_recipe"]
    commits = {row[2]:row[3] for row in roots["commits"]}
    if len(commits) != len(roots["commits"]):
        raise ValueError("source commits share a packet serial")
    source = Counter(commits.values())
    paid, won = Counter(), Counter()
    end = 0
    for first, n, rid in roots["chain_audit"]["paid_ranges"]:
        if first <= end or n <= 0:
            raise ValueError("paid ranges overlap or are not chronological")
        end = first + n - 1
        paid[rid] += n
        for serial in range(first, end+1):
            if serial in commits:
                if commits[serial] != rid:
                    raise ValueError("root attributed to a different source rule")
                won[rid] += 1
    if sum(paid.values()) != sum(roots["emitted"]):
        raise ValueError("root accounting does not cover all paid emissions")
    rules = []
    for rid,n in paid.items():
        atoms = recipe["rules"][rid]["query"]
        rules.append(dict(rule=rid, paid=n, won=won[rid], uncommitted=n-won[rid], source=source[rid],
                          query=[a["call"].get("table") or a["call"].get("primitive") for a in atoms]))
    rules.sort(key=lambda r:(-r["uncommitted"],-r["won"],r["rule"]))
    return dict(roots=sum(paid.values()), committed_roots=sum(won.values()),
                selected_merge=sum(int(r["selected"]) for r in data["merge_child"]["issued"]),rules=rules)
