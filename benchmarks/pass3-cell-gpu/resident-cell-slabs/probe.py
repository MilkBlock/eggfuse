"""Compile and run a destructive lifecycle case in a private copy of the measured source."""
import argparse,shutil,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('build',type=Path);p.add_argument('out',type=Path);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    tree=a.out/'tree';subprocess.run(['cp','-cR',a.build/'tree',tree],check=True)
    src=tree/'engine/cell-runtime/src'
    shutil.copyfile(HERE/'conformance.rs',src/'resident_lifecycle_test.rs')
    with (src/'resident_cell_pages.rs').open('a') as f:f.write('\ninclude!("resident_lifecycle_test.rs");\n')
    out=subprocess.run(['cargo','test','--release','--locked','--offline','-p','eggfuse-cell-runtime',
                        '--features','precomputed-forest,slot-transfer-audit','--target-dir',a.out/'target',
                        '--lib','private_lanes_become_visible_in_place_and_release_the_last_owner'],
                       cwd=tree,stdout=subprocess.PIPE,check=True)
    assert b'1 passed; 0 failed' in out.stdout
    (a.out/'test.txt').write_bytes(out.stdout.strip()+b"\n");print(out.stdout.decode(),flush=True)
