"""Verified collection totals and actual query-witness owner-sharing coverage."""
import argparse,collections,hashlib,io,json,tarfile
from pathlib import Path
import numpy as np


def prediction_counts(rows,selected,generated):
    if len(rows)!=len(selected) or len(rows)!=len(generated):raise ValueError('prediction/source alignment')
    counts={name:dict(instances=0,correct=0) for name in ('all','direct','generated')}
    for row,value,is_generated in zip(rows,selected,generated):
        wanted=row['y'][row['quotient']['representatives']]
        if wanted.shape!=np.asarray(value).shape:raise ValueError('prediction quotient shape')
        correct=bool(np.array_equal(wanted,np.asarray(value)>=.5))
        for group in ('all','generated' if is_generated else 'direct'):
            counts[group]['instances']+=1;counts[group]['correct']+=int(correct)
    return counts


def summarize(directory):
    raw=(directory/'manifest.json').read_bytes();manifest=json.loads(raw)
    count=dict(accepted_samples=0,logical_shared_pairs=0,physical_alias_pairs=0)
    prediction={name:dict(instances=0,correct=0) for name in ('all','direct','generated')}
    for record in manifest['records']:
        if record['status']!='pass':continue
        path=directory/(str(record['index'])+'.tar.gz')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=record['archive_sha256']:raise ValueError('archive checksum')
        with tarfile.open(path) as t:
            capture=t.extractfile('case/capture.npz').read();meta=json.load(t.extractfile('case/capture.json'))
            labeled=t.extractfile('case/labeled.npz').read();labels=json.load(t.extractfile('case/labeled.json'))
        if not labels['capture']['passed'] or hashlib.sha256(labeled).hexdigest()!=labels['capture']['artifact_sha256']:raise ValueError('label checksum or acceptance')
        from audit_device_match_readout import rows_from_labels
        from audit_input_relations import restore
        with np.load(io.BytesIO(labeled)) as data:
            ids=[labels['source_rules'].index(int(r)) for r in data['rules']]
            rows=rows_from_labels(labels['semantic_recipe'],ids,data['target_eq_classes'])
            selected=[]
            prefixes=[k[:-4] for k in data.files if k.startswith('capture/') and k.endswith('/rule') and '/witness/' not in k and '/boundary/' not in k]
            prefixes.sort(key=lambda s:tuple(map(int,s.strip('/').split('/')[1:])))
            for prefix in prefixes:
                c=restore(data,prefix)
                if bool(c['recorded']):selected.extend(c['completion_readout']['selected'][c['accepted']])
            if len(selected)!=len(rows):raise ValueError('selected state alignment')
            current=prediction_counts(rows,selected,data['generated_source'])
            for group,values in current.items():
                for key,value in values.items():prediction[group][key]+=value
        if hashlib.sha256(capture).hexdigest()!=meta['capture']['artifact_sha256']:raise ValueError('capture checksum')
        with np.load(io.BytesIO(capture)) as data:
            for key in data.files:
                if not key.endswith('/witness/physical_owner'):continue
                prefix=key[:-len('witness/physical_owner')];live=data[prefix+'bindings/live']&data[prefix+'accepted']
                for owners,logical in zip(data[key][live],data[prefix+'bindings/witness_rows'][live]):
                    count['accepted_samples']+=1
                    for i in range(len(owners)):
                        for j in range(i):
                            count['logical_shared_pairs']+=int(logical[i]==logical[j])
                            count['physical_alias_pairs']+=int(logical[i]!=logical[j] and owners[i]==owners[j])
    return dict(scope=manifest['scope'],producer_frames=manifest.get('producer_frames',False),prediction=prediction,complete=manifest.get('complete',False),expected=manifest['expected'],attempted=len(manifest['records']),statuses=dict(collections.Counter(r['status'] for r in manifest['records'])),samples=sum(r.get('samples',0) for r in manifest['records']),generated_source_consumers=sum(r.get('generated_source_consumers',0) for r in manifest['records']),released_owner_rows=sum(r.get('released_owner_rows',0) for r in manifest['records']),owner_witness_pairs=count,manifest_sha256=hashlib.sha256(raw).hexdigest(),head_sha256=manifest['head_sha256'],training_performed=False)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    r=summarize(a.directory);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
