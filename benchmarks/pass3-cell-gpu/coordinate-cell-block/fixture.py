"""Exercise true and false local constraints, missing keys and repaired roles in native source Runs."""
import argparse,importlib.util,json,sys,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('reference',HERE.parent/'compact-recipes/study.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    program=a.out/'compiled/program.json';b=a.out/'bundle'
    subprocess.run(['cargo','cell-compile','--source',HERE/'ports.egg','--output',program.parent],check=True)
    subprocess.run([sys.executable,HERE.parent/'codec.py',program,a.out/'image'],check=True)
    subprocess.run([sys.executable,HERE.parent/'joint-witness/prepare.py',program,a.out/'image',b],check=True)
    req=base.read(b/'request.json');req.pop('merge_config',None)
    tables=a.exp/'baked-port-packed-study-v1'
    (b/'root.json').write_text(json.dumps(dict(control='use',encoding='checked_slots',forbid_fallback=True)))
    req.update(single_config=str(b/'single.json'),root_config=str(b/'root.json'),radius=0,multi_mode='rowdeltapairguardstackseal2xlearned',
               baked_codes=str(tables/'sum-bits-1703-tied.bin'),multi_weights=str(tables/'sum-bits-1703-tied.json'),packed_lookup=True,
               multi_root_pages=True,multi_generation='complete',audit=True)
    with base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',program) as get:gold=get({'audit':True})
    records={}
    with base.session(a.native,program,b/'plans.json') as get:
        for arm,cfg in [('source',{}),('hashed',dict(page_premises=9)),('direct',dict(factor_page=2,page_premises=9,coordinate_verify=2))]:
            v=get(dict(req,**cfg));assert 'source_error' not in v,v.get('source_error')
            assert all(v[k]==gold[k] for k in ('rhs','writes','resumes','schedule','runs','state_sha'))
            assert [[e for e in row if e[0]=='union'] for row in v['events']]==gold['unions'] and any(gold['unions'])
            m=v['multi'];wins=[{k:t[k] for k in ('run','rule','ordinal','anchors','inputs')} for t in m['tickets']]
            r=dict(graph=v['state_sha'],cells=base.digest(v['cell_ids']),source={k:gold[k] for k in ('rhs','writes','resumes','unions','schedule')},
                   winners=wins,raw=m['raw_sha256'],block=m['blocks'],words=m['word_verifier'],page=m['premises'])
            if records:
                for key in ('graph','cells','source','winners','raw'):assert r[key]==records['source'][key]
            records[arm]=r
        v=get(dict(req,factor_page=2,page_premises=9,coordinate_verify=2,factor_fault=True))
        assert 'coordinate' in v.get('source_error','')
        records['direct']['fault']=v['source_error']
    (a.out/'fixture.json').write_text(json.dumps(records,indent=1)+'\n')
    print('Connected winners in Runs',sorted({v['run'] for v in wins}),records['direct']['block'],records['direct']['words'],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    run(p.parse_args())
