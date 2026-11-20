"""Build in an isolated directory from the same source, overlays and allocator."""
import argparse
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'joint-witness'))
import build as joint

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('out', type=Path)
    p.add_argument('--rows',action='store_true')
    a=p.parse_args()
    joint.build(a.out,True,True,True,cli_allocator=True,
                extensions=('incremental-neural-index','baked-port-codes')+
                           (('adaptive-row-policy',) if a.rows else ())+ (HERE.name,))
