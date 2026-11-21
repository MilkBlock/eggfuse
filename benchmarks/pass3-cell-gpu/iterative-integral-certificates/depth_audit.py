"""Join source resume records to the unique observed issuer of each source rule."""
import argparse,importlib.util,json
from collections import Counter
from pathlib import Path
HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('chain_bake',HERE/'bake.py');b=importlib.util.module_from_spec(sp);sp.loader.exec_module(b)
def run(a):
    a.out.mkdir(parents=True,exist_ok=True);results={}
    for case in ('sum-bits','3mm'):
        p,plan,req=b.joint['src'].config(a,case)
        with b.joint['src'].base.session(a.native,p,plan) as get:v=get(dict(b.joint['settings'](req,'filter_mixed'),chain=dict(depth=2),audit=True))
        actual=[e for run in v['events'] for e in run if e[0]=='resume']
        sr={e[2] for e in v['single']['committed']};mr={e['rule'] for e in v['multi']['tickets']}
        assert sr.isdisjoint(mr) and all(e[4] in sr|mr for e in actual)
        single=Counter(str(e[5])for e in actual if e[4] in sr);all_=Counter(str(e[5])for e in actual)
        assert len(actual)==sum(x[0] for x in v['resumes'])
        results[case]=dict(native_depths=all_,native_singleton_depths=single,graph=v['state_sha'],singleton_digest=b.digest(v['single']['committed']))
        lib=json.loads((a.library or a.exp/'iterative-fept-bake-v1/library.json').read_bytes())
        _,ix=b.schema_map(p);prefix=b.relink(lib['rounds']['1']['selected'],ix)
        with b.joint['src'].base.session(a.native,p,plan) as get:
            observed=get(dict(b.joint['settings'](req,'filter_mixed'),chain=dict(depth=2,library=prefix,explore_second=True)))
        assert observed['state_sha']==v['state_sha'] and observed['runs']==v['runs'] and observed['multi']['total_rhs']==v['multi']['total_rhs']
        diag=observed['integral_root']['chain']
        results[case]['observed_given_donor_prefixes']=[sum(n for path,n in diag['suppressed'] if len(path)==i) for i in (1,2)]
        for label,chain in [('unrestricted',v['integral_root']['chain']),('donor_prefix',diag)]:
            stats={}
            for k in (1,2):
                actual=sorted((n for path,n in chain['suppressed'] if len(path)==k),reverse=True)
                stats[k]=dict(shapes=len(actual),credits=sum(actual),top32_same_trace=sum(actual[:32]))
            results[case][label+'_concentration']=stats
        (a.out/'depth.json').write_text(json.dumps(results,indent=1)+'\n')
        print(case,dict(all_),dict(single),flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--library',type=Path);run(p.parse_args())
