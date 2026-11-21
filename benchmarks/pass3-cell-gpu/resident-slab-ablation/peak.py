"""Whole-process RSS from fresh native processes on the same checked source programs."""
import argparse,json
from pathlib import Path
from runpy import run_path
HERE=Path(__file__).resolve().parent
study=run_path(str(HERE/'study.py'));measure=run_path(str(HERE.parent/'verified-binding-transfer/peak.py'))['run']
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','timing','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.seed=1703;a.cap=8192;a.widths=[16,64,256]
    a.policy=json.loads((HERE.parent/'speculative-allocation-policy/policy.json').read_bytes())
    measure(a,('move','resident-16','resident-64','resident-256'),study['settings'])
