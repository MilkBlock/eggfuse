"""Attribute only actual fresh ids constructed from the winning root recipe or the validated dependent allocator."""
import argparse,gzip,hashlib,importlib.util,json,subprocess,sys
from pathlib import Path
from statistics import median
from time import perf_counter_ns
HERE=Path(__file__).resolve().parent;J=HERE.parent/'joint-witness'
sys.path.insert(0,str(J))
spec=importlib.util.spec_from_file_location('joint_benchmark',J/'evaluate.py');joint=importlib.util.module_from_spec(spec);spec.loader.exec_module(joint)
read=lambda p:json.loads(p.read_bytes())

def digest(obj):return hashlib.sha256(json.dumps(obj,separators=(',',':'),sort_keys=True).encode()).hexdigest()
def audit(r,case,a,plans,expected):
    record=joint.audit(r,case,a.ref,a.corpus,a.capture,plans,'learned','learned')
    assert record['aligned'] and record['valid_98']
    parents={}
    for row in r['single']['committed']:parents[row[0]]=('single',row[2],row[8])
    for row in r['multi']['tickets']:
        assert row['ordinal'] not in parents;parents[row['ordinal']]=('multi',row['rule'],row['local_token_id'])
    rr=r['root_recipe'];assert rr['rhs']==record['source_rhs']
    fresh={i:(o,t,w) for o,i,t,w,reused in r['cell_ids'] if not reused}
    assert len(fresh)==sum(not x[4] for x in r['cell_ids'])
    commits={};serials=set()
    for ordinal,kind,serial,rid,t,epoch,refs,values in rr['commits']:
        assert ordinal not in commits and serial not in serials and parents[ordinal][:2]==(kind,rid)
        commits[ordinal]=(kind,serial,rid,t);serials.add(serial)
        # Initial empty-LHS proposals can have no refs. Each multi recipe cites independent typed addresses.
        if kind=='multi':assert len(refs)>=2
    primary=set()
    for i,o,rid,t,kind,serial in rr['fresh']:
        assert i not in primary and commits[o]==(kind,serial,rid,t)
        assert fresh[i]==(o,t,t);primary.add(i)
    children=set()
    for child in r['merge_child']['issued']:
        i=child['allocated']
        if i is None:continue
        p=child['parent'];assert i not in children and i not in primary and parents[p['ordinal']]==(p['provider'],p['rule'],p['token'])
        assert fresh[i][0]==p['ordinal'] and fresh[i][1]==child['template'] and child['entered_allocator']
        children.add(i)
    assert len(primary)==rr['allocated'] and len(commits)==rr['applied']
    observed=dict(rhs=record['source_rhs'],neural_rhs=record['total_attributed'],source_exact=True,root_recipe_issued=rr['emitted'],
            root_verified=rr['sealed'],root_rejected=rr['rejected'],root_consumed=rr['applied'],direct_roots=len(primary),
            direct_children=len(children),direct_distinct=len(primary|children),fresh=len(fresh),
            elected_rule_template_comparison=record['instance_audit']['source_rule_template_matches'],
            root_proposal_hash=rr['raw_hash'],multi_raw_hash=record['multi_raw_sha'],merge_gate_hash=r['merge_child']['score_trajectory'],
            allocation_sha=digest(r['cell_ids']),root_allocations_sha=digest(rr['fresh']),root_commits_sha=digest(rr['commits']))
    if expected=='use':
        assert len(primary)+len(children)>=len(fresh)*.98,(case,observed)
    return observed


def main(a):
    a.out.mkdir(parents=True,exist_ok=False);data={}
    for case in a.cases:
        prog=a.ref/case/'program.json' if case in ('sum-bits','dot-product') else a.corpus/case/'program.json'
        plans_file=a.policies/f'{case}-plans.json';plans=read(plans_file)
        for seed in a.seeds:
            for policy in a.regimes:
                key=f'{case}/{seed}/{policy}';scfg=a.policies/f'{case}-{seed}-target.json'
                if policy=='certified':
                    cfg=read(Path(a.certified.replace('{seed}',str(seed))));cfg.update(residual=False,mode='learned')
                    scfg=a.out/f'{case}-{seed}-certified.json';scfg.write_text(json.dumps(cfg))
                merge=a.merge/f'{case}-{seed}-learned.json'
                base=dict(single_config=str(scfg),multi_weights=str(a.multi/str(seed)/'model.json'),multi_mode='stackseal3xlearned',
                          multi_residual=False,radius=2,cap=1000000,merge_config=str(merge))
                proc=subprocess.Popen([a.binary,prog,plans_file],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                try:
                    group={};raw=None
                    for arm in a.arms:
                        mode=arm.split('/')[0];forbid='/' in arm
                        root_cfg=a.out/f'{case}-{seed}-{policy}-{arm.replace("/","-")}.json'
                        root_cfg.write_text(json.dumps(dict(control=mode,forbid_fallback=forbid)))
                        r=joint.rpc(proc,dict(base,root_config=str(root_cfg),audit=True))
                        if 'source_error'in r:
                            assert forbid and 'no verified root recipe' in r['source_error'],r['source_error']
                            group[arm]=dict(error=r['source_error'],fault=r['root_recipe']['fault'],first_uncompleted_run=r['runs']+1);continue
                        info=audit(r,case,a,plans,mode)
                        if raw is None:raw=info
                        else:
                            for f in ('allocation_sha','neural_rhs','multi_raw_hash','merge_gate_hash','root_proposal_hash'):
                                assert info[f]==raw[f],(case,seed,arm,f)
                        if mode in ('wrong-template','wrong-port','shadow','withhold'):assert info['direct_roots']==0
                        if mode=='use':
                            with gzip.open(a.out/f'{case}-{seed}-{policy}-{arm.replace("/","-")}-evidence.json.gz','wt') as stream:
                                json.dump(dict(roots=r['root_recipe'],allocations=r['cell_ids'],children=r['merge_child']['issued']),stream,separators=(',',':'))
                        group[arm]=info
                    data[key]=group;(a.out/'results.json').write_text(json.dumps(data,indent=1)+'\n')
                    print(key,[(k,v.get('direct_roots'),v.get('direct_children'),v.get('fresh'),v.get('first_uncompleted_run')) for k,v in group.items()],flush=True)
                finally:
                    proc.stdin.close();proc.wait()
                    if proc.returncode:raise RuntimeError(proc.stderr.read().decode()[-2048:])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('binary','ref','corpus','capture','policies','multi','merge','certified','out'):p.add_argument(k,type=str if k=='certified' else Path)
    p.add_argument('--seeds',nargs='+',type=int,default=[1703,1709]);p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    p.add_argument('--regimes',nargs='+',default=['high','certified'])
    p.add_argument('--arms',nargs='+',default=['use','withhold','wrong-template','wrong-port','shadow','use/no-fallback','withhold/no-fallback'])
    main(p.parse_args())
