"""Collect all seeds and both training objectives; no best-checkpoint selection."""
import argparse,json,hashlib,shutil
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser();p.add_argument('artifacts',type=Path);p.add_argument('destination',type=Path)
a=p.parse_args();a.destination.mkdir(parents=True,exist_ok=True)
source=Path(__file__).parent;rows={};stats={};fresh_hash=None
for seed in (1703,1709,1721):
    path=a.artifacts/f'seed-{seed}'/'result.json';r=json.loads(path.read_text())
    for name,digest in r['protocol']['source_sha256'].items():
        assert hashlib.sha256((source/name).read_bytes()).hexdigest()==digest,name
    old=json.loads((source.parent/'structure/results'/f'seed-{seed}.json').read_text())
    first=json.loads((source/'results/end-to-end'/f'seed-{seed}.json').read_text())
    for name,h in old['protocol']['dataset_hashes'].items():
        if name=='train':assert h==r['protocol']['train_hash']
        else:assert h==r['protocol']['dataset_hashes'][name],name
    for name,h in first['protocol']['dataset_hashes'].items():assert h==r['protocol']['dataset_hashes'][name],name
    if fresh_hash is None:fresh_hash=r['protocol']['fresh_manifest']['sha256']
    else:assert fresh_hash==r['protocol']['fresh_manifest']['sha256']
    shutil.copyfile(path,a.destination/f'seed-{seed}.json')
    for name,g in r['groups'].items():
        baseline=old['groups'].get(name,r['baseline_fresh'].get(name))
        rows.setdefault(name,{})[str(seed)]=dict(old_passed=baseline['passed'],new_passed=g['passed'],cases=g['cases'],
            run_passed=g['stage_passed'],expected_transfers=g['expected_transfers'],correct_alias=g['transfer_alias_passed'],
            false_transfers=g['false_transfers'],missed_transfers=g['missed_transfers'])
    with np.load(path.parent/'inputs.npz') as inputs:
        fresh_unique={k:len({tuple(c) for c in inputs[k]}) for k in ('final_shape','final_joint')}
    stats[str(seed)]=dict(semantic_status=r['semantic_status'],lineage=r['lineage'],masks=r['masks'],
        fresh_unique=fresh_unique,ablations={k:dict(passed=v['passed'],cases=v['cases']) for k,v in r['head_ablation'].items()},
        model_sha256=r['checkpoint_sha256'],result_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
summary=dict(rows=rows,seeds=stats,fresh_manifest_sha256=fresh_hash,artifact_root=str(a.artifacts),
    initial_shared_commit='f7687c01',old_flat_commit='14f1183e',
    token_floats=dict(old=128,new=279),token_bytes=dict(old=512,new=1116),
    learned_parameters=667,protected_input_floats=139,
    change='structured GPU state plus tied heads PLUS offline primitive-rule supervision',
    source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(source.glob('*.py'))},
    limits=['bounded fixed-size synthetic family','not a compression/speed result','not fully learned proof semantics','no CPU fallback or state repair'])
(a.destination/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
for name,values in rows.items():print(name,{seed:(v['old_passed'],v['new_passed'],v['cases']) for seed,v in values.items()})
