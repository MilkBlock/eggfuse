"""Verified collection totals and actual query-witness owner-sharing coverage."""
import argparse,collections,hashlib,io,json,tarfile
from pathlib import Path
import numpy as np


def summarize(directory):
    raw=(directory/'manifest.json').read_bytes();manifest=json.loads(raw)
    count=dict(accepted_samples=0,logical_shared_pairs=0,physical_alias_pairs=0)
    for record in manifest['records']:
        if record['status']!='pass':continue
        path=directory/(str(record['index'])+'.tar.gz')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=record['archive_sha256']:raise ValueError('archive checksum')
        with tarfile.open(path) as t:
            capture=t.extractfile('case/capture.npz').read();meta=json.load(t.extractfile('case/capture.json'))
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
    return dict(scope=manifest['scope'],complete=manifest.get('complete',False),expected=manifest['expected'],attempted=len(manifest['records']),statuses=dict(collections.Counter(r['status'] for r in manifest['records'])),samples=sum(r.get('samples',0) for r in manifest['records']),generated_source_consumers=sum(r.get('generated_source_consumers',0) for r in manifest['records']),released_owner_rows=sum(r.get('released_owner_rows',0) for r in manifest['records']),owner_witness_pairs=count,manifest_sha256=hashlib.sha256(raw).hexdigest(),head_sha256=manifest['head_sha256'],training_performed=False)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    r=summarize(a.directory);a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
