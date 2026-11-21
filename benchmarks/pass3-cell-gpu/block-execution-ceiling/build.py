"""Link the measured verifier, dictionary issuer and ordered source program into the same binary."""
import argparse,importlib.util,os
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('composed_build',HERE.parent/'composed-cpu/build.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('out',type=Path);a=p.parse_args()
    os.environ['EGGFUSE_ORDERED_WRITE_STUDY']='1'
    base.joint.build(a.out,True,True,True,cli_allocator=True,extensions=(*base.EXTENSIONS,
            'perfect-receipt-replay','page-premise-programs','batched-cell-verifier',
            'factored-receipt-pages','coordinate-cell-block','ordered-effect-blocks','ordered-repair-reuse'))
