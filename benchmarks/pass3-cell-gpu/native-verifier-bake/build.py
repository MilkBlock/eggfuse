"""Build the reference compiler, emit rule kernels from a source program, then link them."""
import argparse,hashlib,importlib.util,json,shutil,subprocess
from pathlib import Path
from time import perf_counter
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('base_build',HERE.parent/'composed-cpu/build.py')
base=importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


def run(a):
    base.joint.build(a.out,True,True,True,cli_allocator=True,extensions=(*base.EXTENSIONS,HERE.name))
    binary=a.out/'session';tree=a.out/'tree';target=a.out/'target'
    code=tree/'engine/cell-runtime/src/baked_verifiers.rs'
    old_size=binary.stat().st_size
    start=perf_counter()
    subprocess.run([binary,'--emit-verifiers',a.program,code,a.out/'shapes.json'],check=True)
    elapsed=perf_counter()-start
    subprocess.run(['cargo','build','--locked','--offline','--release','-p','eggfuse-cell-runtime','--features','precomputed-forest,slot-transfer-audit','--example','joint_witness_session','--target-dir',target],cwd=tree,check=True)
    shutil.copy2(target/'release/examples/joint_witness_session',binary)
    (a.out/'generation.json').write_text(json.dumps(dict(
        program_sha256=hashlib.sha256(a.program.read_bytes()).hexdigest(),source_sha256=hashlib.sha256(code.read_bytes()).hexdigest(),
        emitted_bytes=code.stat().st_size,bootstrap_bytes=old_size,linked_bytes=binary.stat().st_size,
        native_generation_s=elapsed,native_generation_and_relink_s=perf_counter()-start),indent=1)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for k in ('program','out'):parser.add_argument(k,type=Path)
    run(parser.parse_args())
