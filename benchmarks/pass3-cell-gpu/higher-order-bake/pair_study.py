"""Full source comparison of independent, shared-generation and single-comparison multi-parent branches."""
import argparse
import hashlib
import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns

from study import make_session,paths
from evaluate import audit,read,rpc


def same_commit(records):
    # Native ticket serials can differ when one learned candidate batch replaces two.
    return [[row[i] for i in (0,1,2,4,5)] for row in records]


def run(a):
    a.out.mkdir(parents=True,exist_ok=False);report={}
    pairs=a.catalog['pairs']
    for case in a.cases:
        for seed in a.seeds:
            proc,req,plans,gold,capture=make_session(a,case,seed)
            result={};reference=None
            try:
                for mode in ('base','independent','raw','verified','stale'):
                    cfg=None if mode=='base' else dict(pairs=pairs,sharing=mode)
                    full=rpc(proc,dict(req,audit=True,guarded_pairs=cfg))
                    outcome=audit(full,case,a.ref,a.corpus,capture,plans,'learned','stackseal3xlearned')
                    assert outcome['aligned'] and not outcome['uncredited']
                    multi=full['multi'];versions=full.get('guarded_pairs')
                    root_ids={v[0] for v in full['root_recipe']['fresh']};nested={v['allocated'] for v in full['merge_child']['issued'] if v['allocated'] is not None}
                    assert not (root_ids & nested) and len(root_ids|nested)*100>=98*full['new_cells']
                    actual=[(v['ordinal'],v['rule'],v['anchors']) for v in multi['tickets']]
                    if reference is None:reference=actual
                    else:assert actual==reference,(case,seed,mode,'different committed neural witness')
                    if versions:
                        rows=same_commit(versions.pop('commits'))
                        digest=hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()
                        versions['sample_commits']=[r for r in rows if r[-1]][:5]
                        versions['commit_identity']=digest
                        if mode=='independent':source=digest
                        else:assert digest==source,(case,seed,mode,'published parent differs')
                        if mode in ('raw','verified'):assert versions['reused_sibling_runs'] and versions['shared_raw_tuples']
                        if mode=='verified':assert versions['comparisons'] and versions['gt']
                        if mode=='stale':assert not versions['reused_sibling_runs'] and versions['snapshot_misses']
                    result[mode]=dict(ms=[],rhs=outcome['source_rhs'],actual=outcome['total_attributed'],
                        graph_exact=True,source_aligned=True,direct_cells=len(root_ids|nested),fresh_cells=full['new_cells'],
                        multituples=multi['counts']['raw_tuples'],candidate_visits=multi['counts']['approximate_visits'],
                        source_comparisons=multi['counts']['primitive_evals'],guarded=versions)
                names=['base','independent','raw','verified']
                for trial in range(2*len(names)+1):
                    order=names[trial%len(names):]+names[:trial%len(names)]
                    for mode in order if trial%2==0 else order[::-1]:
                        cfg=None if mode=='base' else dict(pairs=pairs,sharing=mode)
                        start=perf_counter_ns();full=rpc(proc,dict(req,audit=False,guarded_pairs=cfg));elapsed=(perf_counter_ns()-start)/1e6
                        assert full['multi']['counts']['raw_tuples']==result[mode]['multituples']
                        assert full['state_sha']==outcome_digest(gold)
                        if trial:result[mode]['ms'].append(full['ms']);result[mode].setdefault('request_ms',[]).append(elapsed)
                for mode in names:result[mode]['median_ms']=median(result[mode]['ms'])
                report[f'{case}/{seed}']=result;(a.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
                print(case,seed,[(n,round(result[n]['median_ms'],1),result[n]['multituples']) for n in names],flush=True)
            finally:proc.stdin.close();proc.wait()


def outcome_digest(gold):
    return hashlib.sha256((gold/'state.json').read_bytes()).hexdigest()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('binary','ref','corpus','capture','train_capture','catalog','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','gemm-bias-relu','stable-argmax'])
    p.add_argument('--seeds',nargs='+',type=int,default=[1703,1709])
    a=p.parse_args()
    a.catalog=dict(read(a.catalog),training=[])
    run(a)
