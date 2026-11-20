"""Full native 2x4 holdout comparison from the same post-supervision warm start."""
import argparse,json,sys
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'row-admission'))
from study import check_graph,counts,launch,metrics
from export import compile_plan,read


def study(a):
    a.out.mkdir(parents=True,exist_ok=False);results={}
    donor=a.ref/'sum-bits/program.json'
    for case in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
        anchor=case in ('sum-bits','dot-product')
        program=a.ref/case/'program.json' if anchor else a.corpus/case/'program.json'
        image=a.ref/f'release-input-{case}' if anchor else a.corpus/case/'input'
        base=a.reference/f'{case}-exact'
        for seed in (1703,1709):
            summary={};plans={};realized=set();own={}
            for name in ('supervised','team','weighted','weighted_cf'):
                weights=a.weights/f'{seed}-{name}/model.json'
                p=compile_plan(program,image,donor,weights);p['schedule']=dict(rows=2,waves=4,admission='static')
                plans[name]=a.out/f'{case}-{seed}-{name}.json';plans[name].write_text(json.dumps(p))
                out=a.out/f'{case}-{seed}-{name}';launch(a.binary,program,out,plans[name],audit=True);assert check_graph(out,base)
                v=metrics(out,2,4,'static');realized.update(v['winners']);own[name]=v.pop('winners')
                del v['tasks'],v['first'];v.update(ms=[],cli_ms=[],aligned=True)
                no=a.out/f'{case}-{seed}-{name}-only';launch(a.binary,program,no,plans[name],residual=False)
                negative=metrics(no,2,4,'static');assert negative['exact']==0
                v['without_residual']=dict(rhs=negative['rhs'],first_divergence=next((i for i,(x,y) in enumerate(zip(counts(no),counts(base)),1) if x!=y),None))
                summary[name]=v
            summary['exact']={'ms':[],'cli_ms':[]};order=list(summary)
            for trial in range(10):
                seq=order[trial%5:]+order[:trial%5]
                for name in seq if trial<5 else seq[::-1]:
                    dest=a.out/f'{case}-{seed}-{name}-timed-{trial}'
                    elapsed=launch(a.binary,program,dest,plans.get(name));j=read(dest/'report.json')
                    assert read(dest/'state.json')==read(base/'state.json')
                    if name!='exact':
                        assert sum((e[6]>0)+(e[7]>0) for e in j['action_units']['issued'])==summary[name]['neural']
                    summary[name]['ms'].append(1000*j['inference_seconds']);summary[name]['cli_ms'].append(elapsed)
            for name,v in summary.items():
                v['median_ms']=median(v['ms'])
                if name!='exact':
                    v['missed_jointly_observed_roots']=len(realized-own[name]);v['observed_root_union']=len(realized)
            results[f'{case}/{seed}']=summary;(a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
            print(case,seed,[(n,v.get('neural'),round(v['median_ms'],1)) for n,v in summary.items()],flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('binary','ref','corpus','weights','reference','out'):p.add_argument(k,type=Path)
    study(p.parse_args())
