"""Native training windows, exact root outcomes and source-calibrated phase costs. No evaluation families."""
import argparse,json,sys,subprocess
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'action-granularity'))
from export import compile_plan,read


def run(binary,prog,folder,plan=None,kind='macro',capture=False):
    args=[binary,'--program',prog,'--output',folder]
    if plan:args+=['--action-policy',plan,'--action-kind',kind]
    if capture:args+=['--action-observe','--audit-events']
    subprocess.run(args,check=True,stdout=subprocess.DEVNULL)
    return read(folder/'report.json')


def main(a):
    a.out.mkdir(parents=True,exist_ok=False)
    names=[n for n,c in read(a.corpus/'collection.json').items() if c['split']=='train']
    xs=[];ys=[];metadata={}
    for name in names:
        base=a.corpus/name;program=base/'program.json'
        trained=a.models/'model-1703.json';p=compile_plan(program,base/'input',a.ref/'sum-bits/program.json',trained)
        path=a.out/f'{name}-plan.json';path.write_text(json.dumps(p));dest=a.out/f'{name}-census'
        d=run(a.binary,program,dest,path,'census',True)
        for field in ('rhs','state','writes','resumes'):
            assert read(dest/f'{field}.json')==read(base/'observation'/f'{field}.json')
        units=d['action_units'];steps=d['steps']
        epochs={s['epoch']:i for i,s in enumerate(steps)}
        bank=np.zeros((len(steps),256,8),np.int32);bank[:,:,0]=-1
        labels=np.zeros((len(steps),256),np.bool_)
        macros=np.zeros((len(steps),256,len(p['joins'])),np.int32)
        mapping={}
        for i,(stage,features,_) in enumerate(units['observations']):
            bank[i,:,1]=stage
            for action,addr,*rest in features:
                bank[i,action,0]=addr;bank[i,action,2:]=rest
                mapping[i,action//8,addr]=action
        root_ordinal={}
        for e in units['issued']:
            epoch,slot,leaf,unit,addr,_,winner=e[:7]
            if winner:
                k=epochs[epoch];act=mapping[k,leaf,addr];labels[k,act]=True;root_ordinal[winner]=(k,act,leaf)
        # Cross-source targets are matched on the exact root rule/binding ordinal and originating
        # leaf; a native physical address is never imported from a Metal capture.
        joins={u[0]:i for i,u in enumerate(p['joins'])}
        with np.load(a.targets/'train'/f'{name}.npz') as z:
            for row in z['targets']:
                epoch,leaf,rank,code,depth,root,child=map(int,row[:7])
                if depth!=2 or root not in root_ordinal:continue
                k,act,native_leaf=root_ordinal[root]
                if native_leaf==leaf and steps[k]['epoch']==epoch and code in joins:
                    # A certificate can materialize at most one later child. Keep an earliest observed
                    # source ordinal as a training target; online evaluation still checks every winner.
                    prev=macros[k,act,joins[code]]
                    macros[k,act,joins[code]]=min(prev,child) if prev else child
        np.savez_compressed(a.out/f'{name}.npz',features=bank,labels=labels,children=macros)
        # Time matched source Runs with a common verifier, fixed weights, and different proposal
        # densities. Delta includes all native phases/notifications even when no proposal wins.
        for seed in (1703,1709):
            p=compile_plan(program,base/'input',a.ref/'sum-bits/program.json',a.models/f'model-{seed}.json')
            for trial in range(3):
                modes=['exact','free','static','transfer']
                if trial%2:modes.reverse()
                group={}
                for mode in modes:
                    trialdir=a.out/f'{name}-{seed}-{mode}-{trial}'
                    path=a.out/f'{name}-{seed}-{mode}.json'
                    path.write_text(json.dumps(dict(p,schedule=dict(rows=2,waves=4,admission=mode))))
                    rec=run(a.binary,program,trialdir,None if mode=='exact' else path)
                    assert [s['executed_bindings'] for s in rec['steps']]==[s['executed_bindings'] for s in steps]
                    group[mode]=rec
                reference=np.array([s['elapsed_seconds'] for s in group['exact']['steps']])
                for mode in ('free','static','transfer'):
                    rec=group[mode];events=rec['action_units']['issued']
                    design=np.zeros((len(steps),7));design[:,0]=1;design[:,1]=(bank[:,:,0]>=0).sum(1)
                    # Costs per attempted certificate, novel root (one vs two atoms), child and duplicate.
                    seen=set()
                    for e in events:
                        epoch,slot,leaf,_,addr,_,root,child,later=e[:9];k=epochs[epoch]
                        design[k,2]+=1
                        if root:design[k,3+int(len(read_rules(p,base)[p['entries'][leaf][0]]['q'])>1)]+=1
                        if child:design[epochs[later],5]+=1
                        if (k,leaf,addr) in seen:design[k,6]+=1
                        seen.add((k,leaf,addr))
                    xs.append(design);ys.append((reference-np.array([s['elapsed_seconds'] for s in rec['steps']]))*1e6)
        metadata[name]=dict(runs=len(steps),available_winners=int(labels.sum()),positive_macro_links=int((macros>0).sum()))
    x=np.concatenate(xs);y=np.concatenate(ys)
    # Winsorize OS/timer outliers; report fit error and charge the measured recurring fixed cost
    # separately. Policy comparisons use total measured wall time for final acceptance.
    lo,hi=np.quantile(y,[.01,.99]);y=np.clip(y,lo,hi)
    coef=np.linalg.lstsq(x,y,rcond=None)[0]
    pred=x@coef
    (a.out/'calibration.json').write_text(json.dumps(dict(components=['run','present_address','attempt','one_atom_win','two_atom_win','child_win','duplicate'],
      net_us=coef.tolist(),r2=1-float(((pred-y)**2).sum()/((y-y.mean())**2).sum()),clipped_us=[lo,hi],programs=metadata,rows=len(x)),indent=1)+'\n')


_RULES={}
def read_rules(plan,base):
    if base not in _RULES:_RULES[base]=read(base/'input/ingress.json')['rules']
    return _RULES[base]


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('corpus','ref','models','targets','binary','out'):p.add_argument(key,type=Path)
    main(p.parse_args())
