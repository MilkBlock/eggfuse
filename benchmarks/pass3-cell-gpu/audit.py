"""Post-run comparison. The executor does not import this module or open an oracle."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import numpy as np
from codec import canonical,members


def snapshots(path):
    decoder=json.JSONDecoder()
    with path.open() as f:
        buf=''
        while True:
            if not buf:
                buf=f.read(1<<19)
                if not buf:return
            buf=buf.lstrip(' \r\n\t,[')
            if buf.startswith(']'):return
            try:record,end=decoder.raw_decode(buf)
            except json.JSONDecodeError:
                more=f.read(1<<19)
                if not more:raise
                buf+=more;continue
            yield record
            buf=buf[end:]


def digest(items):
    h=hashlib.sha256()
    for item in items:
        h.update(json.dumps(item,ensure_ascii=False,separators=(',',':')).encode())
    return h.hexdigest()


def typed(spec,v,eq,strings,set_members=(),root=None):
    n=spec['name'];k=spec['kind'];v=int(v)
    if k=='eq':return dict(eq=eq[n,v],sort=n)
    if k=='set':
        if v<0 or v.bit_length()>len(set_members):raise ValueError('unknown set bits')
        elem=spec['element']['name']
        members=[eq[elem,root(int(x))] for i,x in enumerate(set_members) if v&(1<<i)]
        if len(set(members))!=len(members):raise ValueError('duplicate set element in device export')
        return dict(sort=n,elements=[dict(sort=elem,eq=x) for x in sorted(members,key=lambda x:int(x[5:-1]))])
    if k=='String':return dict(sort=n,value=strings[v])
    if k=='bool':return dict(sort=n,value=bool(v))
    if k in ('i64','Unit','f64'):return dict(sort=n,value=v)
    raise ValueError(spec)


def internal(v,spec):
    k=spec['kind']
    if k=='eq':return {'Eq':int(v['eq'].removeprefix('Cell(').removesuffix(')'))}
    if k=='set':return {'Set':[internal(x,spec['element']) for x in v['elements']]}
    if k=='String':return {'Text':v['value']}
    if k=='f64':return {'Float':v['value']}
    return {'Int':int(v['value'])}


def graph(rows,meta,ref,p,strings,parents,set_members=()):
    keep=meta[:,3]!=2
    rows=rows[keep];meta=meta[keep]
    def root(v):
        while parents[v]:v=int(parents[v])
        return v
    anchors={(x['sort'],x['old']):x['now'] for x in ref['anchors']}
    eq={}
    for i,v in enumerate(p['symbols']):
        if 'eq' in v:
            key=(v['sort'],root(p['eq_order'][i]))
            assert eq.setdefault(key,anchors[v['sort'],v['eq']])==anchors[v['sort'],v['eq']],'anchor partition changed'
    tables=p['tables']
    keys={(r['table'],canonical(r['values'][:-1])):r for r in ref['rows']}
    for _ in range(len(rows)+1):
        progress=False
        for line,m in zip(rows,meta):
            t=tables[m[0]];schema=t['schema']
            if t['kind']!='constructor':continue
            key=(schema[-1]['name'],int(line[len(schema)-1]))
            if key in eq:continue
            try:vals=[typed(s,v,eq,strings,set_members,root) for s,v in zip(schema[:-1],line)]
            except KeyError:continue
            witness=keys.get((t['name'],canonical(vals)))
            if witness is not None:
                eq[key]=witness['values'][-1]['eq'];progress=True
        if not progress:break
    translated=[]
    for line,m in zip(rows,meta):
        t=tables[m[0]]
        translated.append(dict(table=t['name'],subsumed=bool(m[3]),
                               values=[typed(s,v,eq,strings,set_members,root) for s,v in zip(t['schema'],line)]))
    assert len(set((sort,x) for (sort,_),x in eq.items()))==len(eq),'class map is not injective'
    return eq,Counter(map(canonical,translated))==Counter(map(canonical,ref['rows']))


def audit(program,packet,output,oracle):
    raw=json.loads(program.read_text());p=json.loads(packet.read_text());run=json.loads((output/'run.json').read_text())
    assert p['program_sha256']==hashlib.sha256(program.read_bytes()).hexdigest()
    decoded=list(members(p));assert Counter(canonical(v) for _,_,v in decoded)==Counter(map(canonical,raw['initial']))
    first=json.loads((oracle/'binding-audit.json').read_text())
    ref_rhs=json.loads((oracle/'rhs.json').read_text());ref_writes=json.loads((oracle/'writes.json').read_text())
    resumes=json.loads((oracle/'resumes.json').read_text())
    separate=json.loads((oracle/'report.json').read_text())['steps']
    streams=snapshots(oracle/'stages.json');results=[]
    function_ids={};next_func=sum(1 for _,_,row in decoded if next(t for t in p['tables'] if t['name']==row['table'])['kind']=='function')
    prior_func={}
    with np.load(output/'snapshots.npz') as states,np.load(output/'output.npz') as z:
        bits=z.get('set_members',())
        def resolver(parents):
            def root(v):
                while parents[v]:v=int(parents[v])
                return v
            return root
        eq,ok=graph(states['rows_0'],states['meta_0'],first['initial'],p,run['strings'],states['parents_0'],bits);assert ok
        rhs,writes=z['rhs'],z['writes']
        for i,stats in enumerate(z['runs']):
            before=eq;ref=next(streams);n=i+1
            try:eq,exact=graph(states[f'rows_{n}'],states[f'meta_{n}'],ref,p,run['strings'],states[f'parents_{n}'],bits)
            except KeyError:results.append(dict(run=n,set=run['sets'][stats[0]],graph=False));break
            trace=rhs[rhs[:,0]==n];rhs_items=[];events=[];lanes=[0,0]
            for entry in trace:
                rid=int(entry[1]);slots=raw['recipe']['rules'][rid]['slots'];values={}
                for j,slot in enumerate(p['rules'][rid]['inputs']):
                    spec=slots[slot]['sort'];values[str(slot)]=internal(typed(spec,entry[4+j],before,run['strings'],bits,resolver(states[f'parents_{n-1}'])),spec)
                rhs_items.append([rid,values]);lanes[int(entry[2])]+=1
            # The device records the source RHS ordinal before function publication.
            for entry in writes[writes[:,0]==n]:
                rid,table,row=map(int,entry[1:4]);schema=p['tables'][table]['schema']
                args=[internal(typed(s,v,eq,run['strings'],bits,resolver(states[f'parents_{n}'])),s) for s,v in zip(schema,entry[4:])]
                if row not in function_ids:function_ids[row]=next_func;next_func+=1
                ordinal=int(entry[-1])
                events.append([n,[ordinal,rid],table,function_ids[row],args[:-1],prior_func.get(row),args[-1]])
                prior_func[row]=args[-1]
            truth=[]
            for binding in first['runs'][i]['bindings']:
                rid=binding['rule'];slots=raw['recipe']['rules'][rid]['slots']
                vals={str(t['slot']):internal(t['value'],slots[t['slot']]['sort']) for t in binding['values']}
                truth.append([rid,vals])
            results.append(dict(rhs_set=Counter(map(canonical,truth))==Counter(map(canonical,rhs_items)),run=n,set=run['sets'][stats[0]],schedule=run['sets'][stats[0]]==separate[i]['ruleset']
                                and bool(stats[3])==separate[i]['changed'],graph=exact,
                                rhs=digest(rhs_items)==ref_rhs[i],writes=[len(events),digest(events)]==ref_writes[i],
                                spine_empty_ref=resumes[i][0]==0,reference_resumes=resumes[i][0],lane_tokens=lanes,
                                distinct=len({canonical(v) for v in rhs_items})==len(trace),facts=len(ref['rows'])))
    return dict(initial_exact=ok,initial_rows=len(decoded),runs=results)


if __name__=='__main__':
    q=argparse.ArgumentParser()
    for k in ('program','packet','gpu','oracle','out'):q.add_argument(k,type=Path)
    a=q.parse_args();result=audit(a.program,a.packet,a.gpu,a.oracle)
    a.out.write_text(json.dumps(result,indent=1)+'\n')
