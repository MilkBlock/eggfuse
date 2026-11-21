"""Build Vec, inline-one and inline-two complete wave/staging executables."""
import argparse,importlib.util,json,hashlib,shutil,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('group_build',HERE.parent/'group-named-cells/build.py')
group=importlib.util.module_from_spec(s);s.loader.exec_module(group)

def build(out):
    group.base.joint.build(out,True,True,True,cli_allocator=True,extensions=(*group.base.EXTENSIONS,
        'speculative-cell-batches','run-proposal-waves','wave-cell-allocation','group-named-cells','resident-cell-slabs',HERE.name))
    tree=out/'tree';target=out/'target'
    shutil.copy2(out/'session',out/'vec')
    for i in (1,2):
        feature=f"precomputed-forest,slot-transfer-audit,fact-lane-{i}"
        common=['--release','--offline','--locked','-p','eggfuse-cell-runtime','--target-dir',target,'--features',feature]
        subprocess.run(['cargo','build',*common,'--example','joint_witness_session'],cwd=tree,check=True)
        shutil.copy2(target/'release/examples/joint_witness_session',out/f'inline{i}')
        subprocess.run(['cargo','test',*common,'--lib','inline_fact_lane_spill_move_and_roundtrip'],cwd=tree,check=True)
    (out/'identities.json').write_text(json.dumps({k:hashlib.sha256((out/k).read_bytes()).hexdigest() for k in ('vec','inline1','inline2')},indent=1)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('out',type=Path)
    build(p.parse_args().out)
