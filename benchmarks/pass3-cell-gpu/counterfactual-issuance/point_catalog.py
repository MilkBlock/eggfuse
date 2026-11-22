"""Rank one-return continuations with no independent operand left to discover."""
from collections import Counter, defaultdict
from itertools import groupby

from ept import determined
from parent_projection import identity


def rank(data, recipe):
    roots = data["root_recipe"]
    signed = {row[0] for row in data["strict_named"]["signed_commits"]}
    signed.update(row[0] for row in roots["pair_children"] or ())
    signed.update(row[0] for row in (roots.get("history_tail") or (0, []))[1])
    eligible = {}
    for rid, rule in enumerate(recipe["rules"]):
        query = rule["query"]
        if rule["metadata"]["seminaive"] and len(query) >= 2:
            for pivot, atom in enumerate(query):
                if "table" in atom["call"] and determined(query, {pivot}):
                    eligible[rid, pivot] = atom["call"]["table"]
    returned = defaultdict(list)
    for owner, rid, op, cell, field, version, _ in roots["pair_returns"]:
        effect = recipe["rules"][rid]["effects"][op]
        if effect.get("kind") == "construct":
            returned[owner].append((op, effect["call"]["table"], ("fact",cell,field,version)))
    latest = {}
    hits = Counter()
    for _, batch in groupby(roots["commits"], key=lambda row:row[5]):
        batch = list(batch)
        for _, _, serial, rid, _, _, refs, _ in batch:
            if serial in signed or len(refs) != 1:
                continue
            pivot = refs[0]["atom"]
            table = eligible.get((rid,pivot))
            producer = latest.get((table, identity(refs[0])))
            if producer is not None:
                hits[(*producer,rid,pivot)] += 1
        for owner, _, serial, rid, _, _, refs, _ in batch:
            if serial in signed or not refs:
                continue
            for op, table, port in returned.get(owner, ()):
                latest[table,port] = rid,op
    return [dict(producer=p,operation=op,consumer=c,pivot=i,commits=n)
            for (p,op,c,i),n in hits.most_common()]


def point_consumers(recipe, family):
    """Use a returned constructor's first slot as the entire suffix key."""
    constructors = {table["name"] for table in recipe["tables"] if table["kind"] == "constructor"}
    result = []
    for rid, rule in enumerate(recipe["rules"]):
        query = rule["query"]
        if len(query) != 2 or not rule["metadata"]["seminaive"]:
            continue
        for pivot, source in enumerate(query):
            table = source["call"].get("table")
            suffix = query[1-pivot]
            other = suffix["call"].get("table")
            if (table not in constructors or not other or len(suffix["args"]) != 2
                    or "slot" not in source["args"][0] or source["args"][0] != suffix["args"][0]):
                continue
            if family != "all" and table not in ("Get","Single"):
                continue
            if family == "size" and other != "Expr-size":
                continue
            result.append((rid,pivot))
    return result


def validate(data, recipe, consumers):
    roots = data["root_recipe"]
    attempts, children, misses = roots["point_claims"]
    by_serial = {row[2]:row for row in roots["commits"]}
    by_owner = {row[0]:row for row in roots["commits"]}
    ports = set()
    for owner,rule,op,cell,field,version,_ in roots["pair_returns"]:
        effect = recipe["rules"][rule]["effects"][op]
        if effect.get("kind")=="construct":
            ports.add((owner,effect["call"]["table"],(cell,field,version)))
    pivots = dict(consumers)
    committed = set()
    claimed = {}
    for row in roots["commits"]:
        if row[3] in pivots:
            if [r["atom"] for r in row[6]] != [pivots[row[3]]]:
                raise ValueError("unexpected source pivot")
            committed.add((row[3],row[5],identity(row[6][0])[1:]))

    def check(owner,rid,epoch,port):
        parent = by_owner[owner]
        table = recipe["rules"][rid]["query"][pivots[rid]]["call"]["table"]
        if parent[5]>=epoch or not parent[6] or (owner,table,port) not in ports:
            raise ValueError("no earlier signed versioned output")

    success = Counter()
    owner_epochs = defaultdict(set)
    producer_counts = Counter()
    for serial,owner in children:
        row = by_serial[serial]
        check(owner,row[3],row[5],identity(row[6][0])[1:])
        if row[0] in claimed:
            raise ValueError("more than one owner credited")
        claimed[row[0]] = row[3]
        success[row[3]] += 1
        owner_epochs[owner].add(row[5])
        producer_counts[by_owner[owner][3]]+=1
    failed = set()
    for rid,epoch,port,owner in misses:
        key = rid,epoch,tuple(port)
        check(owner,*key)
        if key in failed or key in committed:
            raise ValueError("invalid failed point continuation")
        failed.add(key)
    from ept import KINDS
    effective = defaultdict(Counter)
    for batch in data["ept"]:
        for kind,ordinal,*_ in batch:
            if ordinal in claimed:
                effective[claimed[ordinal]][KINDS[kind]]+=1
    return dict(owners=len(owner_epochs), owners_used_across_epochs=sum(len(v)>1 for v in owner_epochs.values()),
                producer_counts=dict(producer_counts),attempts=attempts, union_probes=roots.get("point_union_probes"), rekeyed_entries=roots.get("point_rekeyed"), skipped=roots.get("point_skips",{}), committed=success, misses=len(failed),effective=dict(effective))
