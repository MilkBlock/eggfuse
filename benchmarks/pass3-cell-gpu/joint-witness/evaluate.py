"""Compare every committed ordinal and its physical allocations in one joint CPU/Rust Pass 3."""
import argparse
import gzip
from collections import Counter
import hashlib
import json
from pathlib import Path
from statistics import median
import subprocess
import sys
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'ordinary-witness'))
from plan import compile_program,sealed_plans


def read(path):return json.loads(path.read_bytes())


def rpc(child,request):
    child.stdin.write((json.dumps(request)+'\n').encode());child.stdin.flush()
    line=child.stdout.readline()
    if not line:raise RuntimeError(f'native session exited at {request}: '+child.stderr.read().decode()[-3000:])
    return json.loads(line)


def audit(run,case,ref,corpus,capture,plans,single_mode,multi_mode):
    anchor=case in ('sum-bits','dot-product')
    native=ref/f'events-{case}' if anchor else corpus/case/'observation'
    ordered=read(native/'report.json')
    schedule=[[s[k] for k in ('ruleset','epoch','path','iterations','executed_bindings','changed')] for s in ordered['steps']]
    expected=sum(s[4] for s in schedule)
    checks={k:run[k]==read(native/(k+'.json')) for k in ('rhs','writes','resumes')}
    checks['schedule']=run['schedule']==schedule
    checks['graph']=run['state_sha']==hashlib.sha256((native/'state.json').read_bytes()).hexdigest()
    def unions(events):return [[r for r in group if r[0]=='union'] for group in events]
    checks['unions']=unions(run['events'])==unions(read(native/'events.json'))
    own=run['allocations'];actual=len(own);sing=run['single'];multi=run['multi'];total=sing['rhs']
    assert total==multi['total_rhs']==actual==sum(s[4] for s in run['schedule'])
    widths={i:(p['width'] if p else None) for i,p in enumerate(plans)}
    source_rows={}
    for t in sing['committed']:
        ordinal,epoch,rid=t[:3]
        assert len(t)>=10 and ordinal not in source_rows and own[ordinal-1][:2]==[epoch,rid]
        assert widths[rid] is None
        source_rows[ordinal]=('single',rid)
    for t in multi['tickets']:
        ordinal,rid=t['ordinal'],t['rule']
        assert ordinal not in source_rows and widths[rid]>=2 and own[ordinal-1][:2]==[t['run'],rid]
        assert len(t['anchors'])>=2 and t['width']==widths[rid]
        source_rows[ordinal]=('multi',rid)
    assert multi['counts']['committed']==len(multi['tickets'])
    independent=None
    if 'cell_ids' in run:
        inst=run['cell_ids'];assert len(inst)==run['new_cells']
        for i,rid,cells,facts in own:
            assert i>=1 and rid>=0 and cells>=0 and facts>=0
        origins=Counter(row[0] for row in inst)
        for i,(_,_,created,_) in enumerate(own,1):assert origins[i]==created
    exact=all(checks.values())
    neural={ordinal for ordinal,(kind,_) in source_rows.items()
            if (kind=='single' and single_mode in ('learned','zero-state')) or (kind=='multi' and multi['neural_committed']>0)}
    nullary={t[0] for t in sing['committed'] if t[3] is None}
    covered_cells=sum(own[i-1][2] for i in neural);direct_cells=sum(r[2] for r in own)
    assert 0<=covered_cells<=direct_cells<=run['new_cells']
    if exact:
        with np.load(capture/case/'output.npz') as g:
            assert len(g['rhs'])==expected and np.array_equal(g['rhs'][:,0:2],np.asarray(own)[:,:2])
    if 'cell_ids' in run:
        fresh=[r for r in inst if not r[4]]
        direct=[r for r in fresh if r[0] in neural and r[2]==r[3]]
        independent=dict(physical_events=len(inst),fresh_instances=len(fresh),promotions=len(inst)-len(fresh),
                         distinct_fresh_ids=len({r[1] for r in fresh}),source_rule_template_matches=len(direct),
                         direct_template_share=len(direct)/len(fresh) if fresh else None)
        merge=run.get('merge_child')
        if merge:
            assert merge['source_rhs']==actual
            primary={row[1] for row in direct};by_id={row[1]:row for row in fresh}
            nested=set();trace=merge['issued'];assert len(trace)==merge['counts'][0]
            single_token={t[0]:t[8] for t in sing['committed']}
            for token in trace:
                parent=token['parent'];o=parent['ordinal']
                assert o in neural and source_rows[o]==(parent['provider'],parent['rule']) and own[o-1][0]==parent['run']
                if parent['provider']=='single':assert single_token[o]==parent['token']
                if token['allocated'] is None:continue
                cell=token['allocated'];owner,_,template,source_template,promoted=by_id[cell]
                assert owner==o and template==token['template'] and not promoted
                assert token['selected'] and token['issued_before_mutation'] and token['entered_allocator']
                assert not token['reused'] and not token['rejected'] and cell not in nested
                nested.add(cell)
            assert len(nested)==merge['counts'][5] and not (nested & primary)
            independent.update(named_primary=len(primary),named_nested=len(nested),joint_named_fresh=len(primary|nested),
                joint_named_share=len(primary|nested)/len(fresh) if fresh else None,merge_controls=merge['counts'],
                merge_raw_hash=merge['score_trajectory'],joint_cell_98=len(primary|nested)*100>=98*len(fresh))
        differences=Counter((own[o-1][1],expected,actual) for o,_,actual,expected,_ in fresh if o in neural and actual!=expected)
        independent['other_templates']=[[int(r),int(template),int(actual),n] for (r,template,actual),n in differences.most_common()]
        assert independent['distinct_fresh_ids']==len(fresh)
    first=next((i+1 for i,(a,b) in enumerate(zip(run['rhs'],read(native/'rhs.json'))) if a!=b),None)
    if first is None and len(run['rhs'])!=len(schedule):first=min(len(run['rhs']),len(schedule))+1
    return dict(checks=checks,aligned=exact,source_rhs=expected,actual_rhs=actual,first_rhs_difference=first,
                runs=run['runs'],neural_single=len(sing['committed']) if single_mode in ('learned','zero-state') else 0,
                neural_multi=multi['neural_committed'],zero_witness=len(nullary),total_attributed=len(neural),
                uncredited=actual-len(neural),required=(98*expected+99)//100,
                verified_source_coverage=len(neural)/expected if exact else None,
                valid_98=exact and 100*len(neural)>=98*expected,
                pass_without_zero_witness=exact and 100*len(neural-nullary)>=98*expected,
                new_physical_cells=run['new_cells'],cells_in_rhs=direct_cells,cells_in_neural_rhs=covered_cells,
                instance_audit=independent,allocation_share=covered_cells/run['new_cells'] if run['new_cells'] else None,
                single_work=sing['work'],multi_work=multi['counts'],multi_by_width=multi['by_width'],
                multi_raw_sha=multi.get('raw_sha256'),one_audit_ms=run['ms'])


def main(a):
    a.out.mkdir(parents=True,exist_ok=False);summary={}
    for case in a.cases:
        anchor=case in ('sum-bits','dot-product')
        prog=a.ref/case/'program.json' if anchor else a.corpus/case/'program.json'
        im=a.ref/f'release-input-{case}' if anchor else a.corpus/case/'input'
        plans=(sealed_plans if a.sealed else compile_program)(im)
        path=a.out/f'{case}-plans.json';path.write_text(json.dumps(plans,separators=(',',':')))
        for seed in a.seeds:
            # Both training families and weights are external to the test program.
            single_path=Path(a.single.replace('{seed}',str(seed)))
            trained=read(single_path/'config.json' if single_path.is_dir() else single_path)
            m=Path(a.multi.replace('{seed}',str(seed)))/'model.json'
            proc=subprocess.Popen([a.binary,prog,path],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            trials={}
            try:
                for arm in a.arms:
                    smode='none' if arm in ('null-single','none-only') else 'zero-state' if arm=='zero-state' else 'learned'
                    mmode='none' if arm in ('null-multi','none-only') else 'learned'
                    threshold=trained['model']['threshold']
                    if arm=='broad':threshold=-1e4
                    scfg=a.out/f'{case}-{seed}-{arm}.json'
                    config=dict(trained,mode=smode,residual=arm in ('target','assisted','null-single','null-multi','zero-state'),
                                model=dict(trained['model'],threshold=threshold))
                    scfg.write_text(json.dumps(config,separators=(',',':')))
                    if a.sealed:mmode=('stackseal' if a.shortlist and mmode=='learned' else 'seal')+(a.sealed_index if mmode=='learned' else mmode)
                    req=dict(single_config=str(scfg),multi_weights=str(m),multi_mode=mmode,radius=a.radius,
                             multi_residual=arm in ('assisted','null-single','null-multi'),cap=a.cap)
                    if a.merge_control:
                        merge_path=a.out/f'{case}-{seed}-{arm}-merge.json'
                        gate=read(HERE.parent/'merge-result-port'/f'gate-{seed}.json')
                        merge_path.write_text(json.dumps(dict(program_sha256=read(prog)['sha256'],weights=gate['weights'],control=a.merge_control)))
                        req['merge_config']=str(merge_path)
                    run=rpc(proc,dict(req,audit=True))
                    if 'source_error' in run:
                        if arm not in ('strict','null-single','null-multi','none-only'):raise RuntimeError(run)
                        base=a.ref/f'events-{case}' if anchor else a.corpus/case/'observation'
                        actual=run.get('rhs',[]);truth=read(base/'rhs.json')
                        run['first_different_rhs_run']=next((i for i,(x,y) in enumerate(zip(actual,truth),1) if x!=y),min(len(actual),len(truth))+1)
                        trials[arm]=dict(aligned=False,valid_98=False,source_error=run['source_error'],completed_runs=run['runs'],
                                         actual_partial_rhs=run['partial_rhs'],neural_source_coverage=None,
                                         first_different_rhs_run=run.get('first_different_rhs_run'))
                        summary[f'{case}/{seed}']=trials
                        (a.out/'results.json').write_text(json.dumps(summary,indent=1)+'\n')
                        continue
                    v=audit(run,case,a.ref,a.corpus,a.capture,plans,smode,mmode)
                    if arm=='broad':
                        v['diagnostic_threshold_forces_all_single']=True
                        v['valid_98']=False
                    v['single_residual']=config['residual'];v['multi_residual']=req['multi_residual']
                    v['single_threshold']=threshold
                    records=dict(single=run['single']['committed'],multi=run['multi']['tickets'])
                    if run.get('merge_child'):records['merge']=run['merge_child']['issued'];records['physical_cells']=run['cell_ids']
                    with gzip.open(a.out/f'{case}-{seed}-{arm}-ordinals.json.gz','wt') as file:json.dump(records,file,separators=(',',':'))
                    v['ms']=[]
                    for _ in range(a.repeats):
                        t=rpc(proc,dict(req,audit=False));assert t['state_sha']==run['state_sha']
                        assert t['multi']['counts']['committed']==v['multi_work']['committed']
                        v['ms'].append(t['ms'])
                    if v['ms']:v['median_ms']=median(v['ms'])
                    trials[arm]=v;summary[f'{case}/{seed}']=trials
                    (a.out/'results.json').write_text(json.dumps(summary,indent=1)+'\n')
                    print(case,seed,arm,v['aligned'],v['neural_single'],v['neural_multi'],v['source_rhs'],v['valid_98'],flush=True)
            finally:
                proc.stdin.close();proc.wait()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('binary','ref','corpus','capture','single','multi','out'):p.add_argument(k,type=str if k in ('single','multi') else Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    p.add_argument('--seeds',nargs='+',type=int,default=[1703,1709])
    p.add_argument('--arms',nargs='+',choices=('target','assisted','strict','null-single','null-multi','none-only','zero-state','broad'),default=['target','strict'])
    p.add_argument('--radius',type=int,default=2);p.add_argument('--cap',type=int,default=200000);p.add_argument('--repeats',type=int,default=0)
    p.add_argument('--merge-control',choices=('learned','null','wrong-template','wrong-operands','stale','shadow','all'))
    p.add_argument('--shortlist',action='store_true')
    p.add_argument('--sealed-index',choices=('learned','adaptive','certified','3xlearned'),default='adaptive')
    p.add_argument('--sealed',action='store_true')
    main(p.parse_args())
