"""Isolate source parity and neural provenance using the same binary, independent default engine and original checkpoint."""
from pathlib import Path
import sys,json,argparse
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'compact-recipes'))
from study import compare,session,read,digest

def first(seq,target):
    for i,(a,b) in enumerate(zip(seq,target)):
        if a!=b:return [i+1,a,b]
    return None if len(seq)==len(target) else [min(len(seq),len(target))+1,len(seq),len(target)]

def examine(v,gold):
    if 'source_error' in v:return {'error':v['source_error'],'runs':v['runs']}
    report={'runs':v['runs'],'rhs_count':gold['rhs_count'],'gold_state':gold['state_sha'],'state':v['state_sha'],'diff':{}}
    candidates={k:v[k] for k in ('rhs','writes','resumes','schedule')}
    candidates['unions']=[[e for e in row if e[0]=='union'] for row in v['events']]
    for k,seq in candidates.items():
        diff=first(seq,gold[k]);report['diff'][k]=diff
        if diff:
            index=diff[0]-1
            report.setdefault('schedule_at_diff',{})[k]={'control':gold['schedule'][index] if index<len(gold['schedule']) else None,'candidate':v['schedule'][index] if index<len(v['schedule']) else None}
    report['new_cells']=v['new_cells'];report['cell_ids']=digest(v['cell_ids'])
    if v.get('single') is not None and v.get('multi') is not None:
        q=compare(v,gold)
        report.update({k:q[k] for k in ('rhs','neural_rhs','fresh','direct_cells','root_allocated','checks','aligned')})
        report['exhausted']=v['multi']['counts']['exhausted'];report['single_work']=v['single']['work']
    return report

def run(a):
    a.out.mkdir(parents=True,exist_ok=False);b=a.bundle;p=b/'program.json'
    with session(a.exp/'compact-vanilla-20261121/vanilla-audit',p) as call:gold=call({'audit':True})
    req=read(b/'request.json')
    for k in ('single_config','multi_weights','merge_config','root_config'):req[k]=str(b/req[k])
    # Use the original three-view radius-two model and full root layout from the frozen package.
    arms={'same_build_exact':{'baseline':True},'legacy_joint':req}
    with session(a.binary,p,b/'plans.json') as call:
        all_results={}
        for name in a.arms:
            v=call(dict(arms[name],audit=True));r=examine(v,gold);all_results[name]=r
            if name!='same_build_exact':
                for k in ('rhs','writes','resumes','schedule'):
                    if r.get('diff',{}).get(k):
                        i=r['diff'][k][0]-1
                        if i<len(v['events']):
                            (a.out/f'{name}-{k}-events.json').write_text(json.dumps(v['events'][i]))
            (a.out/'results.json').write_text(json.dumps(all_results,indent=1)+'\n')
            print(name,r.get('error'),r.get('runs'),r.get('rhs'),r.get('neural_rhs'),r.get('fresh'),r.get('direct_cells'), {k: (d[0] if d else None) for k,d in r.get('diff',{}).items()},flush=True)
            del v
if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('binary','exp','bundle','out'):p.add_argument(k,type=Path)
    p.add_argument('--arms',nargs='+',default=['same_build_exact','legacy_joint'])
    run(p.parse_args())
