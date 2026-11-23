"""Attribute missed root commits on frozen Run snapshots after checking alternate certificates."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import torch

from alternate_proofs import digest
from anchor_set import Domains
from anchor_set_audit import check, load_actor
from higher_cell import read
from history import History, address
from prefix_policy import Policy, generate
from prefix_recovery import Recovery


def score_certificate(actor, cat, mem, domains, policy, rule, indices):
    """Teacher forcing is diagnostic. Each pointer sees the correct earlier addresses."""
    if not indices:
        score = actor.root_scores(cat, mem, rule, None, None, domains)
        return None if score.item() >= actor.thresholds[0] else 'zero_parent'
    anchor = next(i for i, j in enumerate(indices)
                  if not cat.seminaive[rule] or mem.ports[j].version >= mem.rules[rule])
    order = cat.read_order(rule, anchor, policy.read_order)
    for depth, role in enumerate(order):
        prior = mem.nodes.new_tensor([[indices[i] for i in order[:depth]]], dtype=torch.long)
        ids = domains.role(cat, mem, rule, anchor, role)
        location = (ids == indices[role]).nonzero().flatten()
        if len(location) != 1:
            raise ValueError('reference parent is outside its seminaive domain')
        scores = (actor.pair_scores(cat, mem, rule, order[:depth], prior, role, ids)
                  if depth else actor.root_scores(cat, mem, rule, role, ids, domains)[None])
        margin = scores - actor.thresholds[2 if depth else 1]
        if margin[0, location].item() >= 0:
            continue
        recovery = policy.recovery.scores(cat, mem, rule, order, depth, prior, ids, margin)
        if recovery[0, location].item() < policy.recovery.cut:
            return 'anchor' if not depth else 'later_parent'
    return None


def teacher_allocation(folder, memory, binary, budget):
    """Construct a feasible frozen-snapshot allocation using only the recorded reference proof."""
    tape = read(folder/'tape.json')
    program = read(folder/'program.json')
    if digest(folder/'program.json') != tape['program_sha256'] or budget < 1:
        raise ValueError('incompatible reference or invalid budget')
    rules = program['recipe']['rules']
    by_run = defaultdict(list)
    for req in tape['requests']:
        by_run[req['run']].append(req)
    chosen = []
    with memory.open() as stream:
        for line in stream:
            frame = json.loads(line)
            watermarks = dict(frame['rules'])
            used = Counter()
            for req in by_run.pop(frame['run'], []):
                rule = req['rule']
                watermark = watermarks[rule]
                parents = req['parents']
                if parents and rules[rule]['metadata']['seminaive']:
                    anchor = next(i for i, p in enumerate(parents) if p['version'] >= watermark)
                else:
                    anchor = 0
                cap = budget if parents else 1
                if used[rule, anchor] < cap:
                    chosen.append(req)
                    used[rule, anchor] += 1
    if by_run:
        raise ValueError('missing source snapshots')
    labels = {req['token']:req['run'] for req in chosen}
    checked = check(folder,binary,tape,chosen)['recall_verdicts']
    if (len(labels) != len(chosen) or len(checked) != len(chosen) or
        {i for _,i,_,_ in checked} != set(labels) or
        any(labels[i] != run or i != winner or reason != 'match' for run,i,winner,reason in checked)):
        raise ValueError('assigned proof did not establish its distinct reference binding')
    return dict(mode='oracle allocation on teacher snapshots', budget=budget, verified=len(chosen),
                reference=len(tape['requests']), tape=digest(folder/'tape.json'), binary=digest(binary))


@torch.no_grad()
def measure(folder, memory, weights, head, binary, seed, budget):
    program = read(folder/'program.json')
    tape = read(folder/'tape.json')
    if digest(folder/'program.json') != tape['program_sha256']:
        raise ValueError('program and teacher tape differ')
    actor = load_actor(weights, True)
    cat = actor.catalog_type(program)
    nodes = actor.template_graph(cat)
    policy = Policy(budget, recovery=Recovery(head, weights))
    history = History(cat, seed)
    commits = {req['token']: req for req in tape['requests']}
    targets = defaultdict(list)
    for req in commits.values():
        targets[req['run']].append(req)
    probes, contents = [], []
    initial_miss = {}
    capacity = 0
    positive_groups = 0
    with memory.open() as stream:
        for line in stream:
            frame = json.loads(line)
            snap = history.snapshot(frame)
            mem = actor.memory(cat, snap, nodes)
            index = {port.address: i for i, port in enumerate(mem.ports)}
            emitted = set()
            for rule, refs in generate(actor, cat, mem, policy):
                indices = [index[ref] for ref in refs]
                parents = [dict(address=dict(token=history.inverse[token], op=op),
                                version=mem.ports[j].version)
                           for (token, op), j in zip(refs, indices, strict=True)]
                probes.append(dict(token=len(probes)+1, run=snap.run, rule=rule, parents=parents))
                contents.append(tuple(mem.ports[j].hashes for j in indices))
                emitted.add((rule, refs))
            groups = Counter(req['rule'] for req in targets[snap.run])
            positive_groups += len(groups)
            domains = Domains(mem)
            for rule, count in groups.items():
                parents = len(cat.atoms[rule])
                # Optimistic bound, including any valid alternate addressing of a binding.
                if parents:
                    anchors = range(parents) if cat.seminaive[rule] else range(1)
                    slots = sum(budget for a in anchors if len(domains.role(cat, mem, rule, a, a)))
                else:
                    slots = 1
                capacity += min(count, slots)
            for req in targets[snap.run]:
                rule = req['rule']
                refs = tuple(history.rename(address(p['address'])) for p in req['parents'])
                if (rule, refs) in emitted:
                    continue
                reason = score_certificate(actor, cat, mem, domains, policy, rule, [index[p] for p in refs])
                initial_miss[req['token']] = reason or 'qualified_but_pruned'

    checked = check(folder, binary, tape, probes)
    families = defaultdict(list)
    rejects = Counter()
    for run, token, winner, reason in checked['recall_verdicts']:
        request = probes[token-1]
        if request['run'] != run:
            raise ValueError('out-of-order native evidence')
        if winner is None:
            rejects[reason] += 1
        else:
            if commits[winner]['run'] != run or commits[winner]['rule'] != request['rule']:
                raise ValueError('matched a different rule or Run')
            families[winner].append(token-1)
    missed = Counter(initial_miss[i] for i in commits.keys()-families.keys())
    similar = sum(len(indices)-len({contents[j] for j in indices}) for indices in families.values())
    hits = len(families)
    duplicate = sum(len(indices)-1 for indices in families.values())
    if hits > capacity or hits+duplicate+sum(rejects.values()) != len(probes):
        raise ValueError('capacity or proposal attribution failed')
    return dict(mode='root-only shadow on teacher snapshots', program=digest(folder/'program.json'),
                tape=digest(folder/'tape.json'), memory=digest(memory), binary=digest(binary),
                actor=digest(weights), head=policy.recovery.checkpoint, seed=seed, budget=budget,
                runs=history.run, required=len(commits), nonempty_rule_runs=positive_groups,
                optimistic_capacity=capacity, paid=len(probes), signed_if_submitted=hits,
                distinct_via_alternate_only=len(families.keys() & initial_miss.keys()),
                duplicate=duplicate, repeat_with_identical_parent_fields=similar,
                missed=dict(missed), rejections=dict(rejects))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    subs = p.add_subparsers(dest='mode',required=True)
    for mode, fields in [('capacity',('folder','memory','binary','output')),
                         ('pointer',('folder','memory','weights','head','binary','output'))]:
        cmd = subs.add_parser(mode)
        for field in fields:
            cmd.add_argument(field,type=Path)
        cmd.add_argument('--budget',type=int,default=32)
        if mode == 'pointer':
            cmd.add_argument('--seed',type=int,required=True)
    a = p.parse_args()
    torch.set_num_threads(1)
    if a.mode == 'capacity':
        result = teacher_allocation(a.folder,a.memory,a.binary,a.budget)
    else:
        result = measure(a.folder,a.memory,a.weights,a.head,a.binary,a.seed,a.budget)
    a.output.write_text(json.dumps(result,indent=2)+'\n')
