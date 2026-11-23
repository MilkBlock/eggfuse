"""Measure Run-local anchor visibility on the unmodified assisted Actor trajectory."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from capture import execute, inputs, load_catalog, read, verify
from chain_check import serial_compiler


def audit(case, corpus, ref, reader, dest):
    image, program, gold = inputs(corpus, ref, case)
    layout = read(image/'device.json')['layout']
    with np.load(image/'device.npz') as packed:
        rom = packed['rom']
    entries = load_catalog(image, program, ref/'sum-bits/program.json')
    leaves = {(rid,pivot):i for i,(rid,pivot,_,_) in enumerate(entries) if rid>=0}
    from lower import OPCODES
    ingress=read(image/'ingress.json')
    orders={(e['rule'],e['anchor']):[e['anchor'],*e['atoms']] for e in ingress['stage_entries']}
    for rid,rule in enumerate(ingress['rules']):
        n,at=rom[layout['RULE']+7*rid:][:2]
        left=list(range(n))
        order=[]
        for i in range(n):
            op,arity,args,_=rom[at+4*i:at+4*i+4]
            signature=[int(op) if op>=0 else OPCODES[-1-op],rom[args:args+arity].tolist()]
            src=next(k for k in left if rule['q'][k]==signature)
            order.append(src)
            left.remove(src)
        orders[rid,-1]=order
    # A table key or primitive is determined when all its input operands are bound.
    # This upper bound only tests dependencies; the held-out winner supplies existence.
    def one_anchor_suffices(query,pivot):
        bound={v for v in query[pivot][1] if v>=0}
        remaining=set(range(len(query)))-{pivot}
        while remaining:
            ready={i for i in remaining if all(v<0 or v in bound for v in query[i][1][:-1])}
            if not ready:return False
            bound.update(v for i in ready for v in query[i][1] if v>=0)
            remaining-=ready
        return True
    functional={(rid,i) for rid,rule in enumerate(ingress['rules']) for i,(op,_) in enumerate(rule['q'])
                if isinstance(op,int) and one_anchor_suffices(rule['q'],i)}
    catalog_rules={rid for rid,_ in leaves}
    snapshots = {}
    def observe(run,ruleset,rows,marks,tickets):
        if run in snapshots:
            raise ValueError('repeated Run snapshot')
        snapshots[run] = (ruleset,rows,marks,tickets)
    with TemporaryDirectory() as tmp:
        execute(image/'device.json',reader,ref/'ports-1703.pt',2048,2,dest,
                neural=dict(catalog=entries,rows=2,ranks=8,hidden=8,capture=True,
                            capture_edges=True,capture_boundaries=True),
                serial_compile=serial_compiler(Path(tmp)),run_observer=observe)
    verify(dest,gold,image)
    counts=Counter()
    per=defaultdict(Counter)
    reasons=Counter()
    with np.load(dest/'neural-inputs.npz') as obs,np.load(dest/'output.npz') as z:
        old=obs['features']
        if len(snapshots)!=len(z['runs']) or len(obs['pivot'])!=len(z['rhs']) or len(obs['witnesses'])!=len(z['rhs']):
            raise ValueError('incomplete capture')
        for rhs,pivot,proof in zip(z['rhs'],obs['pivot'],obs['witnesses']):
            run,rid=map(int,rhs[:2])
            rs,rows,wm,tickets=snapshots[run]
            size,offset=rom[layout['SETS']+2*rs:][:2]
            if rid not in rom[offset:offset+size]:
                raise ValueError('winner belongs to another ruleset')
            n,at=rom[layout['RULE']+7*rid:][:2]
            witness=[]
            routes=[]
            future_routes=[]
            old_pivot=int(pivot)-1
            order=orders[rid,old_pivot]
            for atom,(encoded,version,ticket) in zip(order,proof[:n]):
                table=ingress['rules'][rid]['q'][atom][0]
                if isinstance(table,str):
                    if encoded:raise ValueError('primitive has row')
                    continue
                row=int(encoded)-1
                if not (0<=row<len(rows) and rows[row,0]==table and rows[row,3]==0 and
                        rows[row,4]==version and tickets[row]==ticket and version<run):
                    raise ValueError(('frozen source witness',run,rid,atom,row,version,ticket))
                fresh=version>=wm[rid]
                witness.append(bool(fresh))
                if fresh and (rid,atom) in functional:future_routes.append(atom)
                leaf=leaves.get((rid,atom))
                if leaf is not None and fresh and ticket:
                    routes.append((atom,row,leaf))
            if (rid,old_pivot) in leaves and not any(atom==old_pivot and row==rhs[3] for atom,row,_ in routes):
                raise ValueError(('source Spine pivot absent',run,rid,old_pivot,int(rhs[3]),routes,proof[:n],int(wm[rid])))
            fixed=any(row in old[run-1,8*leaf:8*leaf+8,0] for atom,row,leaf in routes if atom==old_pivot)
            flags=dict(committed=1,all_table_witnesses_visible=bool(witness),any_delta=any(witness),
                       all_table_witnesses_delta=bool(witness) and all(witness),
                       one_delta_plus_determined_suffix=bool(future_routes),
                       delta_requires_more_independent_inputs=any(witness) and not future_routes,
                       fixed_source_pivot=fixed,delta_source_pivot=(rid,old_pivot) in leaves,
                       delta_any_certified_pivot=bool(routes))
            counts.update(flags)
            per[run].update(flags)
            if not routes:
                if not witness:reason='empty_lhs' if not n else 'no_table_witness'
                elif not any(witness):reason='no_delta'
                elif rid not in catalog_rules:reason='rule_outside_catalog'
                else:
                    eligible=[(i,r) for i,(r,v,_) in enumerate(proof[:n]) if r and v>=wm[rid] and (rid,order[i]) in leaves]
                    reason='no_published_anchor' if eligible else 'no_certified_delta_role'
                reasons[reason]+=1
        if case=='sum-bits' and (counts['committed'],counts['fixed_source_pivot'])!=(7265,742):
            raise ValueError('original sum-bits reference was not reproduced')
    return dict(case=case, backend='serial_cpp_kernel_diagnostic', runs=len(snapshots),
                counts=dict(counts),outside_certified_delta=dict(reasons),
                two_lane_rhs_upper={k:sum(min(2,c[k]) for c in per.values()) for k in
                                    ('fixed_source_pivot','delta_source_pivot','delta_any_certified_pivot','one_delta_plus_determined_suffix','any_delta')})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('corpus','ref','reader','out'):
        p.add_argument(key,type=Path)
    p.add_argument('--case',default='sum-bits')
    a=p.parse_args()
    if a.out.exists():raise FileExistsError(a.out)
    result=audit(a.case,a.corpus,a.ref,a.reader,a.out)
    (a.out/'delta.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
