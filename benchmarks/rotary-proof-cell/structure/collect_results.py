"""Collect frozen-run evidence without changing weights, predictions or verdicts."""
import argparse,json,hashlib,shutil
from pathlib import Path
import numpy as np
p=argparse.ArgumentParser();p.add_argument('artifact_root',type=Path);p.add_argument('destination',type=Path);a=p.parse_args()
a.destination.mkdir(parents=True,exist_ok=True)
rows={};provenance={}
for seed in (1703,1709,1721):
    source=a.artifact_root/f'seed-{seed}'/'result.json';r=json.loads(source.read_text())
    for filename,digest in r['protocol']['source_sha256'].items():
        assert hashlib.sha256((Path(__file__).parent/filename).read_bytes()).hexdigest()==digest,filename
    shutil.copyfile(source,a.destination/f'seed-{seed}.json')
    provenance[str(seed)]=dict(model_sha256=r['checkpoint_sha256'],result_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    for name,g in r['groups'].items():
        rows.setdefault(name,{})[str(seed)]=dict(passed=g['passed'],cases=g['cases'])
with np.load(a.artifact_root/'seed-1703/inputs.npz') as data:
    train=data['train'];seen=data['seen']
    exact={tuple(c) for c in train};semantic={tuple(c[:6]) for c in train}
    assert not exact & {tuple(c) for c in seen}
    overlap=sum(tuple(c[:6]) in semantic for c in seen)
shutil.copyfile(a.artifact_root/'diagnosis.json',a.destination/'diagnosis.json')
summary=dict(base_revision='8d2a5fc1',artifact_root=str(a.artifact_root),strict_trace_passed=rows,
    seen_panel=dict(cases=len(seen),exact_training_rows=0,semantic_tuple_seen_with_another_annotation=overlap,
                    semantic_tuple_unseen=len(seen)-overlap),
    provenance=provenance,source_sha256={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(Path(__file__).parent.glob('*.py'))},
    model_selection='all three predeclared seeds at step 12000, no heldout selection or retraining',
    verdict='cross-structure semantic acceptance failed; no CPU repair')
(a.destination/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary['seen_panel']))
