#!/usr/bin/env python3
"""Reuse the frozen shuffled campaign and separate background observations."""
from pathlib import Path
import runpy
import sys

if __name__ == '__main__':
    if not __debug__:
        raise SystemExit('run without Python -O')
    campaign = runpy.run_path(str(Path(__file__).parents[1] / 'cell-event-payload/campaign.py'))
    campaign['main'](Path(sys.argv[1]).resolve())
