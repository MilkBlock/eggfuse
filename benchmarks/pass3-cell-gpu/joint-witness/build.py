"""Build a single Rust graph/executor containing both learned witness providers."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
REV='31bf7e41'


def install(name,crate,file="patch.py"):
    path=HERE.parent/name/file
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.install(crate)


def build(out,shortlist,merge_child,root_recipe):
    if root_recipe and not (shortlist and merge_child):raise ValueError("root recipes require shortlist and merge child")
    out.mkdir(parents=True,exist_ok=False);tree=out/'tree';tree.mkdir()
    process=subprocess.Popen(['git','archive',REV,'engine/cell-runtime','engine/structural-key','Cargo.lock'],
                             cwd=HERE.parents[2],stdout=subprocess.PIPE)
    subprocess.run(['tar','xf','-','-C',tree],stdin=process.stdout,check=True)
    process.stdout.close();assert process.wait()==0
    (tree/'Cargo.toml').write_text('[workspace]\nresolver="2"\nmembers=["engine/cell-runtime","engine/structural-key"]\n')
    crate=tree/'engine/cell-runtime'
    # Multi-witness routing first, then single-witness routing in the remaining grammar.
    install('single-witness',crate);install('ordinary-witness',crate)
    if shortlist:install('ordinary-shortlist',crate,'overlay.py')
    from cell_audit import install as audit_cells
    audit_cells(crate)
    with (crate/'src/ordinary_witness.rs').open('a') as f:
        f.write('\npub fn disable(){STORE.with(|s|{s.replace(None);});}\n')
    shutil.copy2(HERE/'session.rs',crate/'examples/joint_witness_session.rs')
    if merge_child:
        install('joint-merge',crate,'overlay.py')
        session=crate/'examples/joint_witness_session.rs'
        old=session.read_text();assert old.count("const MERGE_SUPPORT: bool = false;")==1
        session.write_text(old.replace("const MERGE_SUPPORT: bool = false;","const MERGE_SUPPORT: bool = true;"))
    if root_recipe:install('joint-root-cells',crate,'overlay.py')
    target=out/'target'
    subprocess.run(['cargo','metadata','--offline','--format-version','1'],cwd=tree,stdout=subprocess.DEVNULL,check=True)
    subprocess.run(['cargo','build','--locked','--offline','--release','-p','eggfuse-cell-runtime','--features',
                    'precomputed-forest,slot-transfer-audit','--example','joint_witness_session','--target-dir',target],cwd=tree,check=True)
    shutil.copy2(target/'release/examples/joint_witness_session',out/'session')
    sources={p.name+':'+p.parent.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
             [HERE/'session.rs',*[HERE.parent/name/file for name,file in (('single-witness','single.rs'),('single-witness','patch.py'),
                ('ordinary-witness','ordinary.rs'),('ordinary-witness','patch.py'))]]}
    for name in ('ordinary-shortlist','joint-merge','joint-root-cells'):
        if (name=='ordinary-shortlist' and shortlist) or (name=='joint-merge' and merge_child) or (name=='joint-root-cells' and root_recipe):
            for path in (HERE.parent/name).glob('*.rs'):
                sources[f'{name}/{path.name}']=hashlib.sha256(path.read_bytes()).hexdigest()
            path=HERE.parent/name/'overlay.py';sources[f'{name}/overlay.py']=hashlib.sha256(path.read_bytes()).hexdigest()
    (out/'build.json').write_text(json.dumps(dict(base=REV,sources=sources,shortlist=shortlist,merge_child=merge_child,root_recipe=root_recipe),indent=1)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('out',type=Path);p.add_argument('--shortlist',action='store_true');p.add_argument('--merge-child',action='store_true');p.add_argument('--root-recipe',action='store_true');args=p.parse_args();build(args.out,args.shortlist,args.merge_child,args.root_recipe)
