#!/usr/bin/env python3
"""Freeze provenance and equal-input serial/worker configurations for Raytrace."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runtime', type=Path)
    parser.add_argument('program', type=Path)
    parser.add_argument('compiler', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    runtime, program, compiler = (p.resolve() for p in (args.runtime, args.program, args.compiler))
    variants = {
        'local_serial': ['--local-congruence'],
        'scoped_serial': ['--local-congruence', '--scoped-queues'],
        **{f'overlap{n}': ['--local-congruence', '--guard-workers', str(n),
                          '--completion-batch-tasks', '16', '--overlap-completion'] for n in (2, 4)},
    }
    manifest = {'lanes': {k: {'runtime': str(runtime), 'program': str(program), 'args': v}
                          for k, v in variants.items()}}
    args.output.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output / 'manifest.json'
    if manifest_path.exists():
        assert json.loads(manifest_path.read_text()) == manifest
    else:
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    paths = {'runtime': runtime, 'program': program, 'compiler': compiler,
             'source': root / 'workloads/pass3/inputs/raytrace.eggpart',
             'catalog': root / 'workloads/pass3/catalogs/raytrace.json'}
    provenance = {
        'scope': 'Standalone Cell CPU; not native egglog',
        'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
        'platform': platform.platform(),
        'cpu': subprocess.check_output(['sysctl', '-n', 'machdep.cpu.brand_string'], text=True).strip(),
        'logical_cpus': int(subprocess.check_output(['sysctl', '-n', 'hw.logicalcpu'], text=True)),
        'files': {k: {'path': str(p), 'sha256': sha(p), 'bytes': p.stat().st_size} for k, p in paths.items()},
        'input_provenance': 'Regenerated named Raytrace with checked frozen catalog, then bake-cell-ownership --query-classes true. Previous temporary input was unavailable; no historical timing is used as a paired baseline.',
        'runtime_features': 'sparse-cells,view-ports,storage-metrics; release; no allocation metrics or overlap probes',
        'lane_scope': 'guard-workers counts the worker pool; the main coordinator is additional. Batch mode enables scoped queues. scoped_serial isolates that queue change. No scoped-execution, port-scopes or pure-epochs flags.',
        'semantics': 'Exact final state and complete ordered Run signature against local_serial; not an independent native egglog semantic proof.',
    }
    with (args.output / 'provenance.json').open('x') as f:
        f.write(json.dumps(provenance, indent=2) + '\n')
    print(manifest_path)


if __name__ == '__main__':
    main()
