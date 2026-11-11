#!/usr/bin/env python3
"""Enumerate the vendored non-proof CI .egg suite; retain every failure.
No source stripping, proof emulation, or term-equivalence relaxations.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import statistics
import subprocess
import sys
import time
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'benchmarks/marker-handoff'))
from audit import equivalent, UnresolvedState


def invoke(argv, cwd, timeout, log):
    start = time.perf_counter()
    with log.open('w') as f:
        child = subprocess.Popen([str(x) for x in argv], cwd=cwd, stdout=subprocess.PIPE,
                                 stderr=f, text=True, start_new_session=True)
        try:
            stdout, _ = child.communicate(timeout=timeout)
            log.with_suffix('.stdout').write_text(stdout)
            return child.returncode, stdout, time.perf_counter() - start
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.communicate()
            return 124, '', time.perf_counter() - start



def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bin-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--repeat', type=int, default=3)
    p.add_argument('--timeout', type=float, default=120)
    args = p.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    bindir = args.bin_dir.resolve()
    oracle = bindir / 'examples/upstream_suite'
    compiler = bindir / 'eggfuse-cell-compiler'
    runtime = bindir / 'eggfuse-cell-runtime'
    paths = sorted(x for x in (ROOT / 'egglog/tests').rglob('*.egg')
                   if 'fail-typecheck' not in x.parts and 'proofs' not in x.parts)
    os.environ['RAYON_NUM_THREADS'] = '1'
    os.environ['EGG_LAYOUT_ANALYSIS_THREADS'] = '1'
    result = {'contract':'upstream-grounded-final-state/v1', 'scope':'standalone Cell CPU; unmodified non-proof CI .egg inputs',
              'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'machine':platform.platform(), 'repeat':args.repeat, 'timeout_seconds':args.timeout,
              'binaries':{str(x.relative_to(bindir)):hashlib.sha256(x.read_bytes()).hexdigest() for x in (oracle,compiler,runtime)},
              'nightly_directory_present':(ROOT/'egglog/egglog-benchmarks').is_dir(), 'cases':[]}
    for source in paths:
        name = str(source.relative_to(ROOT/'egglog'))
        d = out / source.stem
        d.mkdir()
        row = {'source':name, 'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
        result['cases'].append(row)
        code, stdout, elapsed = invoke([oracle,'inspect',source], ROOT/'egglog', args.timeout, d/'inspect.log')
        row['preflight_seconds'] = elapsed
        if code:
            row.update(status='preflight_timeout' if code == 124 else 'unsupported', reason=(d/'inspect.log').read_text()[-2400:])
        else:
            code, stdout, elapsed = invoke([compiler,'compile','--source',source,'--output',d/'artifact'], ROOT/'egglog', args.timeout,d/'compile.log')
            row['compile_bake_seconds'] = elapsed
            if code:
                row.update(status='compile_timeout' if code == 124 else 'compile_failed',reason=(d/'compile.log').read_text()[-2400:])
            else:
                code, stdout, elapsed = invoke([oracle,'native',source,d/'native.json',args.repeat],ROOT/'egglog',args.timeout,d/'native.log')
                if code:
                    row.update(status='native_timeout' if code == 124 else 'native_failed', reason=(d/'native.log').read_text()[-2400:])
                else:
                    native = json.loads(stdout.splitlines()[-1])
                    row.update(native)
                    code, stdout, elapsed = invoke([runtime,'--program',d/'artifact/program.json','--output',d/'run','--audit-stages'],ROOT,args.timeout,d/'run.log')
                    if code:
                        row.update(status='runtime_timeout' if code == 124 else 'runtime_failed',reason=(d/'run.log').read_text()[-2400:])
                    else:
                        a = json.loads((d/'native.json').read_text())
                        b = json.loads((d/'run/state.json').read_text())
                        # Only compiler-introduced tables may be projected away;
                        # every original native table (even empty) remains authoritative.
                        tables = set(native['tables'])
                        try:
                            row['proof'] = equivalent(a,b,tables=tables,anchors=False)
                            row['status'] = 'pass'
                        except UnresolvedState as e:
                            row.update(status='inconclusive', reason=str(e))
                        except AssertionError as e:
                            row.update(status='difference', reason=str(e))
                        code, stdout, elapsed = invoke([compiler,'bench','--program',d/'artifact/program.json','--repeat',args.repeat],ROOT,args.timeout,d/'bench.log')
                        if code:
                            row['bench_error'] = (d/'bench.log').read_text()[-2400:]
                        else:
                            row['cell_bench'] = json.loads(stdout.splitlines()[-1])
        print(name, row['status'], flush=True)
        (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    result['counts'] = {s:sum(x['status']==s for x in result['cases']) for s in sorted({x['status'] for x in result['cases']})}
    assert result['binaries'] == {str(x.relative_to(bindir)):hashlib.sha256(x.read_bytes()).hexdigest() for x in (oracle,compiler,runtime)}, 'benchmark binaries changed'
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['counts']),flush=True)

if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('Do not run the semantic comparator with Python -O')
    main()
