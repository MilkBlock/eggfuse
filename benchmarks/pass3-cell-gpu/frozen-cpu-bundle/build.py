from pathlib import Path
import argparse,sys,hashlib,json
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'joint-witness'))
import build as joint

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path)
    out=p.parse_args().out
    joint.build(out,True,True,True,cli_allocator=True,extensions=(
        'incremental-neural-index','baked-port-codes','adaptive-row-policy','witness-production-profile',
        'multi-root-pages','transaction-guards','single-signature-frontier','integrated-cpu-policy',
        'learned-prefix-feasibility','projected-single-verifier','prepared-port-blocks','learned-atom-constraints','tiered-port-projections','complete-generation','pair-source-frontier','lazy-equation-ports','published-single-headers',HERE.name))
    manifest=out/'build.json';info=json.loads(manifest.read_bytes())
    info['frozen_settings_sha256']=hashlib.sha256((HERE/'frozen-options.json').read_bytes()).hexdigest()
    embedded=out/'tree/engine/cell-runtime/examples/frozen-weights'
    if embedded.is_dir():
        info['embedded_checkpoints']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(embedded.glob('*.json'))}
    manifest.write_text(json.dumps(info,indent=1)+'\n')
