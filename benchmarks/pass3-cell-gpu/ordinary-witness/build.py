"""Build the Rust entry point in an independent pinned-source workspace."""
from pathlib import Path
import shutil,subprocess,sys
from patch import install,HERE
REV='3cf9cd5d'
def build(out):
    out.mkdir(parents=True,exist_ok=True)
    src=out/'workspace';src.mkdir(exist_ok=True)
    cmd=subprocess.Popen(['git','archive',REV,'engine/cell-runtime','engine/structural-key','Cargo.lock'],cwd=HERE.parents[2],stdout=subprocess.PIPE)
    subprocess.run(['tar','-xf','-','-C',str(src)],stdin=cmd.stdout,check=True);cmd.stdout.close();assert cmd.wait()==0
    (src/'Cargo.toml').write_text('[workspace]\nresolver="2"\nmembers=["engine/cell-runtime","engine/structural-key"]\n')
    crate=src/'engine/cell-runtime';install(crate)
    shutil.copyfile(HERE/'session.rs',crate/'examples/ordinary_session.rs')
    subprocess.run(['cargo','build','--release','--offline','--manifest-path',str(crate/'Cargo.toml'),'--features','precomputed-forest,slot-transfer-audit',
                    '--example','ordinary_session','--target-dir',str(out/'target')],check=True)
    shutil.copy2(out/'target/release/examples/ordinary_session',out/'session')
if __name__=='__main__':build(Path(sys.argv[1]))
