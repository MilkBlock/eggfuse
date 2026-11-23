"""Bound each rule/anchor frontier after scoring; optionally check selected partial proofs."""
from collections import Counter, defaultdict
from dataclasses import dataclass

import torch
from anchor_set import Domains


@dataclass(frozen=True)
class Policy:
    top_k: int | None = None
    verify: bool = False
    audit: bool = False
    recovery: object = None
    read_order: str | None = None

    def __post_init__(self):
        if self.top_k is not None and self.top_k < 1:
            raise ValueError('top-k must be positive')
        mode=self.read_order or getattr(self.recovery,'read_order','source')
        if mode not in ('source','connected'):
            raise ValueError('unknown pointer read order')
        object.__setattr__(self,'read_order',mode)


def score_tiles(model, cat, mem, dom, rid, anchor, order, depth, frontier):
    role = order[depth]
    ids = dom.role(cat, mem, rid, anchor, role)
    if not len(ids):
        return
    for prefix in frontier.split(max(1, 65536 // len(ids))):
        if depth:
            scores = model.pair_scores(cat, mem, rid, order[:depth], prefix, role, ids)
        else:
            scores = model.root_scores(cat, mem, rid, role, ids, dom)[None,:]
        yield prefix, ids, scores


def shared_conflicts(cat, mem, rid, roles, prefix, ids):
    # Post-score audit of the exported 64-bit field hashes, on the same domain.
    # Native verification separately compares actual canonical Value objects.
    conflicts = torch.zeros((len(prefix), len(ids)), dtype=torch.bool)
    for j, prior in enumerate(roles[:-1]):
        for left,right in cat.field_links[rid,prior,roles[-1]]:
            conflicts |= mem.fields[prefix[:, j],left] @ mem.fields[ids,right].T != 64
    return conflicts


def select_frontier(model, cat, mem, dom, rid, anchor, order, depth, frontier, policy, probe, count, field_audit):
    if policy.recovery is not None:
        from prefix_recovery import select
        return select(model,cat,mem,dom,rid,anchor,order,depth,frontier,policy,count)
    keep, values = [], []
    width = depth + 1
    cut = model.thresholds[1 if depth == 0 else 2]
    k = policy.top_k
    for prefix, ids, scores in score_tiles(model, cat, mem, dom, rid, anchor, order, depth, frontier):
        qualified = scores >= cut
        count['scored'] += scores.numel()
        count['above_threshold'] += int(qualified.sum())
        if policy.audit or field_audit:
            conflicts = shared_conflicts(cat,mem,rid,order[:width],prefix,ids)
            count['shared_hash_conflicts_scored'] += int(conflicts.sum())
            count['shared_hash_conflicts_above_threshold'] += int((conflicts & qualified).sum())
        if policy.audit:
            full = ids.tolist()
            good = torch.tensor(probe(rid, order[:width], [(p,full) for p in prefix.tolist()]), dtype=torch.bool)
            if good.shape != qualified.shape:
                raise ValueError('unmatched diagnostic prefix matrix')
            count['native_inconsistent_scored'] += int((~good).sum())
            count['native_inconsistent_above_threshold'] += int((~good & qualified).sum())
        row, col = qualified.nonzero(as_tuple=True)
        pts = torch.cat([prefix[row], ids[col,None]], dim=1)
        logits = scores[row,col]
        if k is None:
            keep.append(pts)
            continue
        if keep:
            pts = torch.cat([keep[0], pts])
            logits = torch.cat([values[0], logits])
        # Keep a (k+1)th score to detect ties crossing the global layer budget.
        if len(logits) > k+1:
            logits, which = logits.topk(k+1)
            pts = pts[which]
        keep, values = [pts], [logits]
    if not keep:
        return frontier.new_empty((0,width))
    selected = torch.cat(keep)
    if k is not None and len(selected) > k:
        logits, which = values[0].sort(descending=True)
        # At a tie crossing the cap, drop the entire boundary tie. No token address
        # or tensor ordering breaks a semantic tie.
        eligible = logits > logits[k] if logits[k-1] == logits[k] else torch.arange(len(logits)) < k
        selected = selected[which[eligible]]
    count['after_cap'] += len(selected)
    partial = width < len(order)
    if len(selected) and (policy.audit or policy.verify and partial):
        grouped = defaultdict(list)
        for row in selected.tolist():
            grouped[tuple(row[:-1])].append(row[-1])
        rows = list(grouped.items())
        answers = probe(rid, order[:width], rows)
        valid = {(*parents,last) for (parents, choices), flags in zip(rows, answers, strict=True)
                 for last, ok in zip(choices, flags, strict=True) if ok}
        count['native_inconsistent_after_cap'] += len(selected)-len(valid)
        if policy.verify and partial:
            count['verifier_checked'] += len(selected)
            count['verifier_pruned'] += len(selected)-len(valid)
            selected = selected[[tuple(row) in valid for row in selected.tolist()]]
    return selected


def generate(model, cat, mem, policy, probe=None, counts=None, field_audit=False, selected_rules=None, activated=None):
    if (policy.audit or policy.verify) and probe is None:
        raise ValueError('prefix verification needs a sealed native receiver')
    if counts is None:
        counts = defaultdict(Counter)
    dom = Domains(mem)
    for rid, wm in mem.rules.items():
        if selected_rules is not None and rid not in selected_rules:
            continue
        atoms = cat.atoms[rid]
        if not atoms:
            if (not cat.seminaive[rid] or wm == 0) and model.root_scores(cat,mem,rid,None,None,dom).item() >= model.thresholds[0]:
                if activated is not None:
                    activated.add(rid)
                yield rid, ()
            continue
        for anchor in range(len(atoms) if cat.seminaive[rid] else 1):
            order = cat.read_order(rid,anchor,policy.read_order)
            frontier = dom.empty.reshape(1,0)
            for depth in range(len(order)):
                count = counts['partial' if depth+1 < len(order) else 'complete', depth+1]
                if depth and policy.read_order=='connected':
                    source_role=depth-1 if depth<=anchor else depth
                    count['changed_read_position']+=int(order[depth]!=source_role)
                frontier = select_frontier(model,cat,mem,dom,rid,anchor,order,depth,frontier,policy,probe,count,field_audit)
                if not len(frontier):
                    break
                if depth == 0 and activated is not None:
                    activated.add(rid)
            for row in frontier.tolist():
                refs = [None]*len(order)
                for role,j in zip(order,row,strict=True):
                    refs[role] = mem.ports[j].address
                yield rid, tuple(refs)


def native_probe(history, snapshot, send, receive):
    def premise(i):
        port = snapshot.ports[i]
        alias,op = port.address
        return dict(address=dict(token=history.inverse[alias],op=op),version=port.version)
    def probe(rid,roles,rows):
        request = dict(run=snapshot.run, rule=rid, roles=roles,
                       rows=[([premise(i) for i in prev],[premise(i) for i in ids]) for prev,ids in rows])
        send(dict(finish=False,requests=[],prefix_probe=request))
        reply = receive()
        flags = reply['prefix_ok']
        if (reply['run'] != snapshot.run or len(rows)!=len(flags)
                or any(len(r[1])!=len(f) for r,f in zip(rows,flags))):
            raise ValueError('partial verdict dimensions differ')
        return flags
    return probe
