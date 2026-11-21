"""Compare direct publication with a queued higher-order owner on the same frozen native source."""
from argparse import ArgumentParser
from contextlib import ExitStack
import copy,hashlib,json,subprocess
from pathlib import Path
from runpy import run_path
from statistics import median
from time import perf_counter
HERE=Path(__file__).resolve().parent;previous=run_path(str(HERE.parent/'ripsat-set-receipt/study.py'))
source=previous['src'];filtered=previous['partial']['driver']['filtered']
read=lambda p:json.loads(p.read_bytes())
CAP={'schema':'eggfuse-ripsat-higher-cell/v1','request':'resolve-constructor-set','branches':['fresh','no-new-fact','stale'],'batch':'post-run'}
CLOCKS=('setup_ns','request_ns','capture_ns','direct_operand_ns','direct_publication_ns','response_ns','validation_ns','teardown_ns')
def settings(req,auth,mode,*,audit=False,profile=False,fault=None):
    signed=dict(auth['strict_named'],record_links=audit,higher_profile=profile)
    if mode=='higher':
        signed['higher_cell']=dict(CAP,target_sha256=auth['target_sha256'])
        if fault:signed['higher_fault']=fault
    return dict(filtered(req,signed),audit=audit,birth_ledger=audit)
def summary(v,gold):
    q=source.base.summarize(v,gold);del q['work'],q['rows']
    links,effects=previous['validate_links'](v,'');diag=previous['partial']['attribution'](v)
    candidates=v['merge_child']['issued'];paid=sum(int(x['selected'])for x in candidates);n=sum(q['emitted'])+paid
    z=v['strict_named']
    q.update(set=z['set_publication'],higher=z['higher_cell'],child_decisions=len(candidates),selected=paid,packets=n,
             new=diag['births'],visible=diag['visible'],fept=diag['visible']/n,birth_ids=diag['birth_digest'],endpoint_ids=diag['endpoint_digest'],
             terminal_effects=effects,terminal_links=len(links),link_sha=previous['digest'](links),single_hash=previous['digest'](v['single']['committed']),
             score=v['single']['adaptive_rows']['decision_digest'],ms=[],wall=[])
    return q,links
ALIGN=('checks','rhs','root_parents','root_ids','nested_ids','cells','children','single_winners','multi_winners','state_sha','physical','commits','birth_ids','endpoint_ids','terminal_effects','single_hash','score','new','visible','selected','child_decisions','emitted','wire_bytes','packets','fept','link_sha')
def verify(a,b):
    for k in ALIGN:assert a[k]==b[k],k
    assert all(a['checks'].values())
    h=b['higher'];c=h['counts']
    assert h['enabled'] and not a['higher']['enabled']
    assert c['requests']==c['queued_requests']>0
    assert c['retired_fresh']==c['transferred']==c['stable_address'] and c['requests']==c['retired_fresh']+c['retired_no_result']+c['retired_stale']
    assert c['terminal_commits']==b['terminal_links'] and c['operand_transfers']==b['set']['set_attempts']
    assert h['pending']==h['specialized']==0 and not any(c[k] for k in CLOCKS)
def run(a):
    a.out.mkdir(parents=True,exist_ok=True);reports={}
    cap=json.loads(subprocess.check_output([a.native,'--higher-cell-capabilities']));assert cap==CAP
    for case in a.cases:
        prog,plan,req=source.config(a,case);auth=read(a.authorized/(case+'.json'))
        assert auth['target_sha256']==hashlib.sha256(prog.read_bytes()).hexdigest()
        with source.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',prog)as get:gold=get(dict(audit=True))
        rows={}
        for name in ('direct','higher'):
            with source.base.session(a.native,prog,plan)as get:v=get(settings(req,auth,name,audit=True))
            assert 'source_error' not in v,(case,name,v.get('source_error'))
            rows[name],links=summary(v,gold)
            print(case,name,rows[name]['emitted'],rows[name]['higher'],flush=True)
        verify(rows['direct'],rows['higher']);faults={}
        for fault in ('stale-generation','stale-epoch','duplicate','only-stale','alias-mismatch'):
            with source.base.session(a.native,prog,plan)as get:v=get(settings(req,auth,'higher',fault=fault))
            assert 'source_error' not in v,(case,fault,v.get('source_error'))
            c=v['strict_named']['higher_cell']['counts'];assert v['state_sha']==gold['state_sha'] and v['runs']==gold['runs']
            if fault=='duplicate':assert c['duplicate_replies']>0 and c['stale_replies']==0
            elif fault=='alias-mismatch':assert c['operand_fallbacks']>0
            else:assert c['stale_replies']>0
            if fault not in ('only-stale','alias-mismatch'):
                assert v['root_recipe']['emitted']==rows['higher']['emitted'] and c['terminal_commits']==rows['higher']['terminal_links'] and c['transferred']==rows['higher']['higher']['counts']['transferred']
            else:
                assert c['terminal_commits']==c['transferred']==0
                assert v['root_recipe']['emitted'][0]==rows['higher']['emitted'][0]+rows['higher']['terminal_links']
            faults[fault]=dict(operand_fallback=c['operand_fallbacks'],duplicate=c['duplicate_replies'],stale=c['stale_replies'],transfer=c['transferred'],confirmed=c['terminal_commits'],emitted=v['root_recipe']['emitted'])
        bad=settings(req,auth,'higher');bad['strict_named']['higher_cell']['target_sha256']='0'*64
        proc=subprocess.run([a.native,prog,plan],input=json.dumps(bad)+'\n',text=True,capture_output=True)
        assert proc.returncode and 'incorrect higher Cell target' in proc.stderr
        rows['faults']=faults
        with source.base.session(a.native,prog,plan) as get:
            for lap in range(a.repeats+1):
                for name in (('direct','higher') if lap%2 else ('higher','direct')):
                    start=perf_counter();v=get(settings(req,auth,name));wall=1000*(perf_counter()-start);h=v['strict_named']['higher_cell']
                    assert v['state_sha']==gold['state_sha'] and v['root_recipe']['emitted']==rows[name]['emitted']
                    assert h['counts']['terminal_commits']==rows[name]['higher']['counts']['terminal_commits'] and not h['audit_examples']
                    if lap:rows[name]['ms'].append(v['ms']);rows[name]['wall'].append(wall)
            for name in ('direct','higher'):
                clocks=[]
                for _ in range(3):
                    v=get(settings(req,auth,name,profile=True));c=v['strict_named']['higher_cell']['counts'];assert v['state_sha']==gold['state_sha']
                    clocks.append([c[k]/1e6 for k in CLOCKS]);assert sum(clocks[-1])>0
                rows[name]['phase_ms']=dict(zip(CLOCKS,map(median,zip(*clocks))));rows[name]['phase_samples_ms']=clocks;rows[name]['profiled_protocol_samples_ms']=[sum(x) for x in clocks];rows[name]['median_profiled_protocol_ms']=median(rows[name]['profiled_protocol_samples_ms'])
                rows[name]['median_ms']=median(rows[name]['ms']);rows[name]['median_wall_ms']=median(rows[name]['wall'])
        reports[case]=rows;(a.out/'results.json').write_text(json.dumps(reports,indent=1)+'\n')
        print(case,'complete',[(n,rows[n]['median_ms'],rows[n]['phase_ms'])for n in ('direct','higher')],flush=True)
if __name__=='__main__':
    p=ArgumentParser(description=__doc__)
    for k in ('exp','native','authorized','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','3mm']);p.add_argument('--repeats',type=int,default=4)
    run(p.parse_args())
