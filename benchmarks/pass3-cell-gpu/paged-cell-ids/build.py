"""Produce four otherwise identical native executables, including the unmodified hash storage control."""
import argparse,hashlib,importlib.util,json,shutil,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('composed_build',HERE.parent/'composed-cpu/build.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('out',type=Path);a=p.parse_args()
    base.joint.build(a.out,True,True,True,cli_allocator=True,extensions=(*base.EXTENSIONS,HERE.name))
    tree=a.out/'tree';target=a.out/'target'
    shutil.copy2(a.out/'session',a.out/'hash')
    for mode in ['arena','page16','page64']:
        subprocess.run(['cargo','build','--locked','--offline','--release','-p','eggfuse-cell-runtime',
            '--example','joint_witness_session','--features','precomputed-forest,slot-transfer-audit,receipt-'+mode,
            '--target-dir',target],cwd=tree,check=True)
        shutil.copy2(target/'release/examples/joint_witness_session',a.out/mode)
    (a.out/'identities.json').write_text(json.dumps({k:hashlib.sha256((a.out/k).read_bytes()).hexdigest() for k in ('hash','arena','page16','page64')},indent=1)+'\n')
