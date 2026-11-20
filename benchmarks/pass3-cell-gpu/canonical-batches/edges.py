"""Run the actual native Parents regressions with the pinned complete CPU crate."""
import argparse,os,shutil,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('build',type=Path);p.add_argument('--frame',action='store_true');a=p.parse_args()
    tree=a.build/'tree';dst=tree/('engine/cell-runtime/src/canonical_frames.rs' if a.frame else 'engine/cell-runtime/src/canonical_batch.rs')
    source=HERE/('frame.rs' if a.frame else 'roots.rs')
    # Allow adding cfg(test) coverage to an already-built experiment, retaining native release source.
    src=source.read_text()
    assert src.partition('#[cfg(all(test')[0].strip()==dst.read_text().partition('#[cfg(all(test')[0].strip()
    shutil.copy2(source,dst)
    subprocess.run(['cargo','test','--locked','--offline','--release','-p','eggfuse-cell-runtime','--features','precomputed-forest,slot-transfer-audit',
                    '--lib','canonical_frame_lifecycle' if a.frame else 'canonical_batch_lifecycle','--','--nocapture'],cwd=tree,env=dict(os.environ,CARGO_TARGET_DIR=str(a.build/'target')),check=True)
