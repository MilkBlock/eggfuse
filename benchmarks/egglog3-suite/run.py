#!/usr/bin/env python3
"""Paired pristine native egglog 2/3 replay of captured eggcc inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import signal
import statistics
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
ENV = {k: v for k, v in os.environ.items()
       if not k.startswith(('CELL_CPU_', 'RAYON_', 'EGGLOG_COUNT_', 'EGG_LAYOUT_'))}
ENV['RAYON_NUM_THREADS'] = '1'


def sha(path):
    with open(path, 'rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def invoke(binary, source, timeout):
    start = time.perf_counter()
    timer = ['/usr/bin/time', '-l'] if platform.system() == 'Darwin' else ['/usr/bin/time', '-f', 'RSS_KIB=%M']
    p = subprocess.Popen([*timer, str(binary), str(source)], env=ENV,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        return {'status': 'timeout', 'timeout_s': timeout}
    wall = time.perf_counter() - start
    out, err = out.decode(errors='replace'), err.decode(errors='replace')
    if p.returncode:
        return {'status': 'failed', 'returncode': p.returncode, 'stderr': err[-6000:]}
    ms = re.findall(r' ([\d.]+) ms', out)
    phases = re.findall(r'PHASE ([\d.]+) ([\d.]+) ([\d.]+)', out)
    rss = re.search(r'(\d+)\s+maximum resident set size' if platform.system() == 'Darwin' else r'RSS_KIB=(\d+)', err)
    if not ms or not phases or not rss:
        return {'status': 'invalid_report', 'stdout': out, 'stderr': err[-2000:]}
    return {'status': 'complete', 'inference_ms': float(ms[-1]), 'cli_ms': wall * 1000,
            'search_apply_ms': float(phases[-1][0]), 'merge_ms': float(phases[-1][1]),
            'rebuild_ms': float(phases[-1][2]),
            'process_peak_rss_bytes': int(rss[1]) * (1 if platform.system() == 'Darwin' else 1024)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--capture', type=Path, default=ROOT / 'out/eggcc-suite/capture')
    parser.add_argument('--repeat', type=int, default=3)
    parser.add_argument('--case', action='append', help='Optional source substring, for smoke runs only')
    parser.add_argument('--timeout', type=int, default=360)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    bins = {arm: args.output / 'bin' / arm for arm in ('egglog2', 'egglog3')}
    hashes = {arm: sha(path) for arm, path in bins.items()}
    manifest = json.loads((args.capture / 'manifest.json').read_text())
    metadata = {'binaries': hashes, 'capture_sha256': sha(args.capture / 'manifest.json'),
                'repeats': args.repeat, 'timeout_s': args.timeout, 'threads': 1,
                'filter': args.case, 'host': platform.platform(),
                'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'semantic_scope': 'original source execution; no native2/native3 final-state equivalence proof'}
    meta = args.output / 'metadata.json'
    if meta.exists():
        old = json.loads(meta.read_text())
        for key in ('binaries', 'capture_sha256', 'repeats', 'filter', 'timeout_s'):
            assert old[key] == metadata[key], f'Cannot resume changed {key}'
    meta.write_text(json.dumps(metadata, indent=2) + '\n')
    records = args.output / 'suite.jsonl'
    done = {(r['case'], r['pass_number']) for r in map(json.loads, records.read_text().splitlines())} if records.exists() else set()
    for phase in (3, 1, 2):
        for index, case in enumerate(manifest['cases']):
            name = case['source'].split('/benchmarks/passing/')[1]
            if args.case and not any(pattern in name for pattern in args.case):
                continue
            if (name, phase) in done:
                continue
            entry = case['passes'][phase - 1]
            source = args.capture / Path(case['directory']).name / Path(entry['input']).name
            assert sha(source) == entry['input_sha256']
            row = {'case': name, 'pass_number': phase, 'source_sha256': sha(source), 'samples': []}
            for iteration in range(args.repeat):
                order = ['egglog2', 'egglog3'] if (index + phase + iteration) % 2 == 0 else ['egglog3', 'egglog2']
                sample = {'iteration': iteration + 1, 'order': order}
                for arm in order:
                    sample[arm] = invoke(bins[arm], source, args.timeout)
                row['samples'].append(sample)
                if any(sample[arm]['status'] != 'complete' for arm in order):
                    break
            row['status'] = 'complete' if len(row['samples']) == args.repeat and all(s[a]['status'] == 'complete' for s in row['samples'] for a in bins) else 'failed'
            if row['status'] == 'complete':
                for arm in bins:
                    row[arm] = {key: statistics.median(s[arm][key] for s in row['samples'])
                                for key in row['samples'][0][arm] if key != 'status'}
                row['egglog2_over_3'] = row['egglog2']['inference_ms'] / row['egglog3']['inference_ms']
            assert {arm: sha(path) for arm, path in bins.items()} == hashes, 'Executable changed'
            with records.open('a') as stream:
                stream.write(json.dumps(row) + '\n')
            print(phase, index, name, row['status'],
                  round(row.get('egglog2_over_3', 0), 3), flush=True)


if __name__ == '__main__':
    main()
