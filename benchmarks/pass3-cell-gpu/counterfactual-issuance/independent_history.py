"""Measure independent named-parent availability without using target-rule citations."""
from collections import Counter, defaultdict
from itertools import combinations, groupby

from parent_projection import identity


def profile(data, recipe):
    roots = data["root_recipe"]
    returns = defaultdict(list)
    for ordinal, _, _, cell, op, version, _ in roots["pair_returns"]:
        returns[ordinal].append(("fact", cell, op, version))

    # Two distinct observers suffice to decide whether some earlier observer
    # differs from any one excluded target. Publish only at the end of an epoch.
    observed = defaultdict(set)
    counts = defaultdict(Counter)
    last = -1
    for epoch, rows in groupby(roots["commits"], key=lambda row: row[5]):
        if epoch < last:
            raise ValueError("out-of-order committed source epoch")
        last = epoch
        batch = list(rows)
        for _, _, _, rid, _, _, refs, _ in batch:
            atoms = tuple(ref["atom"] for ref in refs)
            if len(set(map(identity, refs))) < 2:
                continue
            if len(set(atoms)) != len(atoms):
                raise ValueError("duplicate source query atom")
            row = counts[rid, tuple(sorted(atoms))]
            available = sum(any(owner != rid for owner in observed.get(identity(ref), ())) for ref in refs)
            row["all" if available == len(refs) else "some" if available else "none"] += 1
        for ordinal, _, _, rid, _, _, refs, _ in batch:
            for port in [*map(identity, refs), *returns.get(ordinal, ())]:
                providers = observed[port]
                if len(providers) < 2:
                    providers.add(rid)

    result = []
    for (rid, atoms), categories in counts.items():
        query = recipe["rules"][rid]["query"]
        slots = [{arg["slot"] for arg in query[i]["args"] if "slot" in arg} for i in atoms]
        edges = [[a, b, sorted(slots[a] & slots[b])] for a, b in combinations(range(len(atoms)), 2)
                 if slots[a] & slots[b]]
        result.append(dict(rule=rid, atoms=atoms, tables=[query[i]["call"].get("table") for i in atoms],
                           edges=edges, **categories))
    return sorted(result, key=lambda row: -row.get("all", 0))


def export_chains(data, recipe, path):
    """Export actual signed inputs and constructor returns, withholding the target."""
    import json
    rules = recipe["rules"]
    roots = data["root_recipe"]
    result = {}
    for target in (312, 538):
        query = rules[target]["query"]
        layout = [[arg["slot"] for arg in atom["args"]] for atom in query]
        tables = [atom["call"]["table"] for atom in query]
        if len(set(tables)) != 3:
            raise ValueError("expected three distinct relation roles")
        sources = {(rid, i): (tables.index(atom["call"]["table"]), atom["args"])
                   for rid, rule in enumerate(rules) if rid != target
                   for i, atom in enumerate(rule["query"]) if atom["call"].get("table") in tables}
        events, labels = [], []
        count = 0
        for ordinal, _, _, rid, _, epoch, refs, slots in roots["commits"]:
            if rid == target:
                count += 1
                if sorted(ref["atom"] for ref in refs) == [0, 1, 2]:
                    labels.append([epoch, [identity(ref) for ref in sorted(refs, key=lambda ref:ref["atom"])]])
                continue
            for ref in refs:
                source = sources.get((rid, ref["atom"]))
                if source is None:
                    continue
                role, args = source
                fields = [slots.get(str(a["slot"])) if "slot" in a else a.get("literal") for a in args]
                address = identity(ref)
                events.append([epoch, role, address, ordinal, ~ref["atom"], fields])
        returns = []
        for owner, rid, epoch, table, op, cell, field, version, fields in roots.get("chain_rows") or ():
            name = recipe["tables"][table]["name"]
            if rid == target or name not in tables:
                continue
            role = tables.index(name)
            effect = rules[rid]["effects"][op]
            if effect["call"].get("table") != name or len(fields) != len(layout[role]):
                raise ValueError("typed return disagrees with source operation")
            returns.append([epoch, role, ("fact",cell,field,version), owner, op, fields])
        writes, updates = [], []
        by_owner = {c[0]: (c[3],c[5]) for c in roots["commits"]}
        for owner,rid,epoch,table,op,index,version,fields in roots.get("chain_audit",{}).get("writes") or ():
            name = recipe["tables"][table]["name"]
            if rid == target or name not in tables:
                continue
            role = tables.index(name)
            if (by_owner.get(owner) != (rid,epoch) or rules[rid]["effects"][op]["call"].get("table") != name
                    or len(fields) != len(layout[role]) or version > epoch):
                raise ValueError("function receipt does not belong to its named writer")
            writes.append([epoch,role,("function",index,version),owner,op,fields])

        # An update extends only a version already associated with this very
        # owner port. Native emission checks liveness at the publication hook.
        evidence = {}
        for epoch,role,addr,owner,slot,_ in [*events,*returns,*writes]:
            k = role,tuple(addr),owner,slot
            evidence[k] = min(evidence.get(k,epoch),epoch)
        for epoch,table,dep,owner,slot,old,new,fields in roots.get("chain_audit",{}).get("updates") or ():
            name = recipe["tables"][table]["name"]
            if name not in tables:
                continue
            role = tables.index(name)
            prior = identity(dict(row=dep,version=old))
            if evidence.get((role,prior,owner,slot),epoch+1) > epoch:
                raise ValueError("publication lacks earlier named owner and revision")
            if new is None:
                updates.append([epoch,role,prior,owner,slot,None])
                continue
            if not old < new <= epoch or len(fields) != len(layout[role]):
                raise ValueError("invalid published revision")
            addr = (*prior[:-1],new)
            evidence[role,addr,owner,slot] = min(evidence.get((role,addr,owner,slot),epoch),epoch)
            updates.append([epoch,role,addr,owner,slot,fields])
        result[target] = dict(layout=layout,tables=tables,events=events,returns=returns,
                              writes=writes,updates=updates,labels=labels,source=count)
    path.write_text(json.dumps(result, separators=(",", ":")))


def check_packets(data, proposals):
    roots = data["root_recipe"]
    if roots.get("chain_audit",{}).get("checked") is None:
        raise ValueError("missing native scheduled checks")
    result = {}
    for key, packets in proposals.items():
        rid = int(key)
        def triple(refs):
            return tuple(identity(dict(row=dep,version=ver)) for dep,ver in refs)
        all_packets = {triple(p["refs"]):p["birth"] for p in packets}
        if len(all_packets) != len(packets):
            raise ValueError("duplicate three-parent packet")
        source = {(epoch,tuple(identity(r) for r in sorted(refs,key=lambda r:r['atom'])))
                  for _,_,_,rule,_,epoch,refs,_ in roots['commits'] if rule==rid}
        seen, accepted = set(), set()
        reads = stale = expired = withheld = 0
        for rule,epoch,birth,refs,mark,fresh,valid,n,*release in roots['chain_audit']['checked']:
            if rule != rid:
                continue
            ports = triple(refs)
            if ports in seen or all_packets.get(ports) != birth or birth >= epoch:
                raise ValueError("packet release disagrees with causal issue")
            seen.add(ports)
            reads += n
            if release == [False]:
                withheld += 1
                continue
            if valid:
                accepted.add((epoch,ports))
            elif fresh:
                expired += 1
            else:
                stale += 1
        result[key] = dict(proposed=len(packets), checked=len(seen)-withheld, pending=len(packets)-len(seen),
                           source=len(source), matches=len(source & accepted), missing=len(source-accepted),
                           non_source=len(accepted-source), version_or_binding_rejections=expired,
                           watermark_rejections=stale, direct_reads=reads, withheld=withheld, released=len(seen)-withheld)
    return result
