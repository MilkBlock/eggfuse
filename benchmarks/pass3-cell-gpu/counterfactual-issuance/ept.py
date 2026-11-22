"""Score committed changes against the independent exact-run operation ledger."""
from collections import Counter
from hashlib import sha256
import json

KINDS = ("visible_birth", "effective_write", "effective_union", "visibility_change")


def ledger_digest(data):
    ledger = data["ept"]
    if len(ledger) != data["runs"] or len(ledger) != len(data["events"]):
        raise ValueError("incomplete EPT Run boundaries")
    h = sha256()
    for events, native in zip(ledger, data["events"]):
        # The ordinary auditor independently records the actual changes.
        expected = [(e[3], e[4]) for e in native if e[0]=="write" and e[6]!=e[7]]
        actual = [(e[2],e[3]) for e in events if e[0]==1]
        unions = [(e[1],e[2]) for e in native if e[0]=="union"]
        if expected!=actual or unions!=[(e[2],e[3]) for e in events if e[0]==2]:
            raise ValueError("EPT writes or unions disagree with ordinary audit")
        # Include full native write payloads, constructor identities and legal Run boundaries.
        payload=[events,[e for e in native if e[0] in ("write","birth","union")]]
        h.update(json.dumps(payload,separators=(",",":"),sort_keys=True).encode())
        h.update(b"\n")
    return h.hexdigest()


def determined(query, named):
    # A source address binds the whole typed row. Remaining functions and
    # constructors can be checked only at a completely determined input key.
    bound={a["slot"] for i in named for a in query[i]["args"] if "slot" in a}
    remaining=[atom for i,atom in enumerate(query) if i not in named]
    while remaining:
        ready=[a for a in remaining if all("literal" in v or v.get("slot") in bound
                                           for v in a["args"][:-1])]
        if not ready:return False
        for atom in ready:
            dst=atom["args"][-1]
            if "slot" in dst:bound.add(dst["slot"])
            remaining.remove(atom)
    return True


def score(data, recipe, paid, reference):
    digest=ledger_digest(data)
    if digest!=reference:raise ValueError("effective-operation ledger changed")
    roots=data["root_recipe"]
    strict=data["strict_named"] or {}
    commits=roots["commits"]
    ordinal={r[2]:r[0] for r in commits}
    parents={ordinal[serial]:ordinal[root] for serial,root,*_ in strict.get("signed_commits",[])}
    tail = roots.get("history_tail")
    children = [*(roots.get("pair_children") or []), *(tail[1] if tail else [])]
    points = roots.get("point_claims")
    if points:children.extend(points[1])
    for serial,root in children:
        child=ordinal[serial]
        if child in parents:raise ValueError("duplicate signed owner")
        parents[child]=root
    required=[{i for i,q in enumerate(r["query"]) if "table" in q["call"]} for r in recipe["rules"]]
    signed=set()
    decisions={}
    rule_for={}
    for row in commits:
        n,_,_,rid,_,_,refs,_=row
        rule_for[n]=rid
        if n in parents:
            if parents[n]>=n:raise ValueError("noncausal EPT owner")
            if parents[n] in signed:signed.add(n)
        else:
            named=frozenset(ref["atom"] for ref in refs)
            key=(rid,named)
            if key not in decisions:
                query=recipe["rules"][rid]["query"]
                decisions[key]=(bool(named) or not required[rid]) and determined(query,named)
            if decisions[key]:signed.add(n)
    totals=[Counter(),Counter()]
    per_rule=Counter()
    system_rule=Counter()
    unowned=Counter()
    for run in data["ept"]:
        for kind,n,*_ in run:
            if n is not None and n not in rule_for:raise ValueError("missing EPT ordinal")
            k=KINDS[kind]
            totals[int(n in signed)][k]+=1
            if n is None:unowned[k]+=1
            if n is not None:system_rule[rule_for[n],k]+=1
            if n in signed:per_rule[rule_for[n],k]+=1
    uncredited,credited=totals
    return dict(ledger_sha256=digest, paid=paid,
        signed={k:credited[k] for k in KINDS},uncredited={k:uncredited[k] for k in KINDS},
        ept=credited.total()/paid, system_ept=(credited.total()+uncredited.total())/paid,
        no_rhs_owner={k:unowned[k] for k in KINDS},
        unsupported_root={k:uncredited[k]-unowned[k] for k in KINDS},
        rule_breakdown={rid:dict(commits=sum(r[3]==rid for r in commits),
            signed={k:per_rule[rid,k] for k in KINDS},
            system={k:system_rule[rid,k] for k in KINDS}) for rid in (153,317)},
        rule_153_writes=[per_rule[153,"effective_write"],system_rule[153,"effective_write"]],
        rule_317_unions=[per_rule[317,"effective_union"],system_rule[317,"effective_union"]])
