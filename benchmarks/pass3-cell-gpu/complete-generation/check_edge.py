"""A finite cap equal to the true final parent step is complete; one more candidate makes it incomplete."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent;GPU=HERE.parent
s=importlib.util.spec_from_file_location('compact_reference',GPU/'compact-recipes/study.py')
ref=importlib.util.module_from_spec(s);s.loader.exec_module(ref)


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);data={}
    for extra in (False,True):
        tag='two' if extra else 'one';tmp=a.out/tag;tmp.mkdir()
        text=(HERE/'last-parent.egg').read_text()
        if extra:text=text.replace('(run pair 1)','(Right 7 9)\n(run pair 1)')
        src=tmp/'input.egg';src.write_text(text)
        compiled=tmp/'compiled';image=tmp/'image';bundle=tmp/'bundle'
        subprocess.run(['cargo','cell-compile','--source',src,'--output',compiled],check=True)
        program=compiled/'program.json'
        subprocess.run([sys.executable,GPU/'codec.py',program,image],check=True)
        subprocess.run([sys.executable,GPU/'joint-witness/prepare.py',program,image,bundle,'--policy','certified'],check=True)
        req=ref.read(bundle/'request.json')
        for k in ('single_config','merge_config','root_config'):req[k]=str(bundle/req[k])
        # This two-constructor fixture has no function-constructor merge routes.
        # The multi-parent issuer remains the sole source of the Joined RHS.
        req.pop('merge_config')
        (bundle/'root.json').write_text(json.dumps(dict(encoding='checked_slots',control='use',forbid_fallback=True)))
        tables=a.exp/'baked-port-packed-study-v1'
        req.update(cap=1,radius=0,multi_mode='rowdeltapairguardstackseallearned',multi_root_pages=True,
                   multi_weights=str(tables/'sum-bits-1703-tied.json'),baked_codes=str(tables/'sum-bits-1703-tied.bin'),packed_lookup=True,
                   multi_page_tuples=1)
        with ref.session(a.exp/'compact-vanilla-20261121/vanilla-audit',program) as original:truth=original({'audit':True})
        with ref.session(a.native,program,bundle/'plans.json') as infer:
            finite=infer(dict(req,multi_generation='bounded',audit=True))
            complete=infer(dict(req,multi_generation='complete',audit=True))
            assert 'source_error' not in complete,complete
            fields=('rhs','writes','resumes','state_sha','runs','schedule')
            assert all(complete[k]==truth[k] for k in fields), ([(k,complete[k],truth[k]) for k in fields if complete[k] != truth[k]],complete['multi']['counts'])
            assert [[e for e in group if e[0]=='union'] for group in complete['events']]==truth['unions']
            won={t['ordinal'] for t in complete['multi']['tickets']}
            assert len(won)==truth['rhs_count']
            v=dict(complete_rhs=len(won),graph=complete['state_sha'],tuples=complete['multi']['counts']['raw_tuples'])
            if not extra:
                assert finite['state_sha']==complete['state_sha'] and finite['multi']['counts']['exhausted']>0
                assert all(finite[k]==truth[k] for k in fields);v['reached_limit']=finite['multi']['counts']['exhausted']
            else:
                assert 'source_error' in finite and 'state_sha' not in finite
                v['unfinished']=finite['unfinished_generation'];assert v['unfinished']['limit']==v['unfinished']['attempts']==1
            data[tag]=v
    assert data['two']['tuples']==data['one']['tuples']+1 and data['two']['complete_rhs']==data['one']['complete_rhs']+1
    (a.out/'edge.json').write_text(json.dumps(data,indent=1)+'\n');print(data,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    run(p.parse_args())
