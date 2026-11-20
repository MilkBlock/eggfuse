"""Use the same fresh-process high-water counter as previous receipt studies."""
import argparse
from pathlib import Path
from runpy import run_path

HERE=Path(__file__).resolve().parent
driver=run_path(str(HERE/'study.py'))
measure=run_path(str(HERE.parent/'verified-binding-transfer/peak.py'))['run']

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','timing','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.seed=1703;a.arms=['reference','classes','two-hit']
    measure(a,('reference','classes','two-hit'),driver['settings'])
