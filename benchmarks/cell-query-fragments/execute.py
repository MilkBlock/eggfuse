#!/usr/bin/env python3
"""Fresh work/semantic exports, sequentially; no performance claims."""
import gzip
from pathlib import Path
import runpy
import shutil
import subprocess
import sys


def execute(config, root, proof_inputs):
    benchmarks = Path(__file__).resolve().parents[1]
    run = runpy.run_path(str(benchmarks / 'cell-worker-runs/run.py'))['run']
    for lane, binary in (('control', root / 'control-runtime'),
                         ('candidate', root / 'checks/candidate-runtime')):
        destination = root / lane
        run(config, destination, binary, control_commit='67d32b09')
        state = destination / 'candidate-ray/state.json'
        with state.open('rb') as source, gzip.open(str(state) + '.gz', 'wb', compresslevel=1) as out:
            shutil.copyfileobj(source, out)
        state.unlink()
    subprocess.run([sys.executable, str(benchmarks / 'marker-handoff/choice_diagnosis.py'),
        str(proof_inputs), str(root / 'candidate/semantic-acceptance.json')], check=True)
    subprocess.run([sys.executable, str(Path(__file__).with_name('check.py')),
        str(root), str(root / 'results.json')], check=True)


if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    execute(*(Path(arg).resolve() for arg in sys.argv[1:]))
