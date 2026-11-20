"""Perfect catalog admission on the two previously audited GPU source traces."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

GPU=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(GPU))
from run import execute
from events_audit import align
from endpoint import endpoint

def read(p):return json.loads(p.read_bytes())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def plans(ref,case,donor):
    program=read(ref/case/'program.json')
    catalog=read(ref/donor/'program.json')
    certs=catalog.get('spine_blocks',{}).get('entries',[])
    folder=ref/f'release-input-{case}';packet=read(folder/'ingress.json')
    with np.load(folder/'device.npz') as z:rom=z['rom']
    layout=read(folder/'device.json')['layout']
    depth=layout['DEPTH'];entries=[-1]*(len(packet['rules'])*depth);ids=[];pivots=entries.copy();tables=[0]*len(packet['tables'])
    for i,e in enumerate(certs):
        r,p=e['consumer'],e['pivot']
        # Cross-program transfer requires the same typed rule (including RHS),
        # same table schemas and target's own exhaustive Stage Entry.
        assert catalog['recipe']['tables']==program['recipe']['tables']
        if catalog['recipe']['rules'][r]!=program['recipe']['rules'][r]:continue
        matches=[s for s in packet['stage_entries'] if s['rule']==r and s['anchor']==p]
        assert len(matches)==1
        op,args=packet['rules'][r]['q'][p]
        assert isinstance(op,int)
        rule=rom[layout['RULE']+7*r:][:7];matches=[]
        for j in range(rule[0]):
            t,w,offset,_=rom[rule[1]+4*j:][:4]
            if t==op and rom[offset:offset+w].tolist()==args:matches.append(j)
        if len(matches)!=1:raise ValueError('cannot uniquely recover physical pivot')
        index=r*depth+matches[0]
        assert entries[index]<0
        tables[op]=1;pivots[r*depth+p]=len(ids);entries[index]=len(ids);ids.append([i,r,p])
    report=read(ref/f'oracle-{case}'/'report.json')
    assert program['sha256']==report['program_sha256']
    c=report['repair_cells']['catalog']
    assert c['recipe']==program['recipe']['sha256']
    # Use the actual archived scalar-constructor schema catalog. Do not assign
    # a historical single-position variant by coincident table or template IDs.
    shapes=[-1 if x is None else x for x in c['tables']]
    assert all(len(c['shapes'][x]['schema'])==len(t['schema']) and c['shapes'][x]['schema']==t['schema']
               for x,t in zip(shapes,program['recipe']['tables']) if x>=0)
    return dict(entries=entries,ids=ids,shapes=shapes,pivots=pivots,tables=tables),{'program_sha256':program['sha256'],'donor_sha256':catalog['sha256'],
        'native_leaves':len(program.get('spine_blocks',{}).get('entries',[])), 'admitted_leaves':len(ids),
        'native_composed_states':len(program.get('iterative_bake',{}).get('rhs_handoffs',{}).get('states',[])),
        'repair_tables':sum(x>=0 for x in shapes),'repair_shapes':len(set(shapes)-{-1}),
        'applied_units':report['stage_spine'].get('iterative_bake',{}).get('applied_units',{})}

def replay(ref,weights,out):
    out.mkdir(parents=True,exist_ok=False);report={}
    for case in ('sum-bits','dot-product'):
        image=ref/f'release-input-{case}';oracle=ref/f'oracle-{case}'
        plan,info=plans(ref,case,'sum-bits')
        reference=ref/f'release-{case}'
        runs=read(reference/'check.json')['completed'];assert read(reference/'check.json')['acceptance']=='pass'
        records={}
        for label,select,notify in [('tally',False,False),('selected',True,False),('notified',True,True)]:
            dest=out/f'{case}-{label}'
            execute(image/'device.json',weights,ref/'ports-1703.pt',2048,2,dest,count_work=True,
                    block_study=dict(plan,select=select,notify=notify))
            ordered=align(ref/case/'program.json',image/'ingress.json',dest,oracle,ref/f'events-lifecycle-{case}')
            path=dest/'ordered.json';path.write_text(json.dumps(ordered))
            audit=endpoint(image/'ingress.json',dest,oracle,path)
            assert audit['acceptance']=='pass' and audit['completed']==runs
            state=read(dest/'run.json')['state']
            with np.load(dest/'output.npz') as device:
                outcomes=device['block_coverage'][:,:2]
                assert np.array_equal(outcomes.sum(axis=1),device['runs'][:,1])
                nonempty=outcomes.sum(axis=1)>0
                only=int(((outcomes[:,0]==0)&nonempty).sum())
                own=int(outcomes[:,1].sum())
            leaves=len(plan['ids']);shape_offset=88+3*leaves
            records[label]=dict(whole_nonempty_candidate_runs=only,nonempty_runs=int(nonempty.sum()),covered_tokens=own,
                shape_clean=state[shape_offset::2],shape_dirty=state[shape_offset+1::2],dfs=state[54],repair_scan=state[55],boundaries=state[69],eligible_scan=state[70],
                changed=state[71],key_changed=state[72],subscriptions=state[73],notification_words=state[74],
                dispatch_mask_tests=state[75],outside_scan=state[76],cursor_refreshes=state[77],cursor_heads=state[78],route_visits=state[79],credits=state[88:88+len(plan['ids'])],
                leaf_route_visits=state[88+len(plan['ids']):88+2*len(plan['ids'])],live_route_visits=state[88+2*leaves:shape_offset],
                aligned=audit['ordered_exact'],final=audit['full_typed_graph_equal'],spine=audit['gpu_continuations'])
        base,chosen,index=(records[k] for k in ('tally','selected','notified'))
        saved=base['dfs']-chosen['dfs']; assert saved==sum(base['credits']) and chosen['dfs']==index['dfs']
        assert base['repair_scan']==base['eligible_scan']+base['outside_scan']
        assert base['changed']==index['changed'] and base['outside_scan']==index['outside_scan']
        ceiling=base['eligible_scan']-base['changed'];actual=base['repair_scan']-index['repair_scan']
        assert 0<=actual<=ceiling
        route_bound=sum(base['leaf_route_visits'])-sum(base['live_route_visits'])
        route_saved=base['route_visits']-chosen['route_visits']
        assert base['live_route_visits']==chosen['live_route_visits'] and 0<=route_saved<=route_bound
        assert sum(base['shape_clean'])==ceiling and sum(base['shape_dirty'])==base['changed']
        cpu=read(ref/f'oracle-{case}/report.json')
        terminals={str(s['unit']):s['program'] for s in read(ref/case/'program.json').get('iterative_bake',{}).get('rhs_handoffs',{}).get('states',[])}
        info['local_compositions']=dict(hits=sum(v for k,v in info['applied_units'].items() if int(k)>=info['native_leaves']),
            states_with_query_receipts=sum(bool(p.get('queries')) for p in terminals.values()),
            source_rhs_handoffs={k:cpu['stats'][k] for k in ('handoff_attempts','handoff_closed','handoff_closed_fallback','handoff_sets','handoff_lets','handoff_noop_unions')})
        info.update(route_saved=route_saved,route_bound=route_bound,route_total=base['route_visits'],records=records,dfs_saved=saved,dfs_coverage=saved/base['dfs'],
            repair_selection_only_saved=0,repair_with_incidence_ceiling=ceiling,repair_with_incidence_saved=actual,
            live_run_dispatches=3*runs,dispatches_saved=0,source_runs=runs,
            reverse_directory_bytes=(16384//32)*(16384+read(image/'device.json')['layout']['NSYMBOLS']+4)*4,
            credits=[dict(leaf=i,rule=r,pivot=p,avoided_dfs_steps=w,avoided_route_visits=base['leaf_route_visits'][j]-chosen['leaf_route_visits'][j],route_upper=base['leaf_route_visits'][j]-base['live_route_visits'][j]) for j,((i,r,p),w) in enumerate(zip(plan['ids'],base['credits']))],
            gpu_reference_sha256=sha(reference/'output.npz'))
        report[case]=info
        (out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
        print(case,saved,actual,ceiling,flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ('reference','weights','new_output'):parser.add_argument(arg,type=Path)
    a=parser.parse_args();replay(a.reference,a.weights,a.new_output)
