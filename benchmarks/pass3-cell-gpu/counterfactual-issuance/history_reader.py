"""Shadow rule-518 issuer. Reads constructor returns and earlier named inputs."""
from collections import Counter
from heapq import merge
from itertools import groupby

import torch


def fit_cutoff(hard, seed=518):
    # Random pairs of 64 bits have Binomial(64, .5) mismatches. Train the
    # same affine pointer head on that distribution or with near misses.
    rng = torch.Generator().manual_seed(seed)
    mismatches = torch.randint(2, (512, 64), generator=rng).sum(1).float()
    if hard:
        mismatches[:256] = torch.randint(1, 5, (256,), generator=rng)
    x = torch.cat([torch.zeros_like(mismatches), mismatches])
    y = (x == 0).float()
    head = torch.nn.Linear(1, 1)
    with torch.no_grad():
        head.weight.fill_(-.1)
        head.bias.zero_()
    opt = torch.optim.Adam(head.parameters(), lr=.05)
    for _ in range(350):
        opt.zero_grad()
        torch.nn.functional.binary_cross_entropy_with_logits(head(x[:, None]).flatten(), y).backward()
        opt.step()
    weight, bias = head.weight.item(), head.bias.item()
    accepted = [i for i in range(65) if i * weight + bias >= 0]
    assert weight < 0 and accepted
    return dict(weight=weight, bias=bias, max_distance=max(accepted))


def issue(receipts, model, budget=8, keep_history=True):
    # Histories use exact stable physical reference + version for identity;
    # the model keys come only from the subject carried in each return.
    banks = [{}, {}]
    proposals = {}
    comparisons = 0
    stale_key = 0
    for epoch, batch in groupby(receipts, key=lambda r: r[0]):
        if not keep_history:
            banks = [{}, {}]
        new = [{}, {}]
        for _, owner, effect, role, cell, op, version, subject in batch:
            address = cell, op, version
            entry = (subject, owner, effect)
            old = new[role].get(address, banks[role].get(address))
            if old is None or old[0] != subject:
                stale_key += int(old is not None)
                new[role][address] = entry
        for role in (0, 1):
            # Include fresh/fresh pairs once by installing the left side first.
            opposite = banks[1-role]
            if opposite and new[role]:
                other = sorted(opposite.items())
                def encode(values):
                    return torch.tensor([[(v >> i) & 1 for i in range(64)] for v in values],
                                        dtype=torch.float32)
                keys = encode(v[0] for _, v in other)
                items = list(new[role].items())
                for start in range(0, len(items), 128):
                    chunk = items[start:start+128]
                    q = encode(v[0] for _, v in chunk)
                    distance = q.sum(1)[:, None] + keys.sum(1) - 2 * (q @ keys.T)
                    scores = distance * model["weight"] + model["bias"]
                    comparisons += scores.numel()
                    # One fixed budget for both frozen heads. Stable address order
                    # breaks score ties independently of receipt insertion order.
                    if budget is None:
                        hits = (scores >= 0).nonzero().tolist()
                    else:
                        choices = scores.argsort(dim=1, descending=True, stable=True)[:, :budget]
                        kept = (scores.gather(1, choices) >= 0).nonzero()
                        hits = zip(kept[:,0].tolist(), choices[kept[:,0],kept[:,1]].tolist())
                    for i, j in hits:
                        a, x = chunk[i]
                        b, y = other[j]
                        pair = (a,b) if role == 0 else (b,a)
                        logical = (x[1:],y[1:]) if role == 0 else (y[1:],x[1:])
                        proposals.setdefault(pair, (epoch,logical))
            banks[role].update(new[role])
    return proposals, dict(scores=comparisons, key_changes=stale_key,
                           final_bank_sizes=[len(b) for b in banks])


def cited_ports(commits, recipe, target):
    # Hold out every input of the target rule, even after it has committed.
    # A negative port number encodes the source query atom, disjoint from
    # nonnegative RHS effect positions in the same execution frame.
    roles = {"Get": 0, "HasArgType": 1}
    layouts = {}
    for rid, rule in enumerate(recipe["rules"]):
        if rid == target:
            continue
        for atom, query in enumerate(rule["query"]):
            table = query["call"].get("table")
            if table in roles and "slot" in query["args"][0]:
                layouts[rid, atom] = roles[table], str(query["args"][0]["slot"])
    for owner, _, _, rid, _, epoch, refs, slots in commits:
        for ref in refs:
            atom = ref["atom"]
            layout = layouts.get((rid, atom))
            if layout is None:
                continue
            role, slot = layout
            value = slots.get(slot, {})
            if "Eq" in value:
                row = ref["row"]["Fact"]
                yield (epoch, owner, ~atom, role, row["cell"], row["op"], ref["version"], value["Eq"])


def target_rule(recipe):
    target, = [i for i,r in enumerate(recipe["rules"])
               if [atom["call"].get("table") for atom in r["query"]]==["Get","HasArgType"]
               and r["query"][0]["args"][0] == r["query"][1]["args"][0]]
    return target


def missed_sources(commits, target, receipts, grants):
    """Classify unavailable addresses using only evidence from earlier epochs."""
    from parent_projection import identity
    first = {}
    version = {}
    for epoch, _, _, role, cell, op, ver, _ in receipts:
        key = role, cell, op
        first[key] = min(first.get(key, epoch), epoch)
        version[key, ver] = min(version.get((key, ver), epoch), epoch)
    counts = Counter()
    for _, _, _, rid, _, epoch, refs, _ in commits:
        if rid != target:
            continue
        pair = tuple(identity(r)[1:] for r in sorted(refs,key=lambda r:r["atom"]))
        if (epoch,pair) in grants:
            continue
        missing = []
        for role,(cell,op,ver) in enumerate(pair):
            key = role,cell,op
            if version.get((key,ver),epoch) >= epoch:
                missing.append(("Get" if role == 0 else "HasArgType") +
                               ("_other_version" if first.get(key,epoch) < epoch else "_unseen"))
        counts["+".join(missing) or "both_available"] += 1
    return dict(counts)


def study(data, recipe):
    from parent_projection import identity
    target = target_rule(recipe)
    receipts = data["root_recipe"]["history_returns"]
    owners = {row[0]:row[5] for row in data["root_recipe"]["commits"]}
    if any(owners.get(owner) != epoch for epoch, owner, *_ in receipts):
        raise ValueError("return outside its committed owner epoch")
    if any(a[0] > b[0] for a,b in zip(receipts,receipts[1:])):
        raise ValueError("unordered history")
    citations = list(cited_ports(data["root_recipe"]["commits"], recipe, target))
    seeds = data["root_recipe"]["history_initial"]
    updates = data["root_recipe"]["history_updates"]
    # Anchor each receipt in an actual earlier owner-port observation. Updated
    # versions retain that logical port and can themselves be updated later.
    provenance = {(owner,slot,role,cell,op,version):epoch
                  for epoch,owner,slot,role,cell,op,version,_ in [*seeds,*receipts,*citations]}
    for epoch,owner,slot,role,cell,op,version,_,old in updates:
        if (provenance.get((owner,slot,role,cell,op,old),epoch+1)>epoch or old>=version):
            raise ValueError("lifecycle receipt lacks an earlier named port")
        provenance[owner,slot,role,cell,op,version] = epoch
    revisions = [row[:8] for row in updates]
    results = {}
    hard = fit_cutoff(True)
    for name, model, budget, keep in (
            ("uniform",fit_cutoff(False),8,True), ("near_misses",hard,8,True),
            ("all_positive",hard,None,True), ("same_epoch",hard,None,False),
            ("with_citations",hard,None,True)):
        events = receipts
        if name == "with_citations":
            events = merge(merge(seeds, receipts, citations, key=lambda e:(e[0],e[1])),
                           revisions, key=lambda e:e[0])
        issued, stats = issue(events, model, budget, keep)
        # Labels enter only after the issuer has stopped. Each emitted packet
        # earns credit at most once and only for a strictly later query epoch.
        used = set()
        total = 0
        for _, _, _, rid, _, epoch, refs, _ in data["root_recipe"]["commits"]:
            if rid != target:
                continue
            total += 1
            ordered = sorted(refs, key=lambda r:r["atom"])
            if [r["atom"] for r in ordered] != [0,1]:
                continue
            pair = tuple(identity(r)[1:] for r in ordered)
            if pair in issued and issued[pair][0] < epoch:
                used.add(pair)
        results[name] = dict(model=model, source=total, proposed=len(issued),
                             matched_once=len(used), matched_using_citation=sum(any(port < 0 for _,port in issued[k][1]) for k in used), distinct_owners=sum(issued[k][1][0][0] != issued[k][1][1][0] for k in used), extra=len(issued)-len(used), **stats)
        if name == "with_citations":
            checked, pending = data["root_recipe"]["history_online"]
            accepted = set()
            suppressed = data["root_recipe"]["history_suppressed"]
            observed = {}
            evidence = {(owner, slot, version): (epoch, role, (cell, op, version))
                        for epoch,owner,slot,role,cell,op,version,_ in [*seeds,*receipts]}
            evidence.update({(owner,slot,version): (epoch,role,(cell,op,version))
                             for epoch,owner,slot,role,cell,op,version,_ in [*citations,*revisions]})
            for checked_epoch, proposal, valid in [*checked, *suppressed, *((None,p,False) for p in pending)]:
                pair = tuple(map(tuple, proposal["refs"]))
                birth = proposal["epoch"]
                assert pair not in observed
                observed[pair] = birth
                for role, owner in enumerate(proposal["owners"]):
                    owner_epoch, owner_role, address = evidence[(*owner, pair[role][2])]
                    if owner_epoch > birth or owner_role != role or address != pair[role]:
                        raise ValueError("invalid logical parent at issuance")
                if checked_epoch is not None and checked_epoch <= birth:
                    raise ValueError("premature visibility")
                if valid:
                    accepted.add((checked_epoch, pair))
            if observed != {pair:item[0] for pair,item in issued.items()}:
                raise ValueError("online issuer differs from causal replay")
            committed = set()
            for _,_,_,rid,_,epoch,refs,_ in data["root_recipe"]["commits"]:
                if rid == target:
                    pair = tuple(identity(r)[1:] for r in sorted(refs,key=lambda r:r["atom"]))
                    committed.add((epoch,pair))
            results[name]["native"] = dict(suppressed=len(suppressed), initial_ports=len(seeds), updated_ports=len(revisions), checked=len(checked), pending=len(pending),
                accepted=len(accepted), committed_at_check=len(accepted & committed),
                missed=missed_sources(data["root_recipe"]["commits"],target,
                                      (*seeds,*receipts,*citations,*revisions),accepted))
            from history_successors import profile
            results[name]["successors"] = profile(data,target,accepted,(*seeds,*receipts,*citations,*revisions))
    return results
