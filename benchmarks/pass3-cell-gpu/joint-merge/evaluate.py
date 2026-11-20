"""Count distinct actual allocations named directly by either a sealed parent or its verified learned merge child."""
import argparse,gzip,hashlib,json,subprocess,sys
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'joint-witness'))
import importlib.util
spec=importlib.util.spec_from_file_location('joint_eval',HERE.parent/'joint-witness/evaluate.py');joint=importlib.util.module_from_spec(spec);spec.loader.exec_module(joint)

def read(p):return json.loads(p.read_bytes())
def merge_audit(run,base,config):
    sing,multi=run['single'],run['multi'];parents={}
    for s in sing['committed']:parents[s[0]]=('single',s[2],s[8])
    for m in multi['tickets']:
        assert m['ordinal'] not in parents;parents[m['ordinal']]=('multi',m['rule'],m.get('local_token_id'))
    cells={i:(ord_,t,want,reused) for ord_,i,t,want,reused in run['cell_ids'] if not reused}
    assert len(cells)==sum(not r[-1] for r in run['cell_ids'])
    primary={i for i,(ord_,t,want,_) in cells.items() if ord_ in parents and t==want}
    merged=run['merge_child'];issued=merged['issued']
    aux={};providers={};unique_tokens=set()
    for index,packet in enumerate(issued):
        p=packet['parent'];ord_=p['ordinal']
        assert ord_ in parents and (p['provider'],p['rule'])==parents[ord_][:2]
        if parents[ord_][2] is not None:assert p['token']==parents[ord_][2]
        assert packet['issued_before_mutation'] and packet['id']==index
        if packet['allocated'] is None:continue
        i=packet['allocated'];assert i in cells and i not in aux and i not in primary
        assert packet['selected'] and packet['entered_allocator'] and not packet['rejected'] and not packet['reused']
        assert packet['old_reference'] is not None and packet['candidate_reference'] is not None and packet['old'] is not None
        assert cells[i][0]==ord_ and cells[i][1]==packet['template'] and cells[i][1]!=cells[i][2]
        providers[p['provider']]=providers.get(p['provider'],0)+1;aux[i]=dict(id=i,certificate=index,parent=p['ordinal'],template=packet['template'])
    assert len(primary)==base['instance_audit']['source_rule_template_matches']
    assert len(aux)==merged['counts'][5]
    return dict(total_rhs=base['total_attributed']+base['uncredited'],neural_rhs=base['total_attributed'],source_exact=base['valid_98'],
                total_fresh=len(cells),base_direct=len(primary),extra_direct=len(aux),direct_union=len(primary|aux.keys()),gap=len(cells)-len(primary|aux.keys()),
                direct_fraction=len(primary|aux.keys())/len(cells),counts=merged['counts'],by_provider=providers,
                raw_gate_hash=merged['score_trajectory'],multi_raw_hash=multi['raw_sha256'],cert_data=aux)


def study(a):
    a.out.mkdir(parents=True,exist_ok=False);results={}
    earlier=read(HERE.parent/'merge-result-port/versioned-results.json')
    for case in a.cases:
        anchor=case in ('sum-bits','dot-product')
        program=a.ref/case/'program.json' if anchor else a.corpus/case/'program.json'
        plan_file=a.policies/f'{case}-plans.json';plans=read(plan_file)
        program_id=read(program)['sha256']
        for seed in a.seeds:
            key=f'{case}/{seed}';weights=read(HERE.parent/'merge-result-port'/f'gate-{seed}.json')['weights']
            weights[-1]-=earlier[key]['training_threshold']
            proc=subprocess.Popen([a.binary,program,plan_file],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            arms={};identity=None
            try:
                for arm in a.arms:
                    forbid=arm.endswith('-no-fallback')
                    control=arm.removesuffix('-no-fallback')
                    path=a.out/f'{case}-{seed}-{arm}.json';cfg=dict(program_sha256=program_id,weights=weights,control=control,forbid_fallback=forbid)
                    path.write_text(json.dumps(cfg,separators=(',',':')))
                    req=dict(single_config=str(a.policies/f'{case}-{seed}-target.json'),multi_weights=str(a.multi/str(seed)/'model.json'),
                             multi_mode='seal3xlearned',radius=2,multi_residual=False,cap=1000000,audit=True,merge_config=str(path))
                    r=joint.rpc(proc,req)
                    if 'source_error' in r:
                        assert forbid and 'no verified neural template' in r['source_error'],(arm,r['source_error'])
                        arms[arm]=dict(failure=r['source_error'],first_uncompleted_run=r['runs']+1,partial_rhs=r['partial_rhs']);continue
                    summary=joint.audit(r,case,a.ref,a.corpus,a.capture,plans,'learned','learned')
                    assert summary['valid_98'] and all(summary['checks'].values())
                    s=merge_audit(r,summary,cfg)
                    evid=s.pop('cert_data');physical=r['cell_ids']
                    if identity is None:identity=physical
                    else:assert physical==identity
                    out=a.out/f'{case}-{seed}-{arm}-allocations.json.gz'
                    with gzip.open(out,'wt') as f:json.dump(dict(cell_ids=physical,children=evid,issued=r['merge_child']['issued']),f,separators=(',',':'))
                    arms[arm]=s
                    if control in ('null','shadow','wrong-template','wrong-operands','stale'):assert s['extra_direct']==0
                measured=[v for v in arms.values() if 'gap'in v]
                assert len({v['raw_gate_hash'] for arm,v in arms.items() if 'gap'in v and arm.removesuffix('-no-fallback') not in ('null','all')})<=1
                assert len({v['multi_raw_hash'] for v in measured})<=1
                results[key]=arms;(a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
                print(key,[(k,v.get('base_direct'),v.get('extra_direct'),v.get('total_fresh'),v.get('first_uncompleted_run')) for k,v in arms.items()],flush=True)
            finally:
                proc.stdin.close();proc.wait()
                if proc.returncode:raise RuntimeError(proc.stderr.read().decode()[-2048:])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('binary','ref','corpus','capture','policies','multi','out'):p.add_argument(k,type=Path)
    p.add_argument('--arms',nargs='+',default=['learned','shadow','null','wrong-template','wrong-operands','stale','all','learned-no-fallback','null-no-fallback'])
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax']);p.add_argument('--seeds',nargs='+',type=int,default=[1703,1709])
    study(p.parse_args())
