"""Materialize verified training pairs from the archived enumeration capture."""
import argparse,hashlib,json,tarfile
from pathlib import Path
from synthetic_cell_inputs import validate


def unpack(directory,output,allow_partial=False):
    manifest_bytes=(directory/'manifest.json').read_bytes();manifest=json.loads(manifest_bytes)
    if not manifest.get('complete',False) and not allow_partial:raise ValueError('capture collection is incomplete')
    output.mkdir(parents=True,exist_ok=False);records=[]
    sha=lambda raw:hashlib.sha256(raw).hexdigest()
    for record in manifest['records']:
        if record['status']!='pass':continue
        path=directory/(str(record['index'])+'.tar.gz')
        if sha(path.read_bytes())!=record['archive_sha256']:raise ValueError('archive mismatch')
        with tarfile.open(path) as t:
            source=json.load(t.extractfile('case/input.json'));validate(source)
            metadata=json.load(t.extractfile('case/labeled.json'));raw=t.extractfile('case/labeled.npz').read()
        c=metadata['capture']
        if (sha(raw)!=record['labels_sha256'] or sha(raw)!=c['artifact_sha256'] or
            not c['passed'] or not c.get('synthetic_input') or c['partition']!='train' or
            c['input_sha256']!=source['input_sha256'] or record['input_sha256']!=source['input_sha256']):raise ValueError('training evidence mismatch')
        target=output/(str(record['index'])+'.npz');target.write_bytes(raw);target.with_suffix('.json').write_text(json.dumps(metadata)+'\n')
        records.append(dict(index=record['index'],path=str(target),samples=c['samples'],sha256=sha(raw)))
    result=dict(scope='verified synthetic training files; no fitting',source_manifest_sha256=sha(manifest_bytes),collection_complete=manifest.get('complete',False),expected=manifest['expected'],records=records)
    (output/'manifest.json').write_text(json.dumps(result,indent=2)+'\n');return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('output',type=Path);p.add_argument('--allow-partial',action='store_true');a=p.parse_args()
    r=unpack(a.directory,a.output,a.allow_partial);print(json.dumps(dict(cases=len(r['records']),complete=r['collection_complete'])))
