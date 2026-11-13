#!/usr/bin/env python3
"""Replay frozen sum/Ray inputs consecutively, separate from timing."""
from pathlib import Path
import runpy
import sys

if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    runpy.run_path(str(Path(__file__).parents[1] / 'cell-worker-runs/run.py'))['run'](
        *(Path(p).resolve() for p in sys.argv[1:]), control_commit='f0fb1443')
