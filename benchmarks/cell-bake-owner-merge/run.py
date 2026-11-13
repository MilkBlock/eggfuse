#!/usr/bin/env python3
"""Freeze the merged runtime and replay the unchanged parallel inputs once."""
from pathlib import Path
import runpy
import sys

if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    base = runpy.run_path(str(Path(__file__).parents[1] / 'cell-worker-runs/run.py'))
    base['run'](*(Path(arg).resolve() for arg in sys.argv[1:]), control_commit='26b1650b')
