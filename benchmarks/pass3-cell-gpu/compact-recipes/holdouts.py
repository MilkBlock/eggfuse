"""Compile the two preregistered larger workloads without using execution traces."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
GPU = HERE.parent
CASES = ('jacobi-1d', 'conjugate-gradient')


def main(args):
    args.out.mkdir(parents=True, exist_ok=False)
    records = {}
    for case in CASES:
        program_dir = args.out / case
        image_dir = args.out / (case + '-image')
        subprocess.run(['cargo','cell-compile','--case',case,'--output',program_dir],check=True)
        program = program_dir / 'program.json'
        subprocess.run([sys.executable, GPU/'codec.py', program, image_dir],check=True)
        for seed in (1703,1709):
            subprocess.run([sys.executable,GPU/'joint-witness/prepare.py',program,image_dir,
                            args.out/f'{case}-{seed}', '--policy','certified','--seed',str(seed)],check=True)
        records[case] = hashlib.sha256(program.read_bytes()).hexdigest()
        (args.out/'manifest.json').write_text(json.dumps(records,indent=2)+'\n')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out',type=Path)
    main(parser.parse_args())
