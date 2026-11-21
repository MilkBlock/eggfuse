"""Audit the exact generated pair stream and surviving constructor identities on live native runs."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
from statistics import median
import struct
HERE=Path(__file__).resolve().parent
base=run_path(str(HERE.parent/'generative-pair-buckets/study.py'))
wave=base['wave'];source=base['source']
KEYS=base['KEYS']

def digest(o):return sha256(json.dumps(o,separators=(',',':')).encode()).hexdigest()

def observe(v,gold):
    assert 'source_error' not in v,v.get('source_error')
    m=v['multi'];r=v['root_recipe'];q=source.base.summarize(v,gold);q={k:q[k] for k in KEYS}
    st=m['family_work'];b=v['constructor_births'];visible={e[0] for e in b['endpoint'] if e[-1]==0}
    births=[(f,t,e,tok) for f,t,e,c,tok,_,_,fl in b['rows'] if c and fl&1 and tok]
    orig=dict(m['family_origins']);assert len(orig)==len(m['family_origins'])==st['private_rows']
    assert st['candidate_bound']==st['receiver_pairs']
    commits=Counter(orig[x[2]] for x in r['commits'] if x[2] in orig)
    productive=Counter(orig[tok] for f,_,_,tok in births if f in visible and tok in orig)
    child=v['merge_child']['issued'];selected=sum(j['selected'] for j in child)
    examples=[]
    for buffer in m['family_examples']:
        data=bytes(buffer);words=struct.unpack('<9Q',data[:72]);keys=struct.unpack('<'+'I'*((len(data)-72)//4),data[72:])
        examples.append([list(words),list(keys)])
    ext=r['emitted'];external=sum(ext)+selected+st['actions']
    useful=sum(f in visible for f,_,_,_ in births)
    strict=external+st['absent']+st['stale']  # every rejected/unoccupied prototype also charged.
    all_scored=v['single']['work'][0]+ext[1]+st['actions']+st['prototypes']+len(child)
    assert positive(st['matched_min_packets'],st['actions'])
    floor=sum(ext)+selected+st['matched_min_packets']
    return dict(**q,stats=st,rules=m['family_rules'],examples=examples,visible=useful,births=len(births),birth_digest=digest(births),
        visible_digest=digest(sorted(visible)),external_roots=ext,child_selected=selected,child_decisions=len(child),
        explicit_packets=external,strict_packets=strict,all_scored=all_scored,matched_lower_bound=floor,
        fept=useful/external,strict_fept=useful/strict,matched_ceiling=useful/floor,
        single_score_inputs=v['single']['work'][0],single_source_checks=v['single']['work'][2],multi_source_checks=m['counts']['raw_tuples'],
        checked_parents=m['counts']['verified_parent_tuples'],expanded=m['counts']['raw_tuples'],root_visits=m['counts']['root_offers'],
        group_accepted=sum(commits.values()),group_visible=sum(productive.values()),no_commit=st['actions']-len(commits),
        no_visible=st['actions']-len(productive),raw_issue_sha=m['raw_sha256'])

def positive(bound,actions):return 0<=bound<=actions

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('exp','native','out'):p.add_argument(key,type=Path)
    p.add_argument('--cases',nargs='+',default=['3mm','deriche']);p.add_argument('--smoke',action='store_true')
    a=p.parse_args();a.seed=1703;a.cap=8192
    a.policy=json.loads((HERE.parent/'speculative-allocation-policy/policy.json').read_bytes())
    a.fraction=json.loads((HERE.parent/'wave-demand-policy/policy.json').read_bytes())['models']['fraction']
    a.out.mkdir(parents=True,exist_ok=False);data={}
    for case in a.cases:
        prog,plan,req=source.common.config(a,case);cfg=wave['settings'](req,a)['packed']
        with source.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',prog) as get:gold=get({'audit':True})
        rows={}
        with source.base.session(a.native,prog,plan) as run:
            options={'off':0,'small':1,'wide':2}
            for name,mode in options.items():
                v=run(dict(cfg,audit=True,birth_ledger=True,pair_family=dict(mode=mode,trace=True)))
                q=observe(v,gold);rows[name]=q
                for k in (*KEYS,'births','visible','visible_digest','birth_digest','expanded','raw_issue_sha','child_selected','child_decisions','checked_parents'):
                    assert q[k]==rows['off'][k],(case,name,k)
                assert q['external_roots'][1]+q['stats']['private_rows']==rows['off']['external_roots'][1]
                print(case,name,q['stats'],q['fept'],q['strict_fept'],flush=True);del v
            bad=run(dict(cfg,pair_family=dict(mode=2,fault=True)));assert 'family' in str(bad.get('source_error','')),(case,bad.keys())
            rows['fault']=bad['source_error']
            if not a.smoke:
                for i in range(5):
                    keys=list(options);order=keys[i%3:]+keys[:i%3]
                    for name in order if i%2 else reversed(order):
                        v=run(dict(cfg,pair_family=dict(mode=options[name])))
                        assert v['runs']==gold['runs'] and v['state_sha']==gold['state_sha']
                        if i:rows[name].setdefault('ms',[]).append(v['ms'])
                for name in options:
                    rows[name]['median_ms']=median(rows[name]['ms'])
                    diagnostic=run(dict(cfg,pair_family=dict(mode=options[name],phase=True)))
                    assert diagnostic['state_sha']==gold['state_sha']
                    rows[name]['phase']={k:diagnostic['multi']['family_work'][k] for k in ('source_pair_ms','issue_ms','receiver_ms')}
        data[case]=rows;(a.out/'results.json').write_text(json.dumps(data,indent=1)+'\n')
if __name__=='__main__':main()
