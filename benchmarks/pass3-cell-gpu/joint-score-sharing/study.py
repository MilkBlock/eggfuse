"""Profile full joint CPU Pass 3. Candidate caches are local to each rule occurrence and recurrent state."""
import argparse,hashlib,importlib.util,json,subprocess,sys
from pathlib import Path
from statistics import median
from time import perf_counter_ns

HERE=Path(__file__).resolve().parent;J=HERE.parent/'joint-witness'
sys.path.insert(0,str(J))
spec=importlib.util.spec_from_file_location('joint_cpu_eval',J/'evaluate.py');joint=importlib.util.module_from_spec(spec);spec.loader.exec_module(joint)
read=lambda p:json.loads(p.read_bytes())

def hash_json(v):return hashlib.sha256(json.dumps(v,separators=(',',':'),sort_keys=True).encode()).hexdigest()
def save(path,v):path.write_text(json.dumps(v,indent=1)+'\n')


def main(a):
    a.out.mkdir(parents=True,exist_ok=False);results={}
    for case in a.cases:
        anchor=case in ('sum-bits','dot-product');program=a.ref/case/'program.json' if anchor else a.corpus/case/'program.json'
        ref=a.ref/f'events-{case}' if anchor else a.corpus/case/'observation'
        expected_state=hashlib.sha256((ref/'state.json').read_bytes()).hexdigest()
        plan_root=a.high if (a.high/f'{case}-plans.json').is_file() else a.high.parent/'joint-98-template-audit-v1'
        plan=plan_root/f'{case}-plans.json';plans=read(plan)
        for seed in a.seeds:
            for regime in a.regimes:
                single=a.high/f'{case}-{seed}-target.json'
                if not single.is_file():single=a.high.parent/'joint-98-template-audit-v1'/f'{case}-{seed}-target.json'
                if regime=='certified':
                    config=read(Path(a.certified.replace('{seed}',str(seed))))
                    config.update(residual=False,mode='learned');single=a.out/f'{case}-{seed}-certified.json';save(single,config)
                merge=a.high/f'{case}-{seed}-target-merge.json'
                if not merge.is_file():merge=a.high.parent/'joint-merge-physical-study-v2'/f'{case}-{seed}-learned.json'
                base=dict(single_config=str(single),multi_weights=str(a.multi/str(seed)/'model.json'),multi_mode='stackseal3xlearned',
                          multi_residual=False,radius=2,cap=1000000,merge_config=str(merge))
                worker=subprocess.Popen([a.binary,program,plan],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                try:
                    tagged={};hashes=None
                    for mode in a.modes:
                        r=joint.rpc(worker,dict(base,score_sharing=mode,audit=True))
                        if 'source_error' in r:raise RuntimeError((case,seed,regime,mode,r['source_error']))
                        audited=joint.audit(r,case,a.ref,a.corpus,a.capture,plans,'learned','learned')
                        s=r['single']['score_sharing'];m=r['merge_child']
                        row=dict(offers=s['raw_if_audited'],recurrent=s['state_if_audited'],multi_raw=r['multi']['raw_sha256'],
                           single_committed=hash_json(r['single']['committed']),multi_committed=hash_json(r['multi']['tickets']),
                           child_gate=m['score_trajectory'],child_ids=hash_json(m['issued']),allocated_ids=hash_json(r['cell_ids']),
                           committed_binding_allocations=hash_json(r['allocations']),rhs=hash_json(r['rhs']),writes=hash_json(r['writes']),
                           spine=hash_json(r['resumes']),events=hash_json(r['events']),schedule=hash_json(r['schedule']),state=r['state_sha'])
                        if hashes is None:hashes=row
                        else:assert row==hashes,[(k,mode,row[k],hashes[k]) for k in row if row[k]!=hashes[k]]
                        assert audited['aligned'] and audited['valid_98']
                        instances=audited['instance_audit']
                        direct=instances['source_rule_template_matches']+m['counts'][5];total=instances['distinct_fresh_ids']
                        assert 100*direct>=98*total and s['counts'][0]==s['counts'][1]+s['counts'][2]
                        tagged[mode]=dict(model_requests=s['counts'][0],model_evaluations=s['counts'][1],cache_hits=s['counts'][2],
                            max_hash_entries=s['counts'][3],summed_hash_capacity=s['counts'][4],stale_checks_skipped=s['counts'][5],header_only_reads=s['counts'][6] if len(s['counts'])>6 else 0,
                            fresh_cells=total,direct=direct,neural_rhs=audited['total_attributed'],rhs=audited['source_rhs'],
                            verifier_checks=r['single']['work'][2],single_raw_discrete_hash=s['raw_if_audited'])
                    tagged['exact']={}
                    order=['exact',*a.modes]
                    for v in tagged.values():v.update(ms=[],request_ms=[],score_phase_ms=[],verify_phase_ms=[],multi_phase=[],native_phases=[])
                    for i in range(a.repeats+len(order)):
                        seq=order[i%len(order):]+order[:i%len(order)]
                        for mode in seq if i%2==0 else seq[::-1]:
                            req=dict(baseline=True,audit=False) if mode=='exact' else dict(base,score_sharing=mode,audit=False)
                            start=perf_counter_ns();r=joint.rpc(worker,req);wall=(perf_counter_ns()-start)/1e6
                            assert r.get('state_sha')==expected_state
                            if mode!='exact':
                                v=tagged[mode];s=r['single']['score_sharing']
                                assert (r['multi']['neural_committed']+len(r['single']['committed']))==v['neural_rhs']
                                assert s['counts'][:3]==[v['model_requests'],v['model_evaluations'],v['cache_hits']]
                            if i>=len(order):
                                v=tagged[mode];v['ms'].append(r['ms']);v['request_ms'].append(wall)
                                if 'native_phase_ms' in r:v['native_phases'].append(r['native_phase_ms'])
                                if mode!='exact':
                                    v['score_phase_ms'].append(1000*s['seconds'][0]);v['verify_phase_ms'].append(1000*s['seconds'][1])
                                    if 'joint_profile_seconds' in r['multi']:v['multi_phase'].append([1000*x for x in r['multi']['joint_profile_seconds']])
                    for mode,v in tagged.items():
                        for field in ('ms','request_ms','score_phase_ms','verify_phase_ms'):
                            if v[field]:v['median_'+field]=median(v[field])
                    results[f'{case}/{seed}/{regime}']=dict(arms=tagged,hashes=hashes)
                    save(a.out/'results.json',results)
                    print(case,seed,regime,[(mode,round(v['median_ms'],1),v.get('model_evaluations'),v.get('stale_checks_skipped')) for mode,v in tagged.items()],flush=True)
                finally:
                    worker.stdin.close();worker.wait()
                    if worker.returncode:raise RuntimeError(worker.stderr.read().decode()[-2048:])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('binary','ref','corpus','capture','high','multi','certified','out'):p.add_argument(k,type=str if k=='certified' else Path)
    p.add_argument('--seeds',nargs='+',type=int,default=[1703,1709]);p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    p.add_argument('--regimes',nargs='+',default=['high','certified']);p.add_argument('--modes',nargs='+',default=['off','full-key','static','stale','static-stale'])
    p.add_argument('--repeats',type=int,default=8)
    main(p.parse_args())
