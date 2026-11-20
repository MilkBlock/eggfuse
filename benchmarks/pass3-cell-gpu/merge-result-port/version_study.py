"""One-shot versus revalidated merge certificates, with exact competitors removed before commit."""
import argparse,json
from pathlib import Path
import numpy as np
from study import read,save,run,cfg,compile_plan

def study(a):
    a.out.mkdir(parents=True,exist_ok=False);summary={}
    for seed in (1703,1709):
        checkpoint=read(a.gates/f'gate-{seed}.json');w=np.array(checkpoint['weights'])
        positives=[]
        for n in checkpoint['train']:
            records=read(a.gates/n/'report.json')['late_merge_ports']['records']
            positives.extend(float(w[:6]@r['features']+w[6]) for r in records if r['resolved'])
        threshold=float(np.quantile(positives,.01))
        high=w.copy();high[6]-=threshold
        for n in a.cases:
            anchor=n in ('sum-bits','dot-product');program=a.ref/n/'program.json' if anchor else a.corpus/n/'program.json'
            im=a.ref/f'release-input-{n}' if anchor else a.corpus/n/'input';gold=a.ref/f'events-{n}' if anchor else a.corpus/n/'observation'
            expected=read(a.references/f'v4-{n}'/'references.json')['lhs']
            action=a.out/f'{n}-{seed}-action.json';save(action,compile_plan(program,im,a.ref/'sum-bits/program.json',a.action/f'train-{seed}'/'model.json'))
            results={}
            for arm in ('one-shot','repeat','repeat-pinned','high-recall','high-repeat','all-repeat','swap','withheld'):
                weights=high.tolist() if arm.startswith('high') or arm=='withheld' else w.tolist()
                mode='all-neural' if arm=='all-repeat' else 'neural'
                c=cfg(program,weights,mode,arm!='repeat-pinned',arm=='swap',False)
                c.update(repeat=arm not in ('one-shot','high-recall'),drop_issued=arm=='withheld')
                path=a.out/f'{n}-{seed}-{arm}.json';save(path,c);dest=a.out/f'{n}-{seed}-{arm}';run(a,program,dest,path,action)
                report=read(dest/'report.json');r=report['late_merge_ports'];events=r['records']
                baseline=read(gold/'report.json')['steps']
                first=next((i for i,(s,v) in enumerate(zip(report['steps'],baseline),1) if any(s[k]!=v[k] for k in ('ruleset','executed_bindings','changed'))),None)
                if arm!='withheld':
                    for k in ('state','rhs','resumes','writes'):assert read(dest/f'{k}.json')==read(gold/f'{k}.json'),(n,arm,k)
                    assert first is None
                seen=set();extra=0;revalidated=0;forwarded=0
                for ev in events:
                    assert ev['root'] is not None
                    for ordinal,epoch,relaxed in ev['wins']:
                        assert ev['source']<ordinal and epoch>ev['run'] and ordinal not in seen and ev['merged'] and ev['candidate_pair']
                        seen.add(ordinal);revalidated+=int(relaxed);forwarded+=int(ev['forwarded'])
                        if arm!='withheld':assert expected[ordinal-1][2]==r['routes'][ev['route']][6]
                    extra+=max(0,len(ev['wins'])-1)
                roots=[e[6] for e in report['action_units']['issued'] if e[6]];assert not seen.intersection(roots)
                result=dict(potential=len(events),emitted=sum(e['selected'] for e in events),verified_ports=sum(e['merged'] is not None for e in events),
                    actual_children=len(seen),second_or_later=extra,after_revalidation=revalidated,forwarded=forwarded,
                    removed_exact_duplicates=r['extra_overlaps'],source_rhs=sum(s['executed_bindings'] for s in report['steps']),neural_roots=len(roots),first_divergence=first)
                if arm=='withheld':assert not seen and first is not None
                if arm=='swap':assert not seen
                if arm!='withheld':assert result['removed_exact_duplicates']==len(seen)
                results[arm]=result
            summary[f'{n}/{seed}']=dict(training_threshold=threshold,arms=results);save(a.out/'results.json',summary)
            print(n,seed,[(k,v['emitted'],v['actual_children'],v['after_revalidation']) for k,v in results.items()],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('runtime','corpus','ref','action','references','gates','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax']);study(p.parse_args())
