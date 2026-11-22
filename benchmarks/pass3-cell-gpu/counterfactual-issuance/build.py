"""Build the native signed-block verifier with a single issuance intervention."""
from pathlib import Path
from runpy import run_path
import sys

here=Path(__file__).resolve().parent
base=run_path(str(here.parent/'ripsat-set-receipt/build.py'))
if __name__=='__main__':
    base['prior']['base']['base']['joint'].build(Path(sys.argv[1]),True,True,True,
        cli_allocator=True,extensions=(*base['EXTENSIONS'],'ripsat-issuance-rl',
        'ripsat-receipt-locality','ripsat-block-verifier','ripsat-prefix-fork',here.name))
