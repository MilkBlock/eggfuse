from pathlib import Path
import argparse,importlib.util
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('composed_build',HERE.parent/'composed-cpu/build.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);a=p.parse_args()
    base.joint.build(a.out,True,True,True,cli_allocator=True,extensions=(*base.EXTENSIONS,
        'perfect-receipt-replay','page-premise-programs','batched-cell-verifier','factored-receipt-pages','coordinate-cell-block',HERE.name))
