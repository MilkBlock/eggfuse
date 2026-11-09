#!/usr/bin/env python3
"""Record frozen inputs and source provenance without executing a workload."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def prepare(output, expected_candidate):
    records = {}
    for workload in ('sum-bits', 'raytrace'):
        manifest = json.loads((output / f'{workload}-manifest.json').read_text())
        for config in manifest['lanes'].values():
            for key in ('runtime', 'program'):
                name = config[key]
                records[name] = {'sha256': sha(name), 'bytes': Path(name).stat().st_size}
    assert records['out/witness-prefix/runtime-normal']['sha256'] == expected_candidate
    files = ['Cargo.toml', 'Cargo.lock', 'engine/cell-runtime/Cargo.toml', 'tools/cell-compiler/Cargo.toml']
    for root in ('engine/cell-runtime/src', 'tools/cell-compiler/src'):
        files.extend(str(path) for path in sorted(Path(root).rglob('*.rs')))
    metadata = {
        'scope': 'standalone Cell CPU; three-lane single-thread pilot; not native egglog',
        'repeat': 3, 'warmups': 1,
        'prepared_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'head_at_start': command('git', 'rev-parse', 'HEAD'),
        'features': 'sparse-cells,view-ports,storage-metrics',
        'profile': 'release; runtime built alone; no allocator or ordered-audit instrumentation',
        'build_command': 'cargo build --release --locked -j 2 -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics',
        'coordination': 'Root freezes production and explicitly releases CPU before timing; no concurrent build or benchmark.',
        'machine': {
            'chip': command('sysctl', '-n', 'machdep.cpu.brand_string'),
            'logical_cpus': int(command('sysctl', '-n', 'hw.logicalcpu')),
            'memory_bytes': int(command('sysctl', '-n', 'hw.memsize')),
            'os': command('sw_vers'), 'rustc': command('rustc', '--version'),
            'affinity': 'unavailable; native macOS scheduling',
        },
        'inputs': records,
        'source_manifest': {name: sha(name) for name in files},
        'harness_manifest': {name: sha(name) for name in [
            'benchmarks/raytrace-parallel/measure.py', 'benchmarks/condition-bake/collect.py',
            'benchmarks/witness-prefix/measure.py', 'benchmarks/witness-prefix/collect.py',
            'benchmarks/witness-prefix/prepare.py']},
        'allocation_status': 'Not collected by normal timing binaries; missing counters are not zero.',
        'semantic_checks': 'Exact raw state SHA and complete ordered Run schedule SHA, all lanes and samples including warmup.',
    }
    (output / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--candidate-sha256', required=True)
    args = parser.parse_args()
    prepare(args.output, args.candidate_sha256)
