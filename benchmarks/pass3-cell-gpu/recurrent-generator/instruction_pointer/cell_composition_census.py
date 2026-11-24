"""Offline census of named Cell owners and possible unary/binary composition operators."""
import argparse
from bisect import bisect_left,insort
from collections import Counter, defaultdict
from functools import lru_cache
import gzip
import hashlib
import json
from math import prod
from pathlib import Path

from alternate_proofs import digest
from higher_cell import fingerprint, read
from ripsat_layout import capture, queries
from ripsat_replay import unpack


def inventory(program):
    rules=program['recipe']['rules']
    tables=[t['name'] for t in program['recipe']['tables']]
    merges={m['table']:m['operations'] for m in program['merge_programs']['programs']}
    exports={('initial',t):{0:t} for t in tables}
    def merge_ports(t,base):
        return {base+i:op['call']['table'] for i,op in enumerate(merges[t]) if op['kind']=='construct'}
    for t in merges:
        exports['repair',t]=merge_ports(t,0)
    for rid,r in enumerate(rules):
        out={}
        offset=len(r['effects'])
        for pc,op in enumerate(r['effects']):
            t=op.get('call',{}).get('table')
            if t and op['op'] in ('let','set'):
                out[pc]=t
            if op['op']=='set' and t in merges:
                out.update(merge_ports(t,offset));offset+=len(merges[t])
        exports['generated',rid]=out
    return exports,tables


def operator_ceiling(tables,counts):
    """Count labeled atom assignments onto one or two distinct producer instances."""
    if not tables:return (0,0)
    columns=Counter(tables)
    profiles=Counter(tuple(row.get(t,0) for t in columns) for row in counts)
    profiles.pop((0,)*len(columns),None)
    exponents=tuple(columns.values())
    def ways(p):return prod(x**n for x,n in zip(p,exponents,strict=True))
    singles={p:ways(p) for p in profiles}
    one=sum(v*profiles[p] for p,v in singles.items())
    directed=sum(nx*ny*(ways(tuple(a+b for a,b in zip(x,y,strict=True)))-singles[x]-singles[y])
                 for x,nx in profiles.items() for y,ny in profiles.items())
    assert directed%2==0
    return one,directed//2


def higher_counts(folder,donor,bank,requests):
    eligible=set(unpack(read(bank/'catalog.json')))
    refs,_,by_root,_=capture(folder,donor,max(map(len,eligible)),each_parent_first=True,grow_consumers=True)
    assert refs==requests
    end={r['token']:r['run'] for r in refs}
    occupied={}
    selected=[]
    candidates=set()
    for layouts in by_root.values():
        for layout,occurrences in layouts.items():
            if layout not in eligible:continue
            for _,ready,scheduled,tokens in occurrences:
                if ready and scheduled:candidates.add(tokens)
    # A single conservative packing, with one owner per completed primitive token.
    for group in sorted(candidates,key=lambda g:(max(end[t] for t in g),-len(g),g)):
        if len(group)<2 or any(t in occupied for t in group):continue
        done=max(end[t] for t in group)
        selected.append(group)
        for t in group:occupied[t]=(group[0],done)
    by_token={q['token']:q for q in refs}
    boundary_cells=Counter()
    for g in selected:
        member=set(g)
        boundary_cells[len({p['address']['token'] for t in g for p in by_token[t]['parents']
                            if p['address']['token'] not in member})]+=1
    after=Counter();changed=0;cross=Counter()
    for q in refs:
        owners={p['address']['token'] for p in q['parents']}
        packed={occupied[t][0] if t in occupied and occupied[t][1]<q['run'] else t for t in owners}
        after[len(packed)]+=1
        cross[len(owners),len(packed)]+=1
        changed+=len(packed)<len(owners)
    return dict(frozen_catalog=len(eligible),eligible_teacher_groups=len(candidates),packed_groups=len(selected),
                boundary_cells_per_packed_instance=boundary_cells,packed_sizes=Counter(map(len,selected)),changed=changed,after=after,
                transitions={f'{i}->{j}':n for (i,j),n in sorted(cross.items())})


def count_offers(folder,operators,types,positive):
    # Revisit only version buckets inside each scheduled rule's watermark.
    # A trigger offer needs its own mapped ports alive, irrespective of partners.
    index=defaultdict(lambda:defaultdict(list))
    for operator in operators:
        rid,spec=operator
        groups=defaultdict(list)
        for group,tp,pc in spec:groups[group,tp].append(pc)
        for (_,tp),pcs in groups.items():
            for pc in set(pcs):
                index[rid][tp,pc].append((operator,tuple(set(pcs))))
    versions=[];buckets=defaultdict(set);visible={};offers=0;hist=Counter()
    with (folder/'memory.jsonl').open() as stream:
        for frame in map(json.loads,stream):
            for a in frame['retired']:
                key=(a['token'],a['op'])
                buckets[visible.pop(key)].remove(key)
            for a,row in frame['updates']:
                key=(a['token'],a['op']);v=row['version']
                if key in visible:buckets[visible[key]].remove(key)
                if v not in buckets:insort(versions,v)
                buckets[v].add(key);visible[key]=v
            fresh={}
            for rid,wm in frame['rules']:
                if rid not in index:continue
                if wm not in fresh:
                    eligible=defaultdict(list)
                    for i in range(bisect_left(versions,wm),bisect_left(versions,frame['epoch'])):
                        for t,pc in buckets[versions[i]]:eligible[types[t],pc].append(t)
                    fresh[wm]=eligible
                issued=set()
                for key,tokens in fresh[wm].items():
                    for op,pcs in index[rid].get(key,()):
                        for t in tokens:
                            if all((t,pc) in visible for pc in pcs):issued.add((op,t))
                offers+=len(issued)
                hist.update(positive.get((frame['run'],op,t),0) for op,t in issued)
    if sum(k*n for k,n in hist.items())!=sum(positive.values()):
        raise ValueError('delta offer denominator omitted productive triggers')
    return hist


def measure(folder, donor_dir, bank):
    program=read(folder/'program.json');rules=program['recipe']['rules']
    exports,tables=inventory(program)
    types={tpl:Counter(out.values()) for tpl,out in exports.items()}
    @lru_cache(None)
    def ceiling(ts):return operator_ceiling(ts,types.values())
    ts=[tuple(a['call']['table'] for a in queries(r)) for r in rules]
    space=[ceiling(tuple(sorted(t))) for t in ts]
    tape=read(folder/'tape.json')
    if tape['program_sha256']!=digest(folder/'program.json'):raise ValueError('wrong tape')
    reqs=tape['requests'];by_run=defaultdict(list)
    reference=read(folder/'capture.json')
    if len(reqs)!=reference['matches']:raise ValueError('incomplete teacher ledger')
    for q in reqs:by_run[q['run']].append(q)
    template={};visible={};owners=Counter();kinds=Counter();mapping=Counter();fresh_groups=Counter()
    op_freq=Counter();fan=Counter();used_rules=set();fresh_two=0
    for frame in map(json.loads,(folder/'memory.jsonl').open()):
        run=frame['run'];wm=dict(frame['rules'])
        if reference['schedule'][run-1][4]!=len(by_run[run]):raise ValueError('wrong Run attribution')
        for q in frame['accepted']:template[q['token']]=('generated',q['rule'])
        for event in frame['repair_events']:template[event['token']]=('repair',tables[event['merge_table']])
        for addr in frame['retired']:del visible[addr['token'],addr['op']]
        for addr,row in frame['updates']:
            t,pc=addr['token'],addr['op'];visible[t,pc]=row
            if t<0 and t%2:template[t]=('initial',tables[row['table']])
        for q in by_run[run]:
            rid=q['rule'];used_rules.add(rid);roles=ts[rid]
            groups={};spec=[];fresh=[];unique=True
            for i,(table,p) in enumerate(zip(roles,q['parents'],strict=True)):
                t,pc=p['address']['token'],p['address']['op']
                tp=template[t];row=visible[t,pc]
                if exports[tp].get(pc)!=table or tables[row['table']]!=table or row['version']!=p['version']:
                    raise ValueError(f'wrong typed or stale port on run {run}, rule {rid}')
                groups.setdefault(t,len(groups));spec.append((groups[t],tp,pc))
                unambiguous=types[tp][table]==1
                mapping['unique_ports']+=unambiguous;mapping['ports']+=1;unique &= unambiguous
                kinds[tp[0]]+=1
                if p['version']>=wm[rid]:fresh.append(t)
            distinct_ports={(g,pc) for g,_,pc in spec}
            mapping['distinct_parent_ports']+=len(distinct_ports)
            mapping['parent_instances']+=len(groups)
            mapping['commits_using_multiple_pcs_of_one_parent']+=len(distinct_ports)>len(groups)
            k=len(groups);owners[k]+=1;fresh_groups[k,len(set(fresh))]+=1
            if k and unique:mapping['all_unique_commits']+=1
            if k==2 and len(set(fresh))==2:fresh_two+=1
            operator=(rid,tuple(spec));op_freq[operator]+=1
            if fresh:fan[run,operator,fresh[0]]+=1
            elif k and rules[rid]['metadata']['seminaive']:raise ValueError('missing delta owner')
    portable={('generated',i):fingerprint(r) for i,r in enumerate(rules)}
    portable.update({('initial',t['name']):fingerprint(t) for t in program['recipe']['tables']})
    portable.update({('repair',m['table']):fingerprint(m) for m in program['merge_programs']['programs']})
    frequencies={}
    for (rid,spec),n in op_freq.items():
        if not spec:continue
        identity=[portable['generated',rid],[(g,tp[0],portable[tp],pc) for g,tp,pc in spec]]
        sig=hashlib.sha256(json.dumps(identity,separators=(',',':')).encode()).hexdigest()
        frequencies[sig]=[len({g for g,_,_ in spec}),n]
    offers=count_offers(folder,op_freq,template,fan)
    return dict(commits=len(reqs),program=digest(folder/'program.json'),tape=digest(folder/'tape.json'),
                operator_frequency=frequencies,fanout_with_empty=offers,parent_cells=owners,kinds=kinds,mapping=mapping,both_new=fresh_two,
                fresh_counts={f'{k}/{v}':n for (k,v),n in fresh_groups.items()},
                productive_fanout=Counter(fan.values()),
                binary_productive_fanout=Counter(n for (_,(_,spec),_),n in fan.items() if len({g for g,_,_ in spec})==2),
                use_by_arity={str(k):dict(Counter(n for (_,spec),n in op_freq.items()
                                                  if len({g for g,_,_ in spec})==k)) for k in owners},
                catalog_by_rule=[[i,*space[i]] for i in range(len(rules))],
                used_rule_ceiling=[sum(space[i][k] for i in used_rules) for k in range(2)],
                catalog_ceiling=list(map(sum,zip(*space))),higher=higher_counts(folder,read(donor_dir/'program.json'),bank,reqs))


def publish(raw,output):
    cases=('sum','dot','fact','loopfact','sum-divisors')
    results={name:read(raw/(name+'.json')) for name in cases}
    freqs={name:data.pop('operator_frequency') for name,data in results.items()}
    catalog={sig for name in cases[:2] for sig,(arity,_) in freqs[name].items() if arity<=2}
    for name,data in results.items():
        f={sig:n for sig,(arity,n) in freqs[name].items() if arity<=2}
        shared=catalog.intersection(f)
        data['frozen_trace_catalog']=dict(size=len(catalog),used=len(shared),
                                         covered_commits=sum(f[sig] for sig in shared),distinct_observed=len(f))
    output.mkdir(exist_ok=True,parents=True)
    (output/'summary.json').write_text(json.dumps(results,indent=2)+'\n')
    (output/'frequencies.json.gz').write_bytes(gzip.compress(json.dumps(freqs,sort_keys=True).encode(),mtime=0))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('folder','donor','bank','output'):p.add_argument(k,type=Path)
    a=p.parse_args()
    a.output.write_text(json.dumps(measure(a.folder,a.donor,a.bank),indent=2)+'\n')
