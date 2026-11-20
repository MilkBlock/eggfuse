"""Audit one actual native execution at a time. Coverage requires ordered committed provenance."""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess


def read(path):return json.loads(path.read_bytes())


def account(folder,reference):
    record=read(folder/'report.json')
    def steps(report):return [[s[k] for k in ('epoch','ruleset','path','iterations','executed_bindings','changed')]
                              for s in report['steps']]
    assert steps(record)==steps(read(reference/'report.json'))
    for k in ('rhs','writes','resumes','state','events'):
        assert read(folder/f'{k}.json')==read(reference/f'{k}.json'),(folder,k)
    logical=read(folder/'cell-origins.json')
    rows=logical['by_rhs'];total=sum(s['executed_bindings'] for s in record['steps'])
    assert total==len(rows)
    winning={};roots=0;children=0;active=0;certificates=0
    if 'action_units' in record:
        units=record['action_units'];assert units['rhs']==total
        for issue,slot,leaf,code,addr,_,root,child,release,root_verified,child_verified in units['issued']:
            active+=1
            if root:
                assert root_verified and rows[root-1][0]==issue and root not in winning
                winning[root]=(issue,slot);roots+=1;certificates+=1
            if child:
                assert child_verified and 0<root<child and rows[child-1][0]==release and child not in winning
                winning[child]=(issue,slot);children+=1
    elif 'precomputed_forest' in record:
        forest=record['precomputed_forest'];assert forest['rhs']==total
        for slot,parent,rule,epoch,ordinal,sealed_by in forest['children']:
            assert ordinal not in winning and sealed_by<ordinal and rows[ordinal-1][:2]==[epoch,rule]
            winning[ordinal]=slot
        children=certificates=len(winning);active=record['neural_policy']['active']
    rhs_cells=sum(r[2] for r in rows);model_cells=sum(rows[o-1][2] for o in winning)
    new_alloc=logical['final_allocations']-logical['initial_cells']
    assert 0<=model_cells<=rhs_cells<=new_alloc
    need=(total*98+99)//100
    return dict(source_rhs=total,required_rhs=need,neural_rhs=len(winning),outside_neural=total-len(winning),
                missing_to_target=max(0,need-len(winning)),rhs_coverage=len(winning)/total,
                emitted_certificates=active,winning_certificates=certificates,root_rhs=roots,child_rhs=children,
                initial_cells=logical['initial_cells'],new_physical_cells=new_alloc,allocated_inside_rhs=rhs_cells,
                cells_allocated_during_neural_rhs=model_cells,outside_rhs=new_alloc-rhs_cells,
                physical_allocation_share=model_cells/new_alloc if new_alloc else None,
                new_logical_facts_during_rhs=sum(r[3] for r in rows),logical_facts_during_neural_rhs=sum(rows[o-1][3] for o in winning),
                ordered_endpoints_equal=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('ref','corpus','models','binary','out'):p.add_argument(k,type=Path)
    args=p.parse_args();args.out.mkdir(parents=True,exist_ok=False);report={}
    for name in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
        anchor=name in ('sum-bits','dot-product')
        prog=args.ref/name/'program.json' if anchor else args.corpus/name/'program.json'
        # Build a fresh reference w/ the same audit schema and compare it to the saved source run.
        ref=args.out/f'{name}-exact';cmd=[args.binary,'--program',prog,'--audit-events','--audit-cell-origins','--output']
        subprocess.run([*cmd,ref],check=True,stdout=subprocess.DEVNULL)
        gold=args.ref/f'events-{name}' if anchor else args.corpus/name/'observation'
        for k in ('rhs','writes','resumes','state'):
            assert read(ref/f'{k}.json')==read(gold/f'{k}.json')
        for seed in (1703,1709):
            arm='2x4-static';dest=args.out/f'{name}-{seed}'
            plan=args.models/f'{name}-{seed}-{arm}.json'
            subprocess.run([*cmd,dest,'--action-policy',plan,'--action-kind','macro'],check=True,stdout=subprocess.DEVNULL)
            report[f'{name}/{seed}']=account(dest,ref)
    (args.out/'results.json').write_text(json.dumps(report,indent=1)+'\n')
    for k,v in report.items():print(k,v['neural_rhs'],v['source_rhs'],v['cells_allocated_during_neural_rhs'],v['new_physical_cells'])
