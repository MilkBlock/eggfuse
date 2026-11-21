"""Build a timed driver and a separate counting allocator driver from the same native source."""
import argparse,importlib.util,shutil,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('joint_base',HERE.parent/'composed-cpu/build.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)


def build(out):
    base.joint.build(out,True,True,True,cli_allocator=True,extensions=(*base.EXTENSIONS,HERE.name))
    tree=out/'tree';crate=tree/'engine/cell-runtime';target=out/'target'
    src=(crate/'examples/joint_witness_session.rs').read_text()
    allocator='#[global_allocator]\nstatic ALLOCATOR: eggfuse_cell_runtime::RuntimeAllocator = eggfuse_cell_runtime::RuntimeAllocator;'
    spot='        writeln!(out, "{}", report)?;'
    assert src.count(allocator)==src.count(spot)==1
    src=src.replace(allocator,(HERE/'allocator.rs').read_text())
    src=src.replace(spot,'''        if req["release_directory"]==true {
            let mut parts=[0;3];
            for (i,p) in parts.iter_mut().enumerate(){*p=drop_bytes(||runtime.graph.release_reverse_part(i));}
            report["reverse_drop_bytes"]=json!(parts);
            let mut held=None;
            let rest=drop_bytes(||{let graph=runtime.graph;held=Some(graph.program);});
            report["graph_remainder_drop_bytes"]=json!(rest);
            drop(held);
        }
'''+spot)
    (crate/'examples/owner_heap.rs').write_text(src)
    subprocess.run(['cargo','build','--release','--offline','--locked','-p','eggfuse-cell-runtime','--features','precomputed-forest,slot-transfer-audit','--example','owner_heap','--target-dir',target],cwd=tree,check=True)
    shutil.copy2(target/'release/examples/owner_heap',out/'heap')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('out',type=Path)
    build(p.parse_args().out)
