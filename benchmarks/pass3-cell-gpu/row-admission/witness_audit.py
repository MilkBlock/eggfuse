"""Find actual shared-key parents, duplicate row issues, and an independent reader of a macro port."""
import argparse,json
from collections import defaultdict
from pathlib import Path
import numpy as np

def read(p):return json.loads(p.read_bytes())
def fact(w):
    if w and 'Fact' in w:
        f=w['Fact'];return f['cell'],f['op']
    return None

def audit(exp,case):
    base=exp/'row-cpu-grants-v1/paired'
    anchor=case in ('sum-bits','dot-product')
    obs=exp/'repair-bake-families-20261120'/case/'observation'
    packet=read((exp/'pass3-atlas-integration-20261120'/f'release-input-{case}' if anchor else obs.parent/'input')/'ingress.json')
    with np.load(exp/'recurrent-compositions-20261120'/case/'output.npz') as z:rhs=z['rhs']
    events=read(obs/'events.json')
    by_fact=defaultdict(list);same_key=None;duplicate=None;boundary=None
    for run,changes in enumerate(events,1):
        for ev in changes:
            if ev[0]!='displaced':continue
            losing,kept,affected=ev[1:4]
            external=[(fact(w),t,cols) for w,t,cols in affected if fact(w)]
            for owner,t,cols in external:
                last=len(packet['tables'][t]['schema'])-1
                if last not in cols:continue
                others=[(p,table,k) for p,table,k in external if p[0]!=owner[0] and any(c<len(packet['tables'][table]['schema'])-1 for c in k)]
                if others:by_fact[owner].append((run,losing,kept,others[0]))
    for seed in (1703,1709):
        for mode in ('free','free_once','static','transfer'):
            stem=f'{case}-{seed}-2x4-{mode}'
            plan=read(base/f'{stem}.json');a=read(base/stem/'report.json')['action_units'];seen={};raw=defaultdict(list)
            entries=plan['entries'];joins={u:(l,o,r) for u,l,o,r in plan['joins']}
            for i,v in enumerate(a['issued']):
                epoch,slot,leaf,unit,addr,_,root,child,child_epoch,verified,child_verified=v
                rid,pivot,_=entries[leaf];site=(epoch,slot//2,leaf,addr)
                if duplicate is None and site in seen and seen[site][0]%2!=slot%2:
                    duplicate=dict(arm=stem,run=epoch,wave=slot//2,leaf=leaf,address=addr,slots=[seen[site][0],slot],units=[seen[site][1],unit],root_ordinals=[seen[site][2],root])
                seen[site]=(slot,unit,root)
                if not root:continue
                assert verified and tuple(rhs[root-1,:2])==(epoch,rid)
                rule=packet['rules'][rid];q=rule['q'];args=q[pivot][1]
                shared={s for j,(op,row) in enumerate(q) if j!=pivot and isinstance(op,int) for s in row if s>=0}
                slices=[(j,s) for j,s in enumerate(args) if s in shared and s in rule['inputs']]
                if not slices:continue
                vals=dict(zip(rule['inputs'],map(int,rhs[root-1,4:])))
                key=tuple((j,vals[s]) for j,s in slices)
                raw[epoch,leaf,key].append((slot,addr,root))
            if same_key is None:
                for (epoch,leaf,key),grp in raw.items():
                    hits=next(((a,b) for a in grp for b in grp if a[1]!=b[1] and a[0]%2!=b[0]%2),None)
                    if hits:
                        same_key=dict(arm=stem,run=epoch,leaf=leaf,rule=entries[leaf][0],shared_columns_values=key,
                                      slot_address_rhs=hits);break
            if boundary is None:
                for i,source,pub in a['provenance']:
                    v=a['issued'][i];epoch,slot,leaf,unit,addr,_,root,child,ce,ok,cok=v
                    assert ok and cok and root<child and unit in joins
                    for when,lose,keep,(peer,table,columns) in by_fact.get(fact(pub),()):
                        if when<ce:continue
                        boundary=dict(arm=stem,source_run=epoch,slot=slot,root_rhs=root,macro_unit=unit,
                            producer_effect=joins[unit][1],producer_anchor=source,actual_parent_port=pub,
                            child_run=ce,child_rhs=child,union_run=when,union=[lose,keep],outside_cell_op=peer,
                            outside_table=packet['tables'][table]['name'],outside_key_columns=columns)
                        break
                    if boundary:break
    if same_key and anchor:
        recorded=read(exp/'pass3-atlas-integration-20261120'/f'oracle-{case}'/'binding-audit.json')
        ordered=[b for r in recorded['runs'] for b in r['bindings']]
        values=[]
        for _,_,ordinal in same_key['slot_address_rhs']:
            b=ordered[ordinal-1];assert b['rule']==same_key['rule']
            rule=packet['rules'][b['rule']];pivot=entries[same_key['leaf']][1]
            slot=rule['q'][pivot][1][same_key['shared_columns_values'][0][0]]
            values.append(next(v['value'] for v in b['values'] if v['slot']==slot))
        assert values[0]==values[1];same_key['native_shared_argument']=values[0]
    return dict(two_rows_same_task=duplicate,same_join_key_distinct_parent=same_key,macro_port_with_external_reader=boundary)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('experiments',type=Path);a=p.parse_args()
    results={case:audit(a.experiments,case) for case in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax')}
    assert any(v['same_join_key_distinct_parent'] for v in results.values()) and any(v['two_rows_same_task'] for v in results.values())
    print(json.dumps(results,indent=1))
