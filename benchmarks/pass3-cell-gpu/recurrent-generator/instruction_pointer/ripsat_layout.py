"""Bake variable-length Cell wiring from committed teacher requests and their typed result ports."""
from bisect import bisect_right
from collections import Counter, defaultdict, deque
from functools import lru_cache
from heapq import heappop, heappush
import json

from higher_cell import fingerprint, read
from side_boundary import address


def signatures(program):
    return [fingerprint(r) for r in program['recipe']['rules']]


def queries(rule):
    return [a for a in rule['query'] if 'table' in a['call']]


def output_table(rule, pc):
    if pc<0 or pc>=len(rule['effects']):
        return None
    effect=rule['effects'][pc]
    return effect.get('call',{}).get('table') if effect['op'] in ('let','set') else None


def capture(folder, donor, limit, *, each_parent_first=False, grow_consumers=False, receipt_contract=None):
    """Layout contains (rule, relative Run group, atom sources) in source order.
    A source is (previous step, result PC) or (-1, independent boundary slot).
    Exact obligations include every table atom, including external repair ports.
    """
    target=read(folder/'program.json')
    refs=read(folder/'tape.json')['requests']
    rules=target['recipe']['rules']
    donor_index={sig:i for i,sig in enumerate(signatures(donor))}
    mapped=[donor_index.get(sig) for sig in signatures(target)]
    contract = receipt_contract if receipt_contract is not None else target.get("receipt_contract")
    if contract is not None and (contract["schema"] != "eggfuse-recipe-receipts/v1" or
                                 contract["recipe_sha256"] != target["recipe"]["sha256"]):
        raise ValueError("receipt contract does not belong to target Recipe")
    table_names = [t["name"] for t in target["recipe"]["tables"]] if contract is not None else []
    def returned_table(rid, pc):
        if contract is None:
            return output_table(rules[rid], pc)  # historical artifacts
        port = contract["rules"][rid]["outputs"].get(str(pc))
        return table_names[port["table"]] if port is not None else None
    producer={p['token']:j for j,p in enumerate(refs)}
    atoms=[queries(r) for r in rules]
    timelines=defaultdict(list)
    schedules=defaultdict(list)
    with (folder/'memory.jsonl').open() as frames:
        for line in frames:
            frame=json.loads(line)
            for rid,_ in frame['rules']:
                schedules[rid].append(frame['run'])
            for a in frame['retired']:
                timelines[a['token'],a['op']].append((frame['run'],None))
            for a,row in frame['updates']:
                timelines[a['token'],a['op']].append((frame['run'],row))
    def observation(a,run):
        timeline=timelines[a]
        ix=bisect_right(timeline,run,key=lambda x:x[0])-1
        return timeline[ix][1] if ix>=0 else None
    @lru_cache(None)
    def parents(j):
        req=refs[j]
        edges=[]
        for a,atom in zip(req['parents'],atoms[req['rule']],strict=True):
            token,pc=address(a)
            parent=producer.get(token)
            if parent is not None:
                pred=refs[parent]
                if pred['run']>=req['run']:
                    raise ValueError('capture violates the sealed Run boundary')
                if mapped[pred['rule']] is None or returned_table(pred['rule'],pc)!=atom['call']['table']:
                    parent=None
            edges.append(parent)
        return edges
    def encode(nodes):
        indices=sorted(nodes)
        local={j:i for i,j in enumerate(indices)}
        group={}
        boundary={}
        steps=[]
        root_run=refs[indices[0]]['run']
        ready=True
        group_rules=defaultdict(set)
        for j in indices:
            req=refs[j]
            uses=[]
            for a,parent in zip(req['parents'],parents(j),strict=True):
                addr=address(a)
                if parent in local:
                    uses.append((local[parent],addr[1]))
                    row=observation(addr,refs[parent]['run']+1)
                    ready &= row is not None and row['version']==a['version']
                else:
                    key=(*addr,a['version'])
                    uses.append((-1,boundary.setdefault(key,len(boundary))))
                    row=observation(addr,root_run)
                    ready &= row is not None and row['version']==a['version']
            group_rules[req['run']].add(req['rule'])
            epoch=group.setdefault(req['run'],len(group))
            steps.append((mapped[req['rule']],epoch,tuple(uses)))
        previous=root_run
        first_schedule=True
        for run,rule_set in list(group_rules.items())[1:]:
            times=schedules[next(iter(rule_set))]
            start=bisect_right(times,previous)
            for t in times[start:]:
                if t>run:
                    raise ValueError('recorded group missing from source schedule')
                if t==run or all(t in schedule_sets[r] for r in rule_set):
                    first_schedule &= t==run
                    break
            previous=run
        return tuple(steps),indices[0],tuple(boundary),bool(ready),first_schedule,tuple(refs[i]['token'] for i in indices)
    schedule_sets={r:set(times) for r,times in schedules.items()}
    by_root=defaultdict(dict)
    counts=Counter()
    for j,req in enumerate(refs):
        if mapped[req['rule']] is None:
            continue
        direct=parents(j)
        # The default follows atom order. Alternative starting producers expose
        # entry layouts otherwise lost when several atoms have distinct owners.
        orders=[direct]
        if each_parent_first:
            unique=list(dict.fromkeys(k for k in direct if k is not None))
            orders.extend([k]+[p for p in direct if p!=k] for k in unique[1:])
        seen=set()
        for order in orders:
            selected={j}
            todo=deque(order)
            while todo and len(selected)<limit:
                pred=todo.popleft()
                if pred is None or pred in selected:
                    continue
                selected.add(pred)
                todo.extend(parents(pred))
                key=frozenset(selected)
                if key in seen:
                    continue
                seen.add(key)
                layout,root,boundary,ready,first_schedule,tokens=encode(selected)
                by_root[root].setdefault(layout,[]).append((boundary,ready,first_schedule,tokens))
                counts[len(layout)]+=1
    if grow_consumers:
        # Bake time only. A root can own parallel consumers which never appear
        # together in the ancestors of any single downstream request.
        consumers = defaultdict(list)
        for child, req in enumerate(refs):
            if mapped[req['rule']] is not None:
                for pred in set(parents(child)) - {None}:
                    consumers[pred].append(child)
        for root in list(consumers):
            selected = {root}
            pending = list(consumers[root])  # already in ascending source order
            queued = set(pending)
            while pending and len(selected) < limit:
                child = heappop(pending)
                layout, first, boundary, ready, scheduled, tokens = encode(selected | {child})
                if not ready or not scheduled:
                    continue
                selected.add(child)
                record = (boundary, ready, scheduled, tokens)
                occurrences = by_root[first].setdefault(layout, [])
                if record not in occurrences:
                    occurrences.append(record)
                    counts[len(layout)] += 1
                for successor in consumers.get(child, ()):
                    if successor not in queued:
                        heappush(pending, successor)
                        queued.add(successor)
    return refs,mapped,by_root,counts


def iterative_layouts(donor,plan):
    """The iterative catalog's chain edges specify one pivot per join.
    Every remaining atom gets a distinct independent boundary until proven shared.
    """
    rules=donor['recipe']['rules']
    leaves=donor['spine_blocks']['entries']
    chains=[[(leaf['consumer'],leaf['pivot'],None)] for leaf in leaves]
    out=set()
    for join in plan['joins']:
        lhs,rhs=chains[join['left']],chains[join['right']]
        rid,pivot,_=rhs[0]
        chain=lhs+[(rid,pivot,join['output'])]+rhs[1:]
        chains.append(chain)
        steps=[]
        n=0
        for i,(rid,pivot,pc) in enumerate(chain):
            wires=[]
            for a,atom in enumerate(rules[rid]['query']):
                if 'table' not in atom['call']:
                    continue
                if i and pivot==a:
                    if output_table(rules[chain[i-1][0]],pc)!=atom['call']['table']:
                        raise ValueError('iterative Bake pivot type mismatch')
                    wires.append((i-1,pc))
                else:
                    wires.append((-1,n))
                    n+=1
            steps.append((rid,i,tuple(wires)))
        out.add(tuple(steps))
    return out
