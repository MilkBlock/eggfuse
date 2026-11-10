#!/usr/bin/env python3
"""Emit short matched-Cell fixtures and compare frozen runtimes, without timing."""
import argparse
from pathlib import Path
import subprocess
from run_retention_fixtures import run

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('--emitter', type=Path, required=True, help='Compiled emit_cell_source example')
    args = p.parse_args()
    root = args.root.resolve()
    sources = Path(__file__).resolve().parents[2] / 'tools/cell-compiler/tests/fixtures'
    legacy = (sources / 'matched-completion.egg').read_text().replace(
        ':ruleset make :name "producer"', ':ruleset complete :name "producer"').replace(
        '(run complete)', '(run complete) (run complete)')
    (root / 'legacy.egg').write_text(legacy)
    cases = dict(matched=sources / 'matched-completion.egg', boundaries=sources / 'matched-boundaries.egg',
        legacy=root / 'legacy.egg')
    for case, source in cases.items():
        subprocess.run([str(args.emitter.resolve()), str(source), str(root / f'fixture-{case}')], check=True)
    for audit in (True, False):
        run(root, tuple(cases), audit)
