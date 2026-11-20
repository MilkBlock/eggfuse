"""Archive small source, compiler and execution evidence for the joint build."""
import argparse,importlib.util,json
from pathlib import Path
import shutil
from joint_common import HERE,file_digest

spec=importlib.util.spec_from_file_location('pgo_archive',HERE.parent/'native-backend-pgo/archive.py')
archive=importlib.util.module_from_spec(spec);spec.loader.exec_module(archive)


def save(a):
    evidence=json.loads((a.build/'joint-build.json').read_bytes())
    prior=json.loads((a.reference/'build.json').read_bytes())
    evidence['vanilla_pgo']=prior['binaries']['vanilla-use']['sha256']
    evidence['vanilla_profile']=prior['donors']['vanilla']['profile_sha256']
    evidence['previous_neural_profile']=prior['donors']['learned']['profile_sha256']
    for mode,record in evidence['binaries'].items():
        assert record['sha256']==file_digest(a.build/f'learned-{mode}')
        record['runtime_codegen_units']=archive.units(a.build/f'learned-{mode}-target/aarch64-apple-darwin/release/deps')
    evidence['source_tree']=archive.tree_digest(a.exp/'incremental-request-ports-v1/tree')
    (HERE/'build-evidence.json').write_text(json.dumps(evidence,indent=1)+'\n')
    shutil.copyfile(a.study/'joint-results.json',HERE/'results.json')
    shutil.copyfile(a.transfer/'profile-transfer.json',HERE/'profile-transfer.json')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','reference','build','study','transfer'):p.add_argument(k,type=Path)
    save(p.parse_args())
