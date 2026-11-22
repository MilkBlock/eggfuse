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
    """Select wired constructor pivots whose suffix inputs are all known."""
    constructors = {table["name"] for table in recipe["tables"] if table["kind"] == "constructor"}
    result = []
    for rid, rule in enumerate(recipe["rules"]):
        query = rule["query"]
        if family in ("chain", "scalar-chain"):
            tables = sum("table" in q["call"] for q in query)
            if not rule["metadata"]["seminaive"] or len(query) < 2 or (tables < 2 and family == "chain"):
                continue
            for pivot, source in enumerate(query):
                if source["call"].get("table") in constructors and determined(query, {pivot}):
                    result.append((rid, pivot))
            continue
        if len(query) != 2 or not rule["metadata"]["seminaive"]:
            continue
        for pivot, source in enumerate(query):
            table = source["call"].get("table")
            suffix = query[1-pivot]
            other = suffix["call"].get("table")
            if family == "determined":
                if table in constructors and other and suffix["args"] and all(
                    "literal" in key or key in source["args"] for key in suffix["args"][:-1]
                ):
                    result.append((rid, pivot))
                continue
            if (table not in constructors or not other or len(suffix["args"]) != 2
                    or "slot" not in source["args"][0] or source["args"][0] != suffix["args"][0]):
                continue
            if family != "all" and table not in ("Get","Single"):
                continue
            if family == "size" and other != "Expr-size":
                continue
            result.append((rid,pivot))
    return result


def strict_ordinals(data):
    """Identify legacy signed commits by source ordinal across distinct issuers."""
    serials = {r[2]: (r[0], r[3]) for r in data["root_recipe"]["commits"]}
    links = data["strict_named"]["signed_commits"]
    found = {serials[serial] for serial, *_ in links}
    if len(found) != len(links):
        raise ValueError("duplicate signed source ordinal")
    return found


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
    point_serials = {serial for serial, _ in children}
    downstream = Counter(len(path) for _, root, path, _, _ in data["strict_named"]["signed_commits"]
                         if root in point_serials)
    return dict(signed_descendants_by_depth=dict(downstream), batch_gate=roots.get("point_batch_gate"), stale_omissions=roots.get("point_stale_omissions"), owners=len(owner_epochs), owners_used_across_epochs=sum(len(v)>1 for v in owner_epochs.values()),
                producer_counts=dict(producer_counts),attempts=attempts, union_probes=roots.get("point_union_probes"), rekeyed_entries=roots.get("point_rekeyed"), skipped=roots.get("point_skips",{}), committed=success, misses=len(failed),
                misses_by_rule=dict(Counter(rid for rid, _, _ in failed)),effective=dict(effective))


def compare_families(run, request, recipe, control, reference, packets, family):
    from time import perf_counter
    from ept import score

    head = request["history_head"]
    spec = head["point_claims"]
    old = set(point_consumers(recipe, "determined" if family == "chain" else "all"))
    old_consumers = [entry for entry in spec["consumers"] if tuple(entry) in old]
    if family == "chain":
        arms = {"projected":dict(spec, consumers=old_consumers, compose_paths=False, batch_gate=False),
                "chain":spec}
        if spec.get("project_later"):
            arms["table_bounds"] = dict(spec, project_later=False)
        else:
            arms["chain_unbatched"] = dict(spec, batch_gate=False)
    else:
        arms = {"projected":spec, "first_field":dict(spec, consumers=old_consumers, own_stale=False)}
    stats = {name: dict(native_ms=[], request_ms=[]) for name in arms}
    names = list(arms)
    for turn in range(3 if family == "chain" else 4):
        for name in names[turn % len(names):] + names[:turn % len(names)]:
            config = dict(head, point_claims=arms[name])
            start = perf_counter()
            data = run(dict(request, history_head=config))
            duration = 1000 * (perf_counter() - start)
            for field in ("rhs", "writes", "resumes", "events", "runs", "schedule", "state_sha"):
                if data.get(field) != control[field]:
                    raise ValueError((name, field))
            root = data["root_recipe"]
            for field in ("history_online", "history_suppressed", "history_access"):
                if root[field] != control["root_recipe"][field]:
                    raise ValueError((name, field))
            checks, pending = root["history_online"]
            paid = packets(data) + sum(not valid for _, _, valid in checks) + len(pending)
            ledger = score(data, recipe, paid, reference)
            counts = dict(paid=paid, signed=ledger["signed"], ept=ledger["ept"],
                          receiver_table_lookups=data["single"]["work"][3],
                          point_attempts=sum(root["point_claims"][0].values()))
            row = stats[name]
            if "counts" in row and row["counts"] != counts:
                raise ValueError("unstable family counters")
            row["counts"] = counts
            row["native_ms"].append(data["ms"])
            row["request_ms"].append(duration)
            del data
    return stats


def audit_stale_proof(run, request, treatment):
    """Clear the freshness filter and explicitly check every signed continuation."""
    head = request["history_head"]
    options = dict(head["point_claims"], gate=None, own_stale=False)
    exact = run(dict(request, history_head=dict(head, point_claims=options)))
    if exact.get("source_error"):
        raise ValueError(exact["source_error"])
    for field in ("rhs", "writes", "resumes", "events", "schedule", "runs", "state_sha", "ept"):
        if exact[field] != treatment[field]:
            raise ValueError(("ungated reference changed", field))
    a = exact["root_recipe"]
    b = treatment["root_recipe"]
    for field in ("commits", "emitted", "history_online", "history_suppressed"):
        if a[field] != b[field]:
            raise ValueError(("stale proof changed issuance or commits", field))
    attempts, children, misses = a["point_claims"]
    reduced, signed, omitted = b["point_claims"]
    if children != signed or misses != omitted:
        raise ValueError("stale proof changed a signed child or a paid rejection receipt")
    return dict(exact_checks=sum(attempts.values()), gated_checks=sum(reduced.values()),
                matched_children=len(signed), matched_rejections=len(omitted),
                direct_stale_rejections=b["point_stale_omissions"])
