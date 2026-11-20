"""Eight-slot fixed-trace audit. Census is diagnostic only; it cannot enter a policy or earn RHS credit."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import numpy as np

def read(p):return json.loads(p.read_bytes())
def owner(leaf,addr):return (addr*0x9e3779b1+leaf*0x85ebca77)%2

def optimum(actions,per_owner):
    cbc=shutil.which('cbc') or '/opt/homebrew/opt/cbc/bin/cbc'
    actions=sorted(actions);rows=defaultdict(list)
    for i,(epoch,leaf,addr,root,child) in enumerate(actions):
        var=f'x{i}'
        rows[('slot',epoch,owner(leaf,addr) if per_owner else 0)].append(var)
        rows[('task',epoch,leaf,addr)].append(var)
        rows[('ordinal',root)].append(var)
        if child:rows[('ordinal',child)].append(var)
    scale=len(actions)+1
    lines=['Maximize','win: '+' + '.join(f'{scale*(1+int(a[4]>0))-1} x{i}' for i,a in enumerate(actions)),'Subject To']
    for i,(key,vs) in enumerate(rows.items()):
        cap=(4 if per_owner else 8) if key[0]=='slot' else 1
        lines.append(f'g{i}: '+' + '.join(vs)+f' <= {cap}')
    lines+=['Binary',' '.join(f'x{i}' for i in range(len(actions))),'End']
    with tempfile.TemporaryDirectory() as t:
        model=Path(t)/'cover.lp';sol=Path(t)/'out.sol';model.write_text('\n'.join(lines))
        subprocess.run([cbc,str(model),'-ratio','0','-solve','-solution',str(sol)],capture_output=True,check=True)
        values=sol.read_text().splitlines()
    assert values[0].startswith('Optimal - objective value')
    selected=[actions[int(v[1][1:])] for line in values[1:] if (v:=line.split())[1].startswith('x') and float(v[2])>.5]
    ords=[x for *_,r,c in selected for x in (r,c) if x]
    assert len(set(ords))==len(ords) and scale*len(ords)-len(selected)==round(float(values[0].split()[-1]))
    counts=Counter((t,owner(l,a) if per_owner else 0) for t,l,a,_,_ in selected)
    assert max(counts.values())<=(4 if per_owner else 8)
    assert len({(epoch,leaf,addr) for epoch,leaf,addr,_,_ in selected})==len(selected)
    return dict(distinct=len(ords),roots=len(selected),children=len(ords)-len(selected))

def census(exp,work,n,program,plan):
    dest=work/f'{n}-census'
    if not (dest/'report.json').exists():
        work.mkdir(parents=True,exist_ok=True);p=work/f'{n}-plan.json'
        cfg=dict(plan);cfg.pop('schedule',None);p.write_text(json.dumps(cfg))
        subprocess.run([exp/'coverage-denominator-v1/reward-runtime','--program',program,'--output',dest,
                        '--action-policy',p,'--action-kind','census','--action-observe','--audit-events'],
                       stdout=subprocess.DEVNULL,check=True)
    reference=exp/'row-cpu-grants-v1/paired'/f'{n}-exact'
    for field in ('rhs','resumes','writes','state'):
        assert read(dest/f'{field}.json')==read(reference/f'{field}.json')
    return read(dest/'report.json')['action_units']

def audit(exp,work,n):
    anchor=n in ('sum-bits','dot-product');ref=exp/'pass3-atlas-integration-20261120'
    program=ref/n/'program.json' if anchor else exp/'repair-bake-families-20261120'/n/'program.json'
    plan=read(exp/'row-cpu-grants-v1/paired'/f'{n}-1703-2x4-static.json')
    entries=plan['entries'];joins={(l,e,r) for _,l,e,r in plan['joins']};can_extend={l for l,_,_ in joins}
    c=census(exp,work,n,program,plan);valid={};winners={}
    for epoch,_,leaf,_,addr,_,root,_,_,checked,_ in c['issued']:
        if checked:valid[epoch,leaf,addr]=root
        if root:
            assert checked and root not in winners;winners[root]=(epoch,leaf,addr)
    # Conservative native upper: each verified candidate might win its root, and
    # a compatible left leaf is allowed one additional successful future child.
    # Overlap/versions can only reduce that count on this frozen native source path.
    optimistic={}
    for owned in (False,True):
        groups=defaultdict(list);slots=4 if owned else 8
        for epoch,leaf,addr in valid:groups[epoch,owner(leaf,addr) if owned else 0].append(1+int(leaf in can_extend))
        optimistic['static' if owned else 'free']=sum(sum(sorted(v,reverse=True)[:slots]) for v in groups.values())
    actions={(*loc,ordinal,0) for ordinal,loc in winners.items()}
    cap=exp/'recurrent-compositions-20261120'/n
    with np.load(cap/'output.npz') as z,np.load(cap/'neural-inputs.npz') as a:
        rhs=z['rhs'];pub=a['publications'];tickets=a['consumed'];piv=a['pivot']
    right={(r,p):i for i,(r,p,t) in enumerate(entries) if r>=0}
    for ix,t in enumerate(tickets):
        if not t:continue
        root,eff,_,_=map(int,pub[t-1]);child=ix+1
        if root not in winners:continue
        epoch,l,addr=winners[root];r=right.get((int(rhs[ix,1]),int(piv[ix])-1))
        if (l,eff,r) in joins and int(rhs[root-1,0])==epoch:
            assert epoch<int(rhs[ix,0]) and root<child
            actions.add((epoch,l,addr,root,child))
    # Supplement the cross-backend reference links with actually awarded native
    # arms, including alternative parent provenances in an otherwise identical RHS.
    results={};observed=set();prices=read(Path(__file__).with_name('calibration.json'))['net_us']
    rule_sizes=read(program)['recipe']['rules']
    ready=read(Path(__file__).with_name('results.json'))
    for seed in (1703,1709):
        for arm in ('supervised','team','weighted','weighted_cf'):
            info=read(exp/'native-row-reward-study-v1'/f'{n}-{seed}-{arm}'/'report.json')['action_units']
            used=set();one=two=0
            for epoch,slot,leaf,_,addr,_,root,child,_,ok,cok in info['issued']:
                assert slot%2==owner(leaf,addr)
                if not root:assert not child;continue
                assert ok and (epoch,leaf,addr) in valid and root not in used
                used.add(root);observed.add((epoch,leaf,addr,root,0))
                if len(rule_sizes[entries[leaf][0]]['query'])==1:one+=1
                else:two+=1
                if child:
                    assert cok and child not in used;used.add(child)
                    observed.add((epoch,leaf,addr,root,child))
            m=ready[f'{n}/{seed}'][arm]
            assert len(used)==m['neural'] and one+two==m['roots']
            price=min(0.,prices[2])*len(info['issued'])+prices[3]*one+prices[4]*two+prices[5]*m['children']
            results[f'{seed}/{arm}']=dict(roots=m['roots'],children=m['children'],distinct=len(used),
                    action_dependent_price_us=round(price,2),measured_ms=m['median_ms'])
    actions|=observed
    return dict(native_valid_tasks=len(valid),native_winning_roots=len(winners),source_rhs=len(rhs),
                source_reference_root_actions=sum(a[4]==0 for a in actions),source_reference_macro_actions=sum(a[4]>0 for a in actions),
                conservative_ceiling=optimistic,fixed_trace_oracle={k:optimum(actions,o) for k,o in [('free',False),('static',True)]},
                demonstrated_static_lower=max(v['distinct'] for v in results.values()),policies=results)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('experiments',type=Path);p.add_argument('scratch',type=Path);args=p.parse_args()
    print(json.dumps({n:audit(args.experiments,args.scratch,n) for n in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax')},indent=1))
