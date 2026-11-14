"""Count owner-sharing cases in verified synthetic GPU match captures."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np
from synthetic_cell_inputs import validate


def audit(directory,source_directory=None):
    rows=[]
    for path in sorted(directory.glob('*.capture.npz')):
        source=(source_directory or directory)/path.name.replace('.capture.npz','.json')
        validate(json.loads(source.read_text()))
        meta=json.loads(path.with_suffix('.json').read_text())
        sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
        if meta['trace_sha256']!=sha(source) or meta['capture']['artifact_sha256']!=sha(path) or meta['capture']['passed'] is not True:
            raise ValueError('capture provenance mismatch')
        count=dict(samples=0,physical_alias_pairs=0,logical_shared_pairs=0)
        with np.load(path) as data:
            for key in data.files:
                if not key.endswith('/witness/physical_owner'):continue
                prefix=key[:-len('witness/physical_owner')]
                owners=data[key];logical=data[prefix+'bindings/witness_rows']
                live=data[prefix+'bindings/live']&data[prefix+'accepted']
                for a,b in zip(owners[live],logical[live]):
                    count['samples']+=1
                    for i in range(len(a)):
                        for j in range(i):
                            count['physical_alias_pairs']+=int(a[i]==a[j] and b[i]!=b[j])
                            count['logical_shared_pairs']+=int(b[i]==b[j])
        rows.append(dict(source=str(source),capture_sha256=sha(path),**count))
    if not rows:raise ValueError('no verified captures')
    return dict(scope='accepted query-atom witness pairs; not port multiplicity or transfer count',
        synthetic_only=True,cases=rows,totals={k:sum(r[k] for r in rows) for k in ('samples','physical_alias_pairs','logical_shared_pairs')})

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('output',type=Path);p.add_argument('--sources',type=Path);a=p.parse_args()
    result=audit(a.directory,a.sources);a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result['totals']))
