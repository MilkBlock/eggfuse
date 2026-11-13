#!/usr/bin/env python3
"""Replay unchanged four-worker inputs once for work and semantic checks."""
from pathlib import Path
import runpy
import sys

if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    base = runpy.run_path(str(Path(__file__).parents[1] / 'cell-worker-runs/run.py'))
    base['run'](*(Path(arg).resolve() for arg in sys.argv[1:]), control_commit='b9b93023')
