"""Run frozen selection in the old-owner executor, keeping every native Run and reader."""
import argparse
import json
from pathlib import Path
import tempfile
from collect import native,action,allocation,sha

ARMS={'keep':'split-keep','compose':'split-merge','real':'split-policy','synthetic':'split-policy','mixed':'split-policy','replay':'split-policy','regression':'split-policy','natural':'policy'}

def oracle_ref(v,reference):
    assert len(v['source_checks'])==len(reference['rhs'])
    assert v['final_state']==reference['state']
    for i,q in enumerate(v['source_checks']):
        step=reference['report']['steps'][i]
        assert q[:6]==[step[k] for k in ('ruleset','path','iterations','epoch','executed_bindings','changed')]
        assert q[6:9]==[[reference[k][i]] for k in ('rhs','writes','resumes')]
        assert q[9]==[x for x in reference['events'][i] if x[0]=='union']

def evaluate(a):
    a.out.mkdir(parents=True,exist_ok=False);report={}
    policies={k:json.loads((a.policy/(k+'.json')).read_bytes()) for k in ('real','synthetic','mixed','replay','regression')}
    with tempfile.TemporaryDirectory(dir=a.out) as tmp:
        dest=Path(tmp)/'full.json'
        for name in a.cases:
            controls={}
            ref=None
            if name!='fixture':
                d=a.corpus/name/'observation'
                ref={k:json.loads((d/(k+'.json')).read_bytes()) for k in ('rhs','writes','resumes','state','report','events')}
            else: baseline=native(a.engine,a.catalog/name/'original.json','census',dest,1,0)
            for label,mode in ARMS.items():
                p='mixed' if label=='natural' else label
                checkpoint=a.policy/(p+'.json') if p in policies else None
                v=native(a.engine,a.catalog/name/'program.json',mode,dest,1,0,checkpoint)
                if ref is None:
                    assert (v['source_checks'],v['final_state'])==(baseline['source_checks'],baseline['final_state'])
                else: oracle_ref(v,ref)
                row=dict(source_sha=sha(v['source_checks']),graph=v['graph'],runs=v['runs'],domain=v['domain'],
                         readers_sha=sha(v['post_action_read_digests']),later_reads=len(v['post_action_read_digests']),later_unions=v['post_action_unions'])
                cand=action(v)
                if label=='natural':
                    assert row['domain'][6]==0 and not cand
                else:
                    e=cand['event'];token=e['issuer']
                    assert e['old']==e['new'] and token['members']==e['old_members'] and token['epoch']==e['old_epoch']
                    if checkpoint:
                        frozen=policies[p]
                        assert token['checkpoint']==[frozen['weights'],frozen['intercept']]
                        score=frozen['intercept']
                        for f,w in zip(token['features'],frozen['weights']):score+=f*w
                        assert abs(token['score']-score)<1e-11 and (score>0)==token['compose']
                    assert token['compose']==(e['outcome'].get('merged',0)==1)==bool(e['retired_owner_ids'])
                    reward,peak=allocation(e)
                    row.update(source_run=cand['source_run'],token=token,token_id=e['issuer_id'],saved_bytes=reward,peak_bytes=peak,
                               retired_owners=e['retired_owner_ids'],source_before=sha(e['old']),source_after=sha(e['new']))
                    if label!='keep':
                        k=controls['keep']
                        for field in ('readers_sha','source_sha','later_reads','later_unions','source_run','source_before','source_after','graph'):
                            assert k[field]==row[field]
                        assert k['token']['members']==token['members'] and k['token']['features']==token['features']
                    if checkpoint:
                        counter=controls['compose' if token['compose'] else 'keep']
                        assert reward==counter['saved_bytes'] and peak==counter['peak_bytes']
                controls[label]=row;print(name,label,row.get('saved_bytes'),row['domain'][-1],flush=True)
            report[name]=controls;(a.out/'test.json').write_text(json.dumps(report,indent=1)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('engine','policy','catalog','corpus','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['fixture','dot-product','stable-argmax'])
    evaluate(p.parse_args())
