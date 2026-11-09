#!/usr/bin/env python3
"""Compare query-read publication on short neighbor and range workloads."""
import argparse
from pathlib import Path
from run_view_fixtures import run

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('--compiler', type=Path, default=Path('target/cell-unification-tests/debug/eggfuse-cell-compiler'))
    args = p.parse_args()
    run(args.root, args.compiler, {
        'neighbor': Path('tools/cell-compiler/tests/fixtures/neighbor-ports.egg').read_text(),
        'range': Path(__file__).with_name('read-range.egg').read_text(),
    })
