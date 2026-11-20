"""Compile ordinary source arithmetic in both parent orientations, including checked overflow."""
import argparse,importlib.util,json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;GPU=HERE.parent
spec=importlib.util.spec_from_file_location('cpu_ref',GPU/'compact-recipes/study.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

def check(a):
    out=a.out;out.mkdir(parents=True,exist_ok=False)
    program=out/'compiled/program.json';bundle=out/'bundle'
    subprocess.run(['cargo','cell-compile','--source',HERE/('late-union.egg' if a.union else 'arithmetic.egg'),'--output',program.parent],check=True)
    subprocess.run([sys.executable,GPU/'codec.py',program,out/'image'],check=True)
    subprocess.run([sys.executable,GPU/'joint-witness/prepare.py',program,out/'image',bundle],check=True)
    req=base.read(bundle/'request.json');tables=a.exp/'baked-port-packed-study-v1'
    req.pop('merge_config')
    req.update(single_config=str(bundle/'single.json'),root_config=str(bundle/'root.json'),radius=0,multi_mode='rowdeltapairguardstackseal2xlearned',
               baked_codes=str(tables/'sum-bits-1703-tied.bin'),multi_weights=str(tables/'sum-bits-1703-tied.json'),packed_lookup=True,
               multi_root_pages=True,atom_constraints=2)
    (bundle/'root.json').write_text(json.dumps(dict(control='use',encoding='checked_slots',forbid_fallback=True)))
    with base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',program) as r:gold=r(dict(audit=True))
    report={}
    with base.session(a.native,program,bundle/'plans.json') as infer:
        for name,mode in [('off',0),('early',1),('indexed',2),('unavailable',3)]:
            cfg=dict(req,audit=True)
            if mode:cfg['derived_ports']=dict(mode=mode)
            x=infer(cfg)
            assert 'source_error' not in x,x.get('source_error')
            assert all(x[k]==gold[k] for k in ('rhs','writes','resumes','runs','schedule','state_sha'))
            assert [[e for e in row if e[0]=='union'] for row in x['events']]==gold['unions']
            multi=x['multi'];wins=multi['tickets']
            ordinals=[t['ordinal'] for t in wins]+[t[0] for t in x['single']['committed']]
            assert sorted(ordinals)==list(range(1,gold['rhs_count']+1))
            if not a.union:
                assert len(wins)==6
            v=dict(rhs=gold['rhs_count'],rules=sorted({t['rule'] for t in wins}),graph=x['state_sha'],raw=multi['counts']['raw_tuples'],
                   native_unions=sum(map(len,gold['unions'])),winner_runs=sorted({t['run'] for t in wins}),raw_digest=multi['raw_sha256'],cells=base.digest(x['cell_ids']),equations=multi['equations'])
            if a.union:
                # The marker 27 appears in exactly one target and can only bind after Group 2 and Group 3 merge.
                marked=[t for t in wins if {'Int':27} in t['inputs']]
                assert len(marked)==1 and marked[0]['rule']==0 and marked[0]['run']==3
                assert [len(row) for row in gold['unions']]==[0,1,0]
                v['marked_winner']={key:marked[0][key] for key in ('ordinal','rule','run','anchors','inputs')}
                v['source_runs']={key:gold[key] for key in ('rhs','writes','resumes','schedule','unions')}
                v['winners']=base.digest([{key:t[key] for key in ('ordinal','rule','run','anchors','inputs')} for t in wins])
                if mode:
                    for key in ('graph','cells','source_runs','marked_winner','winners'):
                        assert v[key]==report['off'][key],(name,key)
            else:
                assert len(v['rules'])==3
            if mode==1:assert v['equations']['rule_plans']==(1 if a.union else 3) and v['equations']['undefined']>0 and v['raw']<report['off']['raw']
            if mode==2:assert v['raw_digest']==report['early']['raw_digest']
            if mode==3:assert v['raw_digest']==report['off']['raw_digest']
            report[name]=v
    (out/'fixture.json').write_text(json.dumps(report,indent=1)+'\n')
    print({n:(v['rhs'],v['raw'],v['equations']['undefined']) for n,v in report.items()},flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--union',action='store_true');check(p.parse_args())
