"""Lower static templates, instance bindings and the nested source schedule to device words."""
from pathlib import Path
from importlib.util import module_from_spec,spec_from_file_location

HERE=Path(__file__).resolve().parent
_spec=spec_from_file_location('pass3_control',HERE.parent/'eggcc-gpu-supervision/full_program.py')
_control=module_from_spec(_spec);_spec.loader.exec_module(_control)
control_code=_control.lower

PRIMS=['!=','%','*','+','-','/','<','<=','>','>=','and','bool-<','max','min','or','eq-id-!=']
SET_PRIMS=['set-empty','set-of','set-insert','set-intersect','set-union','set-length']
OPCODES=PRIMS+SET_PRIMS
EFFECTS=['copy','construct','set','compute','union','subsume','panic']


def compile_image(p):
    rom=[];layout={}
    def words(xs):
        at=len(rom);rom.extend(xs);return at
    def section(name,xs):layout[name]=words(xs)
    tables=p['tables'];names={t['name']:i for i,t in enumerate(tables)}
    def merge(t):
        expr=t['merge_expr']
        if expr is None:return 0
        if expr.get('var') in ('old','new'):return 1 if expr['var']=='old' else 2
        if expr.get('call',{}).get('table'):
            if expr['args']!=[{'var':'old'},{'var':'new'}]:raise ValueError(expr)
            return 16+names[expr['call']['table']]
        return {'(min old new)':3,'(max old new)':4,'(max 1 (min old new))':5}[t['merge']]
    section('TABLE',[v for t in tables for v in [len(t['schema']),int(t['kind']=='constructor'),merge(t),
             sum(1<<j for j,s in enumerate(t['schema']) if s['kind']=='eq')]])
    sm=[]
    for t in p['templates']:
        start=[]
        for tab,cols in t:start.extend([tab,len(cols),words(cols)])
        sm.extend((len(t),words(start)))
    section('TEMPLATE',sm)
    data=[]
    for tid,params,hidden in p['instances']:
        data.extend((tid,words(params),sum(h<<i for i,h in enumerate(hidden))))
    section('INSTANCE',data)
    strings=sorted({v['value'] for v in p['symbols'] if v['sort']=='String'})
    string_ids={v:i for i,v in enumerate(strings)}
    has_sets=any('elements' in v for v in p['symbols']) or any(
        op in SET_PRIMS for r in p['rules'] for op in [*(a[0] for a in r['q']),*(e[1] for e in r['e'])])
    seed_ids=[]
    if has_sets:
        layout['HAS_SETS']=1
        section('SET_COLS',[sum(1<<i for i,s in enumerate(t['schema']) if s['kind']=='set') for t in tables])
        section('SET_INPUTS',[sum(1<<i for i in r.get('set_inputs',[])) for r in p['rules']])
        if any(i>=31 for r in p['rules'] for i in r.get('set_inputs',[])):raise ValueError("set input index exceeds device mask")
        identities={(v['sort'],v['eq']):rank for v,rank in zip(p['symbols'],p['eq_order']) if 'eq' in v}
        seed_ids=sorted({identities[x['sort'],x['eq']] for v in p['symbols'] for x in v.get('elements',[])})
        if len(seed_ids)>63:raise ValueError("set member dictionary exceeds device capacity")
        section('SET_SEEDS',seed_ids);layout['NSET_SEEDS']=len(seed_ids)
    def scalar(i,v):
        if 'eq' in v:return p['eq_order'][i]
        if v['sort']=='String':return string_ids[v['value']]
        if 'elements' in v:return sum(1<<i for i in {seed_ids.index(identities[x['sort'],x['eq']]) for x in v['elements']})
        return int(v['value'])
    literals=[scalar(i,v) for i,v in enumerate(p['symbols'])]
    routes_by_rule=[[] for _ in p['rules']]
    for entry in p['stage_entries']:routes_by_rule[entry['rule']].append(entry)
    demanded={names[e['table']] for e in p['stage_entries']}
    section('DEMANDED',[int(t in demanded) for t in range(len(tables))])
    rules=[];routes=[]
    for rid,r in enumerate(p['rules']):
        seen=set();pending=list(enumerate(r['q']));atoms=[];order=[]
        while pending:
            choices=[]
            for j,(_, (op,args)) in enumerate(pending):
                known=[v<0 or v in seen for v in args]
                if isinstance(op,str) and not all(known[:-1]):continue
                choices.append((int(isinstance(op,str) or all(known[:-1])),sum(known),-j))
            if not choices:raise ValueError(('ungrounded primitive',rid))
            j=-max(choices)[2];source,(op,args)=pending.pop(j);order.append(source)
            flags=0
            for k,v in enumerate(args):
                if v>=0 and v not in seen:flags|=1<<k;seen.add(v)
            f=op if isinstance(op,int) else -1-OPCODES.index(op)
            atoms.extend([f,len(args),words(args),flags])
        entries=routes_by_rule[rid];pairs=[];covered=0
        for entry in entries:
            pivot=entry['anchor'];ops=[];bound=set()
            schedule=[pivot,*entry['atoms']]
            if sorted(schedule)!=list(range(len(r['q']))):raise ValueError('incomplete Cell entry')
            covered|=1<<order.index(pivot)
            for pos,qi in enumerate(schedule):
                call,args=r['q'][qi]
                if pos and any(x>=0 and x not in bound for x in args[:-1]):
                    raise ValueError('nonfunctional Cell step')
                flag=0
                for j,x in enumerate(args):
                    if x>=0 and x not in bound:bound.add(x);flag|=1<<j
                ops.extend([call if isinstance(call,int) else -1-OPCODES.index(call),len(args),words(args),flag])
            pairs.extend([pivot,words(ops)])
        produces=any(op in ('construct','set') and t in demanded for op,t,_,_ in r['e'])
        routes.extend([len(entries),words(pairs),covered,int(produces)])
        query=words(atoms);effects=[]
        for kind,fn,dst,args in r['e']:
            fn=fn if isinstance(fn,int) else OPCODES.index(fn)
            effects.extend([EFFECTS.index(kind),fn,dst,len(args),words(args)])
        rules.extend([len(r['q']),query,len(r['e']),words(effects),len(r['inputs']),words(r['inputs']),int(r['semi'])])
    section('RULE',rules);section('SPINE',routes)
    offsets=[];total=0
    for rule in p['rules']:
        offsets.append(total);total+=len(rule['inputs'])+5
    section('TOKEN_BASE',offsets);layout['TOTAL_TOKEN_COLS']=total
    sets=list(p['sets']);sr=[]
    for name in sets:sr.extend([len(p['sets'][name]),words(p['sets'][name])])
    section('SETS',sr)
    bytecode,reg=control_code(p['control'],p['sets'])
    ctrl=[]
    for ins in bytecode:
        op=ins['op']
        if op=='run':v=[0,sets.index(ins['ruleset']),0,0]
        if op=='save_epoch':v=[1,ins['slot'],0,0]
        if op=='repeat_if_changed':v=[2,ins['slot'],ins['target'],0]
        if op=='counter':v=[3,ins['slot'],ins['count'],0]
        if op=='decrement_jump':v=[4,ins['slot'],ins['epoch_slot'],ins['target']]
        ctrl+=v
    section('CONTROL',ctrl)
    layout.update(TABLES=len(tables),RULES=len(p['rules']),NINST=len(p['instances']),
        NSYMBOLS=len(literals),NCTRL=len(bytecode),REGS=reg,MAXSLOTS=max(r['n'] for r in p['rules']),
        WIDTH=max(len(t['schema']) for t in tables),DEPTH=max(len(r['q']) for r in p['rules'])+1,
        NINPUT=max(len(r['inputs']) for r in p['rules']))
    return rom,literals,layout,sets,strings


def save_device_image(packet,destination):
    import hashlib
    import json
    import numpy as np
    p=json.loads(packet.read_text());rom,lits,layout,sets,strings=compile_image(p)
    if layout['WIDTH']>30 or layout['DEPTH']>31:raise ValueError('typed port mask exceeds the Metal ABI')
    # Resolve the negative internal link only at read time. The compressed slot
    # program and instance parameters are the sole source of initial fact contents.
    queries=[];widths=[];starts=[];addresses=[];member_coords=[]
    for ti,template in enumerate(p['templates']):
        ops=rom[layout['TEMPLATE']+2*ti+1]
        for j,(_,fields) in enumerate(template):
            off=rom[ops+3*j+2];n=len(fields)
            for k in range(n):
                widths.append(n);queries.append(k if k<n-1 else -1);starts.append(off);addresses.append(off+k)
    for cell,(ti,params,hidden) in enumerate(p['instances']):
        for op in range(len(p['templates'][ti])):member_coords.append((cell,op))
    sort_ids={sort:i for i,sort in enumerate(sorted({v['sort'] for v in p['symbols']}))}
    eq_sort=[sort_ids[v['sort']] if 'eq' in v else -1 for v in p['symbols']]
    arrays=destination/'device.npz'
    np.savez_compressed(arrays,physical_order=np.random.default_rng(181).permutation(len(p['instances'])).astype(np.int32),eq_sort=np.asarray(eq_sort,np.int32),rom=np.asarray(rom,np.int32),lits=np.asarray(lits,np.int64),
        role_width=np.asarray(widths,np.int32),role_query=np.asarray(queries,np.int32),
        role_base=np.asarray(starts,np.int32),role_dst=np.asarray(addresses,np.int32),members=np.asarray(member_coords,np.int32))
    spec=dict(schema='eggfuse.gpu-ingress/1',layout=layout,sets=sets,strings=strings,packet_sha256=hashlib.sha256(packet.read_bytes()).hexdigest(),
              device_sha256=hashlib.sha256(arrays.read_bytes()).hexdigest(),max_set=max(map(len,p['sets'].values())))
    from export_graph import schema_for
    schema_path=destination/'export-schema.json'
    schema_path.write_text(json.dumps(schema_for(p),separators=(',',':'))+'\n')
    spec['export_schema_sha256']=hashlib.sha256(schema_path.read_bytes()).hexdigest()
    (destination/'device.json').write_text(json.dumps(spec,separators=(',',':'))+'\n')


if __name__=='__main__':
    import argparse
    q=argparse.ArgumentParser();q.add_argument('packet',type=Path);a=q.parse_args()
    save_device_image(a.packet,a.packet.parent)
