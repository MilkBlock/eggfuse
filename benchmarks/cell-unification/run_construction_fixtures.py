#!/usr/bin/env python3
"""Check emitted marker programs and run short frozen-runtime differentials."""
import argparse
import json
from pathlib import Path
import subprocess
from check_links import load, sha
from run_view_fixtures import run


def check(root, compiler, phase='construction'):
    source = Path('tools/cell-compiler/tests/fixtures/marker-construction.egg').read_text()
    bodies = {'handoff': source,
        'computed': source.replace('((Out (G (F x)) n))',
                                  '((Out (G (F x)) n) (Keep (Out (G (F x)) (+ n 1))))')}
    if phase == 'symbols':
        bodies = {'handoff': source, 'union': source.replace('(ruleset make)',
            '(ruleset merge) (ruleset later)\n'
            '(rule ((= a (N 0)) (= b (N 1))) ((union a b)) :ruleset merge)\n'
            '(rule ((= a (N 0))) ((Edge a 99)) :ruleset later)\n(ruleset make)')
            .replace('(run read) (run keep)',
                     '(run merge) (run read) (run later) (run read) (run keep)')}
    elif phase in ('bindings', 'candidates'):
        bodies = {'handoff': source,
                  'bindings': Path('tools/cell-compiler/tests/fixtures/marker-bindings.egg').read_text()}
    options = ('--marker-handoff', 'values')
    run(root, compiler, bodies, options)
    records = []
    for case in bodies:
        fixture = root / f'fixture-{case}'
        with (fixture / 'compile-baseline.log').open('w') as log:
            subprocess.run([str(root / 'compiler-baseline'), 'compile', '--source', str(fixture / 'source.egg'),
                '--output', str(fixture / 'compiled-baseline'), *options], stdout=log, stderr=subprocess.STDOUT, check=True)
        files = ('source_sk_mk.egg', 'marker-selection.json', 'marker-program.json', 'program.json')
        hashes = {name: sha(fixture / 'compiled' / name) for name in files}
        assert all(sha(fixture / 'compiled-baseline' / name) == digest for name, digest in hashes.items()), case
        report = load(fixture / 'compiled/marker-selection.json')
        assert report['selected'] > 0 and report['result_handoff']['new_marker_fields'] == 0
        assert sum(row['consumer_result_uses'] for row in report['result_handoff']['rules']) > 0
        records.append(dict(case=case, source_sha256=sha(fixture / 'source.egg'), unchanged_files=hashes,
            result_handoff=report['result_handoff'],
            compiler_sha256={'baseline':sha(root / 'compiler-baseline'), 'candidate':sha(compiler)}))
    (root / 'compiler-compare.json').write_text(json.dumps(records, indent=2) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('--phase', choices=('construction', 'symbols', 'bindings', 'candidates'), default='construction')
    args = p.parse_args()
    check(args.root, args.root / 'compiler-candidate', args.phase)
