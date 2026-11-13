#!/usr/bin/env python3
"""Check original-source Bake catalogs on the actual four-worker path."""
import argparse
import hashlib
import gzip
import shutil
import json
from pathlib import Path
import runpy
import subprocess


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def run(repo, artifacts, catalogs, output):
    lease = runpy.run_path(str(repo / 'tools/local_jobs.py'))['current_lease']()
    assert __debug__ and lease and lease['kind'] == 'compute'
    manifest = read(artifacts / 'candidate/checked/manifest.json')
    build = read(artifacts / 'work.json')
    runtime = artifacts / 'candidate/checked/candidate-runtime'
    binary = sha(runtime)
    assert binary == manifest['runtime_sha256'] == build['lanes']['candidate']['build']['runtime_sha256']
    flags = manifest['lanes']['sum']['args']
    assert flags[flags.index('--query-workers') + 1] == '4' and '--cell-ownership' in flags
    original = Path(manifest['lanes']['sum']['program'])
    source = read(original)
    native = read(artifacts / 'candidate/checked/semantic-acceptance.json')
    assert native['status'] == 'pass'
    expected_state = native['input_sha256']['cpu_values']
    keys = runpy.run_path(str(repo / 'benchmarks/raytrace-parallel/measure.py'))['KEYS']
    effects = ('bindings', 'constructor_requests', 'constructor_reused', 'logical_facts_created',
               'function_updates', 'union_requests', 'unions', 'merge_calls')
    output.mkdir(exist_ok=False)
    result = dict(scope='actual four-worker Cell CPU; exact stage snapshots, bindings, final state and effects; not timing',
                  commit=build['commits']['candidate'], scheduler_job=lease['id'], runtime_sha256=binary,
                  native_sum_acceptance_sha256=sha(artifacts / 'candidate/checked/semantic-acceptance.json'),
                  lanes={})
    baseline = None
    for name, program in [('original', original), ('round1', catalogs / 'round1/program.json'),
                          ('round2', catalogs / 'round2/program.json')]:
        raw = read(program)
        assert raw['source_core'] == source['source_core']
        metadata = {'sha256', 'multi_stage', 'ownership_fragments'}
        assert {k:v for k,v in raw.items() if k not in metadata} == {k:v for k,v in source.items() if k not in metadata}
        destination = output / name
        command = [str(runtime), '--program', str(program), '--output', str(destination), *flags, '--audit-stages']
        (output / f'{name}-command.json').write_text(json.dumps(command, indent=2)+'\n')
        with (output / f'{name}.log').open('w') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
        report = read(destination / 'report.json')
        assert report['status'] == 'complete' and report['cell_ownership']['enabled']
        state = sha(destination / 'state.json')
        assert state == expected_state, f'{name}: fresh final state must match the native-accepted export'
        # These files contain source-stage state and ordered matched bindings,
        # not merely a count of logical rule matches.
        stage_file = destination / 'stages.json'
        binding_file = destination / 'binding-audit.json'
        snapshots = sha(stage_file)
        bindings = sha(binding_file)
        schedule = [[s[k] for k in keys] for s in report['steps']]
        logical = {k: report['stats'][k] for k in effects}
        evidence = (snapshots, bindings, schedule, logical)
        if baseline is None:
            baseline = evidence
        assert evidence == baseline, f'{name}: source-stage/ordered-binding/effect mismatch'
        result['lanes'][name] = dict(program=str(program), program_sha256=sha(program),
            state_sha256=state, stage_sha256=snapshots, bindings_sha256=bindings,
            runs=len(schedule), exact_stage_bindings_effects=True, lookups=report['key_lookup_calls'],
            ownership=report['cell_ownership']['stats'],
            preparation=report['query_workers']['stats']['execution']['constructor'])
        with stage_file.open('rb') as source_file, gzip.open(str(stage_file)+'.gz', 'wb', compresslevel=1) as compressed:
            shutil.copyfileobj(source_file, compressed)
        stage_file.unlink()
        (output / 'result.json').write_text(json.dumps(result, indent=2)+'\n')
        print(name, len(schedule), 'stage/bindings/effects exact', flush=True)
    assert sha(runtime) == binary
    result['status'] = 'pass'
    (output / 'result.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('Run without Python -O')
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'artifacts', 'catalogs', 'output'):
        parser.add_argument(name, type=Path)
    run(**vars(parser.parse_args()))
