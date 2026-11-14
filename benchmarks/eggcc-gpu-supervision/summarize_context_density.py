"""Report actual GPU completion accuracy by synthetic connectivity and density."""
import argparse,hashlib,io,json,tarfile
from pathlib import Path
import numpy as np
from synthetic_cell_inputs import validate
from audit_device_match_readout import rows_from_labels
from audit_input_relations import restore
from summarize_enumerated_gpu import prediction_counts


def summarize(directory):
    manifest=json.loads((directory/'manifest.json').read_text());entries=[]
    for record in manifest['records']:
        if record['status']!='pass':continue
        path=directory/(str(record['index'])+'.tar.gz')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=record['archive_sha256']:raise ValueError('archive checksum')
        with tarfile.open(path) as t:
            doc=json.load(t.extractfile('case/input.json'));meta=json.load(t.extractfile('case/labeled.json'));raw=t.extractfile('case/labeled.npz').read()
        validate(doc)
        if doc['generator'].get('kind')!='context-density/v1':raise ValueError('density input required')
        if not meta['capture']['passed'] or hashlib.sha256(raw).hexdigest()!=meta['capture']['artifact_sha256']:raise ValueError('unverified labels')
        if meta['capture']['input_sha256']!=doc['input_sha256']:raise ValueError('input identity')
        with np.load(io.BytesIO(raw)) as data:
            ids=[meta['source_rules'].index(int(r)) for r in data['rules']]
            rows=rows_from_labels(meta['semantic_recipe'],ids,data['target_eq_classes']);selected=[]
            prefixes=sorted([k[:-4] for k in data.files if k.startswith('capture/') and k.endswith('/rule') and '/witness/' not in k and '/boundary/' not in k],key=lambda s:tuple(map(int,s.strip('/').split('/')[1:])))
            for prefix in prefixes:
                c=restore(data,prefix)
                if bool(c['recorded']):selected.extend(c['completion_readout']['selected'][c['accepted']])
            target_rule=doc['generator']['rule']
            direct_targets=[rows[j]['y'][rows[j]['quotient']['representatives']].astype(int).tolist() for j,rid in enumerate(ids) if rid==target_rule and not data['generated_source'][j]]
            total=prediction_counts(rows,selected,data['generated_source'])
            by_rule={}
            for rid in sorted(set(ids)):
                subset=[j for j,r in enumerate(ids) if r==rid]
                by_rule[str(rid)]=prediction_counts([rows[j] for j in subset],[selected[j] for j in subset],data['generated_source'][subset])
        entries.append(dict(index=record['index'],generator=doc['generator'],input_sha256=doc['input_sha256'],prediction=total,by_rule=by_rule,direct_target_states=direct_targets))
    return dict(scope='actual selected-family GPU feedback on synthetic context-density inputs; graph audit is separate from prediction',expected=manifest['expected'],attempted=len(manifest['records']),passed=len(entries),complete=manifest.get('complete',False),head_sha256=manifest['head_sha256'],records=entries)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('output',type=Path);a=p.parse_args();r=summarize(a.directory);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(dict(expected=r['expected'],attempted=r['attempted'],passed=r['passed'])))
