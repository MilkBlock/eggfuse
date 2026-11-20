"""Prospective family check after the fixed-pool expected-return and regression comparison."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
from collect import allocation,action,native,sha
from evaluate import oracle_ref

def evaluate(a):
    a.out.mkdir(parents=True,exist_ok=False)
    report={}
    for name in ('gemm-bias-relu','gated-state'):
        catalog=a.out/name;src=a.corpus/name
        subprocess.run([a.baker,src/'program.json',catalog],check=True)
        ref={k:json.loads((src/'observation'/(k+'.json')).read_bytes()) for k in ('rhs','writes','resumes','state','report','events')}
        rows={}
        with tempfile.TemporaryDirectory(dir=a.out) as tmp:
            dest=Path(tmp)/'audit.json'
            for label,mode in [('keep','split-keep'),('compose','split-merge'),('replay','split-policy'),('regression','split-policy'),('natural','census')]:
                checkpoint=a.policy/(label+'.json') if mode=='split-policy' else None
                v=native(a.engine,catalog/'program.json',mode,dest,1,0,checkpoint)
                oracle_ref(v,ref)
                decision=action(v)
                row=dict(runs=v['runs'],graph=v['graph'],eligible_visits=v['domain'][-1],issued=bool(decision),source_sha=sha(v['source_checks']),reads_sha=sha(v['post_action_read_digests']))
                if decision:
                    e=decision['event'];t=e['issuer'];row.update(run=decision['source_run'],x=t['features'],selected=t['compose'],score=t['score'],
                        saved_bytes=allocation(e)[0],peak_bytes=allocation(e)[1],token_id=e['issuer_id'],members=t['members'],later_unions=v['post_action_unions'])
                    assert e['old']==e['new']
                    if checkpoint:
                        w=json.loads(checkpoint.read_bytes());score=w['intercept']+sum(f*b for f,b in zip(t['features'],w['weights']))
                        assert score==t['score'] and (score>0)==row['selected']==bool(e['retired_owner_ids'])
                        assert row['saved_bytes']==rows['compose' if row['selected'] else 'keep']['saved_bytes']
                        assert row['members']==rows['keep']['members']
                rows[label]=row
            assert len({r['issued'] for k,r in rows.items() if k!='natural'})==1
            assert len({r['reads_sha'] for k,r in rows.items() if k!='natural'})==1
            print(name,[(k,r.get('saved_bytes'),r['eligible_visits']) for k,r in rows.items()],flush=True)
        report[name]=rows;(a.out/'fresh.json').write_text(json.dumps(report,indent=1)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('engine','baker','policy','corpus','out'):p.add_argument(k,type=Path)
    evaluate(p.parse_args())
