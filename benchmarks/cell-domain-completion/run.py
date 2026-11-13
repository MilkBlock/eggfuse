#!/usr/bin/env python3
"""Run the actual standalone Cell CPU on the unchanged frozen inputs."""
from pathlib import Path
import runpy
import sys

if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    runpy.run_path(str(Path(__file__).parents[1] / 'cell-worker-runs/run.py'))['run'](
        *(Path(p).resolve() for p in sys.argv[1:]), control_commit='b1ab039d')
