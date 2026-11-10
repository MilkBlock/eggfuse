#!/usr/bin/env python3
"""Compare frozen compilers/runtimes on short aliased and retired Cell sources."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from check_links import load, sha
from check_context import RUN_KEYS


def run(root, emitter):
    subprocess.run([str(emitter), str(root)], check=True)
    records = []
    for case in ('expanded', 'retired'):
        folder = root / f'fixture-{case}'
        # Match the source name used by the fixture helper. Bake decisions are
        # held fixed; the frozen compiler supplies every other old component.
        (folder / 'witness-sources').write_text((folder / 'source.egg').read_text())
        subprocess.run([str(root / 'emitter-baseline'), 'witness-sources', 'old-core'], cwd=folder, check=True)
        old = load(folder / 'old-core/program.json')
        new = load(folder / 'program.json')
        for k in ('spine_blocks', 'iterative_bake'):
            old[k] = new[k]
        assert {k: v for k, v in old.items() if k not in ('sha256', 'multi_stage')} == {
            k: v for k, v in new.items() if k not in ('sha256', 'multi_stage')}
        old.pop('sha256')
        old['sha256'] = hashlib.sha256(json.dumps(old, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        (folder / 'program-old.json').write_text(json.dumps(old, indent=2) + '\n')
        for audit in (False, True):
            for bits in (64, 0):
                outputs = []
                for lane in ('baseline', 'candidate'):
                    program = folder / ('program-old.json' if lane == 'baseline' else 'program.json')
                    output = folder / f'{lane}-{bits}-{int(audit)}'
                    argv = [str(root / f'runtime-{lane}'), '--program', str(program), '--output', str(output), '--local-congruence']
                    if audit:
                        argv.append('--audit-stages')
                    env = {'CELL_CPU_HASH_BITS': str(bits)}
                    start = time.monotonic()
                    with output.with_suffix('.log').open('w') as log:
                        subprocess.run(argv, env=dict(os.environ, **env), stdout=log, stderr=subprocess.STDOUT, check=True)
                    elapsed = time.monotonic() - start
                    assert elapsed < 1, 'short-fixture budget exceeded'
                    records.append(dict(case=case, lane=lane, bits=bits, audit=audit, argv=argv, env=env,
                        diagnostic_process_seconds=elapsed, runtime_sha256=sha(Path(argv[0])), program_sha256=sha(program)))
                    outputs.append(output)
                files = ('state.json', 'stages.json', 'binding-audit.json') if audit else ('state.json',)
                assert all(sha(outputs[0] / f) == sha(outputs[1] / f) for f in files), (case, bits, audit)
                reports = [load(p / 'report.json') for p in outputs]
                assert all(r['status'] == 'complete' for r in reports)
                assert [[s[k] for k in RUN_KEYS] for s in reports[0]['steps']] == [[s[k] for k in RUN_KEYS] for s in reports[1]['steps']]
    (root / 'fixture-runs.json').write_text(json.dumps(records, indent=2) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('--emitter', type=Path, required=True)
    args = p.parse_args()
    run(args.root.resolve(), args.emitter.resolve())
