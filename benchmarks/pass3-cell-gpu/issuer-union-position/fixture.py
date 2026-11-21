"""A three-port root, two explicit unions, constructor reuse and congruence of existing parents."""
import argparse,importlib.util,json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('cpu_source',HERE.parent/'compact-recipes/study.py')
cpu=importlib.util.module_from_spec(spec);spec.loader.exec_module(cpu)


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);p=a.out/'compiled/program.json';b=a.out/'bundle'
    subprocess.run(['cargo','cell-compile','--source',HERE/'source.egg','--output',p.parent],check=True)
    subprocess.run([sys.executable,HERE.parent/'codec.py',p,a.out/'image'],check=True)
    subprocess.run([sys.executable,HERE.parent/'joint-witness/prepare.py',p,a.out/'image',b],check=True)
    req=cpu.read(b/'request.json');req.pop('merge_config')
    w=a.exp/'baked-port-packed-study-v1'
    (b/'root.json').write_text(json.dumps(dict(control='use',encoding='checked_slots',forbid_fallback=True)))
    req.update(single_config=str(b/'single.json'),root_config=str(b/'root.json'),radius=0,multi_mode='rowdeltapairguardstackseal2xlearned',
        baked_codes=str(w/'sum-bits-1703-tied.bin'),multi_weights=str(w/'sum-bits-1703-tied.json'),packed_lookup=True,multi_root_pages=True,
        rows=dict(action=4,max_rows=1,workers=1,batch=True,verify=2,prefilter=0),audit=True)
    with cpu.session(a.exp/'compact-vanilla-20261121/vanilla-audit',p) as v:gold=v({'audit':True})
    out={}
    with cpu.session(a.native,p,b/'plans.json') as infer:
        for name,s in [('native',None),('cert',dict(mode='all')),('wrong',dict(mode='all',corrupt=True))]:
            v=infer(dict(req,union_position=s))
            assert 'source_error' not in v,v.get('source_error')
            assert all(v[k]==gold[k] for k in ('rhs','writes','resumes','schedule','runs','state_sha'))
            unions=[[e for e in run if e[0]=='union'] for run in v['events']]
            assert unions==gold['unions']
            ordinals=[t[0] for t in v['single']['committed']]+[t['ordinal'] for t in v['multi']['tickets']]
            assert sorted(ordinals)==list(range(1,gold['rhs_count']+1))
            row=dict(state_sha=v['state_sha'],rhs=gold['rhs_count'],source=v['rhs'],writes=v['writes'],
                     resumes=v['resumes'],schedule=v['schedule'],unions=unions,cells=cpu.digest(v['cell_ids']),
                     winners=cpu.digest([v['single']['committed'],v['multi']['tickets']]),
                     root_fresh=cpu.digest(v['root_recipe']['fresh']),raw=v['root_recipe']['raw_hash'],multi=v['multi']['raw_sha256'])
            row['position']=v['union_position']
            if name!='native':assert all(row[k]==out['native'][k] for k in row if k!='position')
            out[name]=row
    assert out['cert']['position']['origins']['explicit']['effective']>0
    assert out['cert']['position']['origins'].get('constructor_collision',{}).get('effective',0)>0
    assert sum(b['selected_valid'] for _,b in out['cert']['position']['features'])>0
    assert sum(b['selected_valid'] for _,b in out['wrong']['position']['features'])==0
    (a.out/'fixture.json').write_text(json.dumps(out,indent=1)+'\n')
    print(out['cert']['position']['origins'])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    run(p.parse_args())
