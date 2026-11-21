"""One native dual-input composition with pre-RHS grant and receiver-certified pivot partition."""
from argparse import ArgumentParser
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path
from statistics import median
HERE=Path(__file__).resolve().parent
wave=run_path(str(HERE.parent/'verified-wave-execution/study.py'));src=wave['source']
template=json.loads((HERE/'template.json').read_bytes())
def digest(o):return sha256(json.dumps(o,separators=(',',':')).encode()).hexdigest()
def observe(v,gold):
    assert 'source_error' not in v,v.get('source_error')
    q=src.base.summarize(v,gold);root=v['root_recipe'];bs=v['constructor_births'];children=v['merge_child']['issued']
    rr={c[2]:c for c in root['commits']};ordinal={k:v[0] for k,v in rr.items()}
    direct=(v.get('strict_dual') or {});internal=direct.get('children',[])
    marks={int(group[0]):group for group in internal}
    visible={f for f,t,hidden in bs['endpoint'] if not hidden}
    births=[(f,t,e,ordinal[s],int(bool(flags&2))) for f,t,e,ctor,s,_,_,flags in bs['rows'] if s and ctor and flags&1]
    bs_owner={f:(t,e,s,flags) for f,t,e,ctor,s,_,_,flags in bs['rows'] if s and ctor and flags&1 and not flags&2}
    wire_shape=Counter(); internal_child_births=0;strict_return_origins=[]
    for sid,_,epoch,f1,f2 in internal:
        child=rr[sid];producer=rr[marks[sid][1]]
        assert producer[5]+1==epoch==child[5] and all(bs_owner[f][2]==producer[2] and bs_owner[f][1]==producer[5] for f in (f1,f2))
        assert f1&0xffffffff==template['ops'][0] and f2&0xffffffff==template['ops'][1]
        assert len(producer[6])==5 and len(child[6])==2
        inp=[((r['row']['Fact']['cell']<<32)|r['row']['Fact']['op'],r['version']) for r in child[6]]
        assert inp==[(f1,producer[5]),(f2,producer[5])]
        strict_return_origins.append([producer[0],child[0],epoch,f1,f2])
    internal_ord={ordinal[s] for s in marks}
    internal_child_births=sum(f in visible and ord in internal_ord and not dyn for f,t,e,ord,dyn in births)
    selected=sum(int(c['selected']) for c in children)
    row=dict(checks=q['checks'],runs=v['runs'],rhs=q['rhs'],state_sha=q['state_sha'],root_parents=q['root_parents'],nested_ids=q['nested_ids'],cells=q['cells'],
        ordered_winners=digest([(c[0],c[1],c[3],c[4],c[5],c[6],c[7]) for c in root['commits']]),births=digest(births),
        final=digest(bs['endpoint']),single=q['single_winners'],physical_ordinals=digest([[*c[:5],ordinal[c[5]]] for c in root['fresh']]),
        retained=sum(f in visible for f,t,e,ord,dyn in births),emitted=root['emitted'],selected_children=selected,all_child_decisions=len(children),
        raw_multi=v['multi']['counts']['raw_tuples'],confirmed=len(marks),internal_child_visible_births=internal_child_births,
        named_child_identities=digest(strict_return_origins),examples=strict_return_origins[:5],dual=direct.get('counts',{}),
        outstanding=direct.get('outstanding',0),degree_keys=direct.get('degree_keys',0))
    row['external']=sum(row['emitted'])+selected;row['fept']=row['retained']/row['external']
    assert not row['outstanding']
    return row
FIXED=('checks','runs','rhs','state_sha','root_parents','nested_ids','cells','ordered_winners','births','final','single','physical_ordinals','retained','selected_children','all_child_decisions')
def main():
    p=ArgumentParser()
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','3mm']);p.add_argument('--probe',action='store_true');a=p.parse_args();a.seed=1703;a.cap=8192
    a.policy=json.loads((HERE.parent/'speculative-allocation-policy/policy.json').read_bytes());a.fraction=json.loads((HERE.parent/'wave-demand-policy/policy.json').read_bytes())['models']['fraction']
    a.out.mkdir(parents=True,exist_ok=False);out={}
    for case in a.cases:
        program,plan,req=src.common.config(a,case);cfg=wave['settings'](req,a)['packed']
        with src.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',program) as get:gold=get({'audit':True})
        rows={}
        with src.base.session(a.native,program,plan) as run:
            modes={'ordinary':None,'dual':template} if a.probe else {'ordinary':None,'dual':template,'wrong_version':dict(template,fault='version'),'no_unique':dict(template,fault='count')}
            for mode,opt in modes.items():
                v=run(dict(cfg,strict_dual=opt,birth_ledger=True,audit=True))
                q=observe(v,gold);rows[mode]=q
                for k in FIXED:assert q[k]==rows['ordinary'][k],(case,mode,k)
                print(case,mode,q['external'],q['confirmed'],q['dual'],flush=True);del v
            if not a.probe:
                for i in range(5):
                    for n in (('ordinary','dual') if i%2 else ('dual','ordinary')):
                        v=run(dict(cfg,strict_dual=modes[n]));assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
                        if n=='dual':assert v['strict_dual']['counts']['actual_commits']==rows[n]['confirmed']
                        if i:rows[n].setdefault('ms',[]).append(v['ms'])
                for n in ('ordinary','dual'):rows[n]['median_ms']=median(rows[n]['ms'])
        out[case]=rows;(a.out/'results.json').write_text(json.dumps(out,indent=1)+'\n')
if __name__=='__main__':main()
