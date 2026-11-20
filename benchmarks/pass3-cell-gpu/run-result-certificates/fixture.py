"""Check invalidated missing/positive evidence and native verifier fallback on a fresh source universe."""
import argparse,importlib.util,json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('gold',HERE.parent/'compact-recipes/study.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);p=a.out/'compiled/program.json';b=a.out/'bundle'
    subprocess.run(['cargo','cell-compile','--source',HERE/'change.egg','--output',p.parent],check=True)
    subprocess.run([sys.executable,HERE.parent/'codec.py',p,a.out/'image'],check=True)
    subprocess.run([sys.executable,HERE.parent/'joint-witness/prepare.py',p,a.out/'image',b],check=True)
    req=base.read(b/'request.json');req.pop('merge_config')
    weights=a.exp/'baked-port-packed-study-v1'
    (b/'root.json').write_text(json.dumps(dict(control='use',encoding='checked_slots',forbid_fallback=True)))
    req.update(single_config=str(b/'single.json'),root_config=str(b/'root.json'),radius=0,multi_mode='rowdeltapairguardstackseal2xlearned',
       baked_codes=str(weights/'sum-bits-1703-tied.bin'),multi_weights=str(weights/'sum-bits-1703-tied.json'),packed_lookup=True,
       multi_root_pages=True,rows=dict(action=4,max_rows=1,workers=1,batch=True,verify=2,prefilter=0),audit=True)
    with base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',p) as ref:gold=ref({'audit':True})
    result={}
    for path,arms in [(a.native,{'projected':1,'tables':3,'rows':4,'classes':5,'two-hit':6}),
                      (a.generated,{'shared-kernels':3,'all-kernels':4})]:
        with base.session(path,p,b/'plans.json') as issue:
            for name,mode in arms.items():
                actual=issue(dict(req,projected_checks=mode))
                assert 'source_error' not in actual,actual.get('source_error')
                assert all(actual[k]==gold[k] for k in ('rhs','writes','resumes','state_sha','runs','schedule'))
                assert [[e for e in step if e[0]=='union'] for step in actual['events']]==gold['unions'] and any(gold['unions'])
                s=actual['single']['adaptive_rows']
                row=dict(winners=actual['single']['committed'],graph=actual['state_sha'],source_runs=gold['rhs'],
                         write_runs=gold['writes'],unions=gold['unions'],cells=actual['cell_ids'],projection=s['projection'])
                if 'result_certificates' in s:row['certificates']=s['result_certificates']
                if result:
                    for k in ('winners','graph','source_runs','write_runs','unions','cells'):assert row[k]==result['projected'][k]
                result[name]=row
    (a.out/'fixture.json').write_text(json.dumps(result,separators=(',',':'))+'\n')
    for n,r in result.items():print(n,r['projection'].get('native_calls'),r.get('certificates',{}).get('hits'))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','generated','out'):p.add_argument(k,type=Path)
    run(p.parse_args())
