"""Capture actual Rust Vec capacities and verify the allocation counters do not change accepted bindings."""
import argparse
import json
from pathlib import Path
from native_study import cli,read,semantics,inputs


def main(a):
    a.out.mkdir(parents=True,exist_ok=False);result={}
    for name in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
        original=a.anchors if name in ('sum-bits','dot-product') else a.heldout
        gold=a.gold/f'{name}-native-reference'
        if not gold.is_dir():gold=original/f'{name}-native-reference'
        _,program,_=inputs(a.corpus,a.ref,name)
        for seed in (1703,1709):
            weights=original/f'{name}-{seed}-weights.json'
            for mode in ('boundary','fixed4','fixed6','all'):
                stem=f'{name}-{seed}-{mode}';plan=original/f'{stem}-plan.json';dest=a.out/stem
                cli(a.build/'runtime',program,weights,plan,dest)
                _,actual,_,_=semantics(dest,gold,True)
                previous=read(original/stem/'report.json')['precomputed_forest']
                assert actual['children']==previous['children'] and actual['static']==previous['static']
                ports=actual['ports'];old=previous['ports']
                for key in old:assert old[key]==ports[key],key
                keys=('vec_capacity_payload_bytes','vec_capacity_layout_bytes','vec_capacity_audit_bytes','reserved_payload_bytes',
                      'reference_bytes','copy_bytes','typed_value_slots','typed_value_slot_bytes','typed_values_materialized')
                result[f'{name}/{seed}/{mode}']={k:ports[k] for k in keys}
                result[f'{name}/{seed}/{mode}'].update(source_aligned=True,static_plan_file_bytes=plan.stat().st_size,
                                                      combined_weights_file_bytes=weights.stat().st_size)
                assert ports['vec_capacity_payload_bytes']>=ports['reserved_payload_bytes']
            (a.out/'results.json').write_text(json.dumps(result,indent=1)+'\n')
    print(len(result),'native layout allocation checks passed',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('corpus','ref','build','gold','anchors','heldout','out'):p.add_argument(k,type=Path)
    main(p.parse_args())
