"""Causal named-port dataset for a relation join with determined source atoms."""
from collections import Counter
from pathlib import Path
import json

from parent_projection import identity


def export(data, recipe, target, path: Path):
    roots=data['root_recipe']
    rule=recipe['rules'][target]
    names=[a['call']['table'] for a in rule['query']]
    if len(set(names))!=len(names):
        raise ValueError("study requires distinct role tables")
    layout=[[a['slot'] for a in atom['args']] for atom in rule['query']]
    sources={(rid,i):(names.index(a['call']['table']),a['args']) for rid,r in enumerate(recipe['rules'])
             if rid!=target for i,a in enumerate(r['query']) if a['call'].get('table') in names}
    commits=[]
    events=[]
    owners={}
    for ordinal,_,_,rid,_,epoch,refs,slots in roots['commits']:
        owners[ordinal]=rid,epoch
        if rid==target:
            commits.append([epoch,ordinal,[[ref['atom'],identity(ref)] for ref in refs]])
            continue
        for ref in refs:
            k=rid,ref['atom']
            if k in sources:
                role,args=sources[k]
                fields=[slots.get(str(a['slot'])) if 'slot' in a else a.get('literal') for a in args]
                events.append([epoch,ordinal,~ref['atom'],role,identity(ref),fields,'input'])
    for owner,rid,epoch,table,op,cell,field,version,fields in roots['chain_rows']:
        name=recipe['tables'][table]['name']
        if name not in names:
            continue
        role=names.index(name)
        if owners.get(owner)!=(rid,epoch) or recipe['rules'][rid]['effects'][op]['call'].get('table')!=name or len(fields)!=len(layout[role]):
            raise ValueError("return is not from the named source")
        events.append([epoch,owner,op,role,('fact',cell,field,version),fields,'self' if rid==target else 'return'])
    for epoch,table,dep,owner,slot,old,new,fields in roots['chain_audit']['updates']:
        name=recipe['tables'][table]['name']
        if name not in names:
            continue
        events.append([epoch,owner,slot,names.index(name),identity(dict(row=dep,version=new or old)),
                       fields,'revision' if new is not None else 'retire'])
    allocations={row[0]:(row[1],row[2]) for row in roots['fresh']}
    earliest={}
    for ep,_,_,role,dep,_,kind in events:
        if kind!='retire':
            k=role,tuple(dep)
            earliest[k]=min(earliest.get(k,ep),ep)
    missing=Counter()
    for ep,_,refs in commits:
        for role,dep in refs:
            if earliest.get((role,tuple(dep)),ep)>=ep:
                a=allocations.get(dep[1]) if dep[0]=='fact' else None
                missing[str(a[1]) if a else 'unknown']+=1
    origins=dict(missing)
    path.write_text(json.dumps(dict(target=target,tables=names,layout=layout,schedule=[(ep,mark) for rid,ep,mark in roots["chain_audit"]["scheduled"] if rid==target],commits=commits,events=events,missing_allocators=origins),
                               separators=(',',':')))


def study(data):
    """Issue four-parent joins from earlier named observations; hold out all target effects."""
    from collections import defaultdict
    layout=data['layout']
    roles=len(layout)
    banks=[{} for _ in layout]
    indexes=defaultdict(set)
    events=defaultdict(list)
    proposals={}
    cost=Counter()
    for ev in data['events']:
        if ev[-1]!='self':
            events[ev[0]].append(ev)
    def extend(bound,slots,epoch):
        if len(bound)==roles:
            addresses=tuple(bound[i] for i in range(roles))
            proposals.setdefault((addresses[1],addresses[3]),epoch)
            return
        choices=[]
        for role,columns in enumerate(layout):
            if role in bound:
                continue
            for i,slot in enumerate(columns):
                if slot in slots:
                    bank=indexes.get((role,i,slots[slot]),())
                    choices.append((len(bank),role,i,bank))
        if not choices:
            raise ValueError('disconnected join')
        _,role,_,bank=min(choices,key=lambda x:x[:3])
        cost['address_reads']+=1
        for addr in bank:
            cost['port_visits']+=1
            vals=banks[role][addr[:-1]][1]
            if any(s in slots and slots[s]!=v for s,v in zip(layout[role],vals)):
                continue
            extend({**bound,role:addr},{**slots,**dict(zip(layout[role],vals))},epoch)
    for ep,group in sorted(events.items()):
        for _,owner,slot,role,raw,fields,kind in sorted(group,key=lambda e:(e[-1] in ('retire','revision'),e[1],e[2])):
            addr=tuple(raw)
            old=banks[role].get(addr[:-1])
            vals=None if fields is None else tuple(json.dumps(v,sort_keys=True) for v in fields)
            if old and (old[0][-1]>addr[-1] or old==(addr,vals)):
                continue
            if old:
                for i,v in enumerate(old[1]):indexes[role,i,v].discard(old[0])
                del banks[role][addr[:-1]]
            if vals is None or any(v=='null' for v in vals):
                continue
            banks[role][addr[:-1]]=addr,vals
            for i,v in enumerate(vals):indexes[role,i,v].add(addr)
            extend({role:addr},dict(zip(layout[role],vals)),ep)
    hits=set()
    for epoch,owner,refs in data['commits']:
        pair=tuple(tuple(r) for i,r in sorted(refs))
        if proposals.get(pair,epoch)<epoch:hits.add(pair)
    return dict(source=len(data['commits']),proposed=len(proposals),hits=len(hits),extra=len(proposals)-len(hits),**cost)


def snapshot_audit(data, reader=None):
    """Reconstruct frozen port memory at every supplied Run (positive Runs for legacy traces)."""
    from collections import defaultdict

    if data['target'] != 243 or data['layout'] != [[0,1,2],[3,0,4],[5,1],[0,5,6]]:
        raise ValueError('expected the four rule 243 port layouts')
    expected = defaultdict(set)
    for epoch, _, refs in data['commits']:
        refs = dict(refs)
        expected[epoch].add((tuple(refs[1]), tuple(refs[3])))
    schedule = dict(data.get("schedule", []))
    if any(schedule[ep] != mark for ep,mark in data.get("schedule", [])):
        raise ValueError("one epoch has multiple distinct release watermarks")
    if schedule and expected.keys() - schedule.keys():
        raise ValueError("missing source Run for committed reference")
    events = defaultdict(list)
    for event in data['events']:
        events[event[0]].append(event)
    ports = [{} for _ in data['layout']]
    retired = set()
    # The oracle sees the reference only to bound the best attainable first read.
    ceilings = {k: Counter() for k in (1,4,8,16,32)}
    counts = Counter()
    for epoch in sorted(events.keys() | expected.keys() | schedule.keys()):
        if epoch in schedule or epoch in expected:
            # The Cell needs both determined witnesses as well as its B,D roots.
            body_expr = defaultdict(list)
            for address, values in ports[0].values():
                body_expr[values[:2]].append(address)
            by_input = defaultdict(set)
            for address, (x, expr) in ports[2].values():
                by_input[x].add((expr,address))
            loops = defaultdict(list)
            for address, (_, body, _) in ports[1].values():
                loops[body].append(address)
            pairs = set()
            for d, (body, x, _) in ports[3].values():
                for expr, c in by_input.get(x, ()):
                    for a in body_expr.get((body, expr), ()):
                        for b in loops.get(body, ()):
                            if max(a[-1],b[-1],c[-1],d[-1]) >= schedule.get(epoch,0):
                                pairs.add((b,d))
            if reader is not None:
                reader(ports, schedule[epoch], expected[epoch])
            hits = pairs & expected[epoch]
            frequencies = sorted(Counter(b for b,_ in hits).values(),reverse=True)
            for k, totals in ceilings.items():
                totals.update(recoverable=sum(frequencies[:k]),
                              pair_scores=min(k,len(ports[1]))*len(ports[3]),
                              first_scores=len(ports[1]))
            counts.update(reference=len(expected[epoch]), available=len(hits),
                          missing=len(expected[epoch]-pairs), compatible=len(pairs),
                          full_pairs=len(ports[1])*len(ports[3]),
                          minimum_first_loop_ports=len({b for b,_ in hits}),
                          runs_checked=1, positive_runs=int(bool(expected[epoch])))
        # A lifecycle receipt may only revise a row that was independently observed.
        # Apply end-of-Run changes after all source actions and before the next snapshot.
        for _, owner, slot, role, raw, fields, kind in sorted(events.get(epoch, ()),
                key=lambda e:(e[-1] in ('retire','revision'),e[1],e[2])):
            address = tuple(raw)
            key = address[:-1]
            old = ports[role].get(key)
            if kind == 'self' or (role,address) in retired:
                continue
            if old and old[0][-1] > address[-1]:
                continue
            if kind == 'retire':
                retired.add((role,address))
                ports[role].pop(key,None)
            elif fields and None not in fields and (kind != 'revision' or old):
                values = tuple(json.dumps(v,sort_keys=True) for v in fields)
                ports[role][key] = (address, values)
    return dict(counts, first_read_oracle=ceilings)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    args = parser.parse_args()
    trace = json.loads(args.trace.read_text())
    print(json.dumps(dict(early=study(trace), snapshots=snapshot_audit(trace)),indent=2))
