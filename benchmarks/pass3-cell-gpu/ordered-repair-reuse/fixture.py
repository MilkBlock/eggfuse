"""Source test for repeated scalar operands, constructor collisions and a nested Eq set."""
import argparse,importlib.util,json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('ref',HERE.parent/'compact-recipes/study.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def test(a):
    a.out.mkdir(parents=True,exist_ok=False);p=a.out/'compiled/program.json';b=a.out/'bundle'
    subprocess.run(['cargo','cell-compile','--source',HERE/'repair.egg','--output',p.parent],check=True)
    subprocess.run([sys.executable,HERE.parent/'codec.py',p,a.out/'image'],check=True)
    subprocess.run([sys.executable,HERE.parent/'joint-witness/prepare.py',p,a.out/'image',b],check=True)
    plans=b/'plans.json';r=base.read(b/'request.json');r.pop('merge_config',None)
    tables=a.exp/'baked-port-packed-study-v1'
    (b/'root.json').write_text(json.dumps(dict(control='use',encoding='checked_slots',forbid_fallback=True)))
    r.update(single_config=str(b/'single.json'),root_config=str(b/'root.json'),radius=0,multi_mode='rowdeltapairguardstackseal2xlearned',
             baked_codes=str(tables/'sum-bits-1703-tied.bin'),multi_weights=str(tables/'sum-bits-1703-tied.json'),packed_lookup=True,
             multi_root_pages=True,atom_constraints=2,audit=True)
    with base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',p) as ref:gold=ref({'audit':True})
    result={}
    with base.session(a.native,p,plans) as infer:
        for name,m in [('off',0),('reverse',1),('payload',2),('key',4),('all',7),('defer',16),('combined',23)]:
            x=infer(dict(r,ordered_repair=m));assert 'source_error' not in x,x.get('source_error')
            for k in ('rhs','writes','resumes','runs','schedule','state_sha'):assert x[k]==gold[k]
            unions=[[e for e in events if e[0]=='union'] for events in x['events']]
            assert unions==gold['unions'] and sum(map(len,unions))>=3
            source_tables=base.read(p)['source_core']['tables'];size=next(i for i,t in enumerate(source_tables) if t['name']=='Size')
            writes=[[e[6:] for e in events if e[0]=='write' and e[3]==size] for events in x['events']]
            assert writes==[[[None,{'Int':3}]],[],[[{'Int':3},{'Int':1}]],[],[],[]],writes
            result[name]=dict(size=writes,source={k:x[k] for k in ('rhs','writes','resumes','schedule','state_sha','cell_ids')},unions=unions,repair=x['ordered_repair'])
            if m:assert result[name]['source']==result['off']['source']
    w=result['all']['repair']['work']
    assert w['payload_audits'] and w['unsupported_schemas'] and w['substitutions']>=2 and w['retired_index_once'] and w['function_kept_index']
    for name in ('defer','combined'):
        q=result[name]['repair'];assert q['verified_reverse_edges']==q['native']['stats']['live_reverse_edges'] and q['work']['function_adoptions']>0
    (a.out/'fixture.json').write_text(json.dumps(result,indent=1)+'\n')
    print('verified ordered unions, constructor retirement, and set length 3 -> 1',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    test(p.parse_args())
