import argparse
from pathlib import Path
import shutil
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'joint-witness'))
import build as joint

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);a=p.parse_args()
    joint.build(a.out,True,True,True,True,extensions=('baked-port-codes','fresh-entrances'),examples=('bake_port_codes',))
    shutil.copy2(a.out/'target/release/examples/bake_port_codes',a.out/'bake')
