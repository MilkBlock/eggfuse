"""Frozen, whole-workload splits for real multistage Cell traces.

Choose splits before observing labels. No benchmark timings or test outcomes
select cases. Sources are existing frozen eggcc pass-3 captures.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

CASES=[('train','032-sum-bits'),('train','020-loopfact'),('validation','016-gcd'),('test','010-dot-product')]


def main():
    p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('output',type=Path);p.add_argument('--bin',type=Path,default=Path('target/debug/examples'));args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    manifest=dict(scope='CPU full source execution and Eq observer; no GPU takeover',cases=[])
    for split,case in CASES:
        source=args.capture/case/'pass-3-flat.egg';dest=args.output/case;dest.mkdir(exist_ok=True)
        start=time.perf_counter()
        subprocess.run([str(args.bin/'emit_cell_source'),str(source),str(dest)],check=True,timeout=120)
        compile_seconds=time.perf_counter()-start
        trace=dest/'relations.json';start=time.perf_counter()
        subprocess.run([str(args.bin/'gpu_supervision_live_trace'),str(dest/'program.json'),str(trace),'--relations'],check=True,timeout=120)
        capture_seconds=time.perf_counter()-start
        data=json.loads(trace.read_text())
        assert data['strict_audit_reference_equal'] and data['run_control_counts_equal']
        row=dict(split=split,case=case,source=str(source.resolve()),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),trace=str(trace.resolve()),trace_sha256=hashlib.sha256(trace.read_bytes()).hexdigest(),program_sha256=data['program_sha256'],runs=len(data['steps']),bindings=sum(len(r['audit']['bindings']) for r in data['runs']),compile_seconds=compile_seconds,capture_command_seconds=capture_seconds)
        manifest['cases'].append(row);(args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(row),flush=True)

if __name__=='__main__':main()
