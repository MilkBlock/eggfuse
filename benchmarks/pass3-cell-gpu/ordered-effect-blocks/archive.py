"""Archive compact reports and identify the native binaries that produced them."""
import argparse
import hashlib
import json
from pathlib import Path
from shutil import copyfile

HERE=Path(__file__).resolve().parent
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archive(a):
    a.out.mkdir(parents=True,exist_ok=True)
    files={}
    for name,build in [('positions',a.base),('writers',a.writer)]:
        core=build/'tree/engine/cell-runtime'
        info=json.loads((build/'build.json').read_bytes())
        files[name]=dict(pinned_source=info['base'],binary_sha256=sha(build/'session'),
                         compiled={str(p.relative_to(core)):sha(p) for p in
                          [core/'src/graph.rs',core/'src/runtime.rs',core/'src/cell_prefix.rs',core/'src/ordered_effect_blocks.rs',
                           core/'src/ordered_effect_audit.rs',core/'examples/joint_witness_session.rs']})
        if name=='writers':
            files[name]['compiled']['src/ordered_write_plan.rs']=sha(core/'src/ordered_write_plan.rs')
            files[name]['writer_overlay_sha256']=info['ordered_writer_source_sha256']
    evidence=[(a.study/'results.json','results.json'),(a.writer_study/'results.json','writers.json'),
              (a.fixture/'fixture.json','fixture.json')]
    if (a.fixture/'overflow.json').is_file():
        evidence.append((a.fixture/'overflow.json','overflow.json'))
    for source,dest in evidence:
        copyfile(source,a.out/dest)
    (a.out/'manifest.json').write_text(json.dumps(files,indent=1)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('base','writer','study','writer_study','fixture','out'):p.add_argument(key,type=Path)
    archive(p.parse_args())
