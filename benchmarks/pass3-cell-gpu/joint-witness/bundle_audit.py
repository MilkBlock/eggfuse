"""Offline prepare once; deny online access to the repository, source oracle and network."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace

from prepare import prepare


def audit(a):
    results={}
    for case in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
        anchor=case in ('sum-bits','dot-product')
        program=a.ref/case/'program.json' if anchor else a.corpus/case/'program.json'
        image=a.ref/f'release-input-{case}' if anchor else a.corpus/case/'input'
        reference=a.ref/f'events-{case}' if anchor else a.corpus/case/'observation'
        graph=hashlib.sha256((reference/'state.json').read_bytes()).hexdigest()
        for seed in (1703,1709):
            with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
                root=Path(tmp).resolve();shutil.copyfile(a.binary,root/'session');(root/'session').chmod(0o755)
                prepare(SimpleNamespace(program=program,image=image,out=root/'bundle',policy='certified',seed=seed))
                profile='(version 1)(allow default)(deny network*)(deny file-read* (subpath "/Volumes") (subpath "/Users") (subpath "/private/tmp") (subpath "/private/var/folders") (subpath "/System/Volumes/Data/Volumes") (subpath "/System/Volumes/Data/Users"))(allow file-read* (subpath "'+str(root)+'"))'
                guard=['/usr/bin/sandbox-exec','-p',profile]
                assert subprocess.run([*guard,'/bin/cat',reference/'state.json'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode
                run=subprocess.run([*guard,root/'session','--bundle',root/'bundle'],cwd=root,capture_output=True,text=True,check=True)
                report=json.loads(run.stdout)
                assert report['state_sha']==graph and report['remaining_rhs']==0 and report['neural_rhs']==report['rhs']
                expected=json.loads((a.proof/'results.json').read_bytes())[f'{case}/{seed}/certified']['use']
                assert report['root_cells_allocated']==expected['direct_roots'] and report['merge_counts'][5]==expected['direct_children']
                results[f'{case}/{seed}']=dict(report=report,files=sorted(f.name for f in (root/'bundle').iterdir()),reference_read_denied=True)
            a.out.write_text(json.dumps(results,indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('binary','ref','corpus','proof','out'):p.add_argument(k,type=Path)
    audit(p.parse_args())
