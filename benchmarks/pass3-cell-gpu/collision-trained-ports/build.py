from pathlib import Path
import argparse,sys,shutil
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'joint-witness'))
import build as joint

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path)
    out=p.parse_args().out
    joint.build(out,True,True,True,cli_allocator=True,extensions=(
        'incremental-neural-index','baked-port-codes','adaptive-row-policy','witness-production-profile',
        'multi-root-pages','transaction-guards','single-signature-frontier','integrated-cpu-policy',
        'learned-prefix-feasibility','projected-single-verifier','prepared-port-blocks','learned-atom-constraints',HERE.name),examples=('bake_port_codes',))
    shutil.copy2(out/'target/release/examples/bake_port_codes',out/'bake')
