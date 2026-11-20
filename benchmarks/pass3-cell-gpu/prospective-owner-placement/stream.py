"""Assess finite distinct natural supply, native actions and total retained graph bytes."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/"owner-action-policy"))
from collect import allocation,sha
from evaluate import oracle_ref

CASES=("dot-product","stable-argmax","gemm-bias-relu","gated-state")


def run(a):
    a.out.mkdir(parents=True,exist_ok=a.resume)
    checkpoint=a.out/"results.json"
    holdout=json.loads(checkpoint.read_bytes()) if a.resume and checkpoint.is_file() else {}
    def save():
        temp=checkpoint.with_suffix(".tmp")
        temp.write_text(json.dumps(holdout,indent=1)+"\n")
        temp.replace(checkpoint)
    for case in a.cases:
        catalogs="old-pair-catalogs-v1" if case in CASES[:2] else "owner-action-fresh-v1"
        program=a.exp/catalogs/case/"program.json"
        obs=a.exp/"repair-bake-families-20261120"/case/"observation"
        reference={k:json.loads((obs/(k+".json")).read_bytes()) for k in ("rhs","writes","resumes","state","report","events")}
        model=a.exp/"owner-action-weights-v2/regression.json"
        rows=holdout.setdefault(case,{})
        layouts=(("pooled","keep"),("defer-only","keep"),("isolate","keep"),("multi-prefix","keep"),
                 ("defer","keep"),("defer","merge"),("defer","policy"))
        selective=tuple((layout,decision) for layout in ("defer-only","multi-prefix") for decision in ("merge","policy"))
        natural_model=a.out/"natural-regression.json"
        if a.all_actions:
            layouts+=selective
            if case in CASES[2:]:
                from fit_gate import fit
                donors=a.donors or [a.exp/"prospective-owners-stream-v1/results.json",
                                     a.exp/"prospective-stream-stable-argmax-v3/results.json"]
                fit(donors,natural_model)
                layouts+=(("defer","retrained"),)
        if a.selective_actions: layouts=selective
        for layout,control in layouts:
            if layout+"/"+control in rows:continue
            weight={"policy":model,"retrained":natural_model}.get(control)
            regression=json.loads(weight.read_bytes()) if weight else None
            native_control="policy" if weight else control
            with tempfile.TemporaryDirectory(dir=a.out) as tmp:
                out=Path(tmp)/"audit.json"
                subprocess.run([a.engine,program,native_control,out,layout,"0","0","0",weight or "-","stream"],check=True)
                v=json.loads(out.read_bytes())
            oracle_ref(v,reference)
            events=[]
            for r in v['events']:
                e=r['event'];token=e['issuer']
                assert e['kind']=='existing_pair' and token['members']==e['old_members'] and e['old']==e['new']
                assert len(set(y for _,y in e['old_members']))==2 and e['old']['external_readers']
                assert token['compose']==bool(e['retired_owner_ids'])
                if token['compose']:
                    assert e['outcome']['added']==0 and e['outcome']['merged']==1
                if regression:
                    score=regression['intercept']
                    for x,w in zip(token['features'],regression['weights']):
                        score+=x*w
                    assert abs(score-token['score'])<1e-10 and (score>0)==token['compose']
                saved,peak=allocation(e)
                events.append(dict(run=r['source_run'],ids=e['ids'],shape=e['shape'],owners=e['old_members'],features=token['features'],
                                   epoch=token['epoch'],selected=token['compose'],birth_epochs=e['member_birth_epochs'],
                                   old_refs=sha(e['old']),reader_count=len(e['old']['external_readers']),
                                   saved_bytes=saved,peak_bytes=peak))
            assert len(events)==v['issued_distinct'] and len({tuple(map(tuple,e['owners'])) for e in events})==len(events)
            row=dict(domain=v['domain'],distinct=v['distinct'],issued=len(events),selected=sum(e['selected'] for e in events),
                     immediate_bytes=sum(e['saved_bytes'] for e in events),final_charge=v['owner_final'],
                     peak_charge=v['owner_peak'],graph_drop_bytes=v['graph_drop_bytes'],placement=v['placement'],source_sha=sha(v['source_checks']),
                     graph=v['graph'],runs=v['runs'],first_read_digest=sha(v['post_action_read_digests']),first_read_runs=len(v['post_action_read_digests']),
                     first_subsequent_unions=v['post_action_unions'],events=events)
            if "reader_filter" in v:row["reader_filter"]=v["reader_filter"]
            rows[layout+'/'+control]=row
            holdout[case]=rows
            save()
            print(case,layout,control,row['distinct'],row['issued'],row['selected'],row['immediate_bytes'],row['graph_drop_bytes'],flush=True)
        holdout[case]=rows
        save()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','engine','out'):p.add_argument(k,type=Path)
    p.add_argument("--all-actions",action="store_true")
    p.add_argument("--resume",action="store_true")
    p.add_argument("--selective-actions",action="store_true")
    p.add_argument("--donors",nargs=2,type=Path,help="Training result paths for dot-product and stable-argmax, in that order")
    p.add_argument('--cases',nargs='+',choices=CASES,default=CASES)
    run(p.parse_args())
