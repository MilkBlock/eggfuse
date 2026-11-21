from argparse import ArgumentParser
from pathlib import Path
from runpy import run_path
from shutil import copy2, copytree
import subprocess
from overlay import driver
HERE=Path(__file__).resolve().parent
base=run_path(str(HERE.parent/'verified-wave-execution/build.py'))
if __name__=='__main__':
    p=ArgumentParser();p.add_argument('out',type=Path);out=p.parse_args().out.resolve()
    base["base"]["joint"].build(out,True,True,True,cli_allocator=True,extensions=(*base["extensions"],HERE.name))
    tree=out/'vanilla-tree'
    copytree(HERE.parent/'compact-recipes/native',tree)
    manifest=tree/'Cargo.toml'
    manifest.write_text(manifest.read_text().replace('../../../../engine/cell-runtime',str(HERE.parents[2]/'engine/cell-runtime')))
    main=tree/'src/main.rs'
    driver(main,'request','rss_window')
    main.write_text(main.read_text()+'\nmod rss_window;\n')
    copy2(HERE/'window.rs',tree/'src/rss_window.rs')
    target=out/'vanilla-target'
    subprocess.run(['cargo','build','--release','--locked','--offline','--manifest-path',manifest,'--target-dir',target],check=True)
    copy2(target/'release/eggfuse-vanilla-benchmark',out/'vanilla')
