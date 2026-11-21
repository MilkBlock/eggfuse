"""Train only on donor workloads and audit actual group-origin constructor births on held-outs."""
import argparse
from collections import Counter
import json
from pathlib import Path
from runpy import run_path
from statistics import median
from hashlib import sha256
HERE=Path(__file__).resolve().parent
wave=run_path(str(HERE.parent/'verified-wave-execution/study.py'))
source=wave['source']
KEYS=('checks','rhs','commits','physical','cells','root_ids','nested_ids','root_parents','children','multi_winners','single_winners','state_sha','multi')


def digest(x):return sha256(json.dumps(x,separators=(',',':')).encode()).hexdigest()


def summarize(v,gold,profile):
    assert 'source_error' not in v,v.get('source_error')
    s=source.base.summarize(v,gold)
    q={k:s[k] for k in KEYS}
    root=v['root_recipe'];multi=v['multi']
    stats=multi['pair_actor'];examples=multi['pair_examples']
    roots={r[2]:r for r in root['commits']}
    events=v['constructor_births'];visible={e[0] for e in events['endpoint'] if e[-1]==0}
    origins=[(f,t,ep,token) for f,t,ep,ctor,token,_,_,flags in events['rows'] if ctor and flags&1 and token]
    q.update(birth_digest=digest(origins),visible_digest=digest(sorted(visible)),births=len(origins),
             visible=sum(f in visible for f,_,_,_ in origins),stats=stats,external=root['emitted'],
             receiver_raw=multi['counts']['raw_tuples'],visits=multi['counts']['approximate_visits'])
    q['all_child_decisions']=len(v['merge_child']['issued']);q['selected_children']=sum(j['selected'] for j in v['merge_child']['issued'])
    q['single_scores']=v['single']['work'][1];q['verified_parent_tuples']=multi['counts']['verified_parent_tuples']
    birth=Counter(token for f,t,ep,token in origins if f in visible)
    hist=Counter();group_tot=Counter();used=set();rules=Counter()
    for start,n,x,epoch,rid in examples:
        ids=range(start,start+n)
        assert not used.intersection(ids);used.update(ids)
        wins=sum(i in roots for i in ids);nodes=sum(birth[i] for i in ids)
        group_tot['no_commit']+=wins==0;group_tot['no_visible_birth']+=nodes==0
        group_tot['winning_lanes']+=wins;group_tot['visible_births']+=nodes
        rules[rid]+=1
        hist[tuple(x),bool(wins)]+=1
    q['outcomes']=dict(group_tot);q['rules']=dict(rules)
    assert len(examples)==stats['groups'] and len(used)==stats['declared_lanes']==stats['receiver_postings']
    assert root['emitted'][1]==stats['external_residual']
    assert root['emitted'][1]+stats['declared_lanes']==q['receiver_raw']
    charged=sum(root['emitted'])+stats['groups']+q['selected_children']
    q['external_packets']=charged;q['strict_decisions']=charged-stats['groups']+stats['score_calls']
    q['fept']=q['visible']/charged;q['strict_fept']=q['visible']/q['strict_decisions']
    if profile:q['examples']=[[list(x),int(t),n] for (x,t),n in sorted(hist.items())]
    return q


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);results={}
    for case in a.cases:
        prog,plans,req=source.common.config(a,case);base=wave['settings'](req,a)['packed']
        controls={'capture':{'enabled':True}} if a.train else {'off':{'enabled':False},'group':{'enabled':True,'weights':a.weights},'all':{'enabled':True}}
        if a.test_only: controls={'group':controls['group']}
        with source.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',prog) as get:gold=get({'audit':True})
        with source.base.session(a.native,prog,plans) as infer:
            rows={}
            for arm,cfg in controls.items():
                v=infer(dict(base,audit=True,birth_ledger=True,pair_actor=dict(cfg,trace=True)))
                row=summarize(v,gold,a.train);rows[arm]=row
                print(case,arm,row['stats'],row['fept'],flush=True)
                if 'off' in rows:
                    for k in (*KEYS,'birth_digest','visible_digest','births','visible','receiver_raw','all_child_decisions','selected_children'):
                        assert row[k]==rows['off'][k],(case,arm,k)
            if not a.train and not a.test_only:
                bad=infer(dict(base,pair_actor={'enabled':True,'bad_bound':True}))
                assert 'bucket' in str(bad.get('source_error','')),(case,bad.keys());rows['fault']=bad['source_error']
                names=list(controls)
                for i in range(5):
                    seq=names[i%len(names):]+names[:i%len(names)]
                    for arm in seq if i%2 else reversed(seq):
                        v=infer(dict(base,pair_actor=controls[arm]))
                        assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                        if i: rows[arm].setdefault('ms',[]).append(v['ms'])
                for n in names:rows[n]['median_ms']=median(rows[n]['ms'])
        results[case]=rows
        (a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--train',action='store_true');p.add_argument('--test-only',action='store_true')
    p.add_argument('--cases',nargs='+',required=True);p.add_argument('--policy',type=Path)
    a=p.parse_args();a.seed=1703;a.cap=8192
    a.policy_path=a.policy;a.policy=json.loads((HERE.parent/'speculative-allocation-policy/policy.json').read_bytes());a.fraction=json.loads((HERE.parent/'wave-demand-policy/policy.json').read_bytes())['models']['fraction']
    a.weights=json.loads(a.policy_path.read_bytes())['weights'] if a.policy_path else [1.,0.,0.]
    run(a)
