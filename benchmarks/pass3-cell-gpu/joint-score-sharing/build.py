import argparse
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'joint-witness'))
import build as base
spec=base.importlib.util.spec_from_file_location('single_scores',HERE/'overlay.py');m=base.importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);a=p.parse_args()
    native=base.install
    def install(name,crate,file='patch.py'):
        native(name,crate,file)
        if name=='joint-merge':m.install(crate)
    base.install=install;base.build(a.out,True,True)
