import argparse
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'joint-witness'))
import build as joint
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);a=p.parse_args()
    joint.build(a.out,True,True,True,cli_allocator=True,extensions=('incremental-neural-index','baked-port-codes','adaptive-row-policy',
        'witness-production-profile','multi-root-pages','transaction-guards','single-signature-frontier','integrated-cpu-policy',HERE.name))
