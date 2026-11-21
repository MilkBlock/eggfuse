"""Fresh-process RSS includes the live private wave, original Graph, startup and export."""
import argparse,json
from pathlib import Path
from runpy import run_path
HERE=Path(__file__).resolve().parent
study=run_path(str(HERE/'study.py'))
measure=run_path(str(HERE.parent/'verified-binding-transfer/peak.py'))['run']
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','weights','timing','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.seed=1703;a.policy=json.loads(a.weights.read_bytes())
    measure(a,('off','wave','named','all-lanes'),study['settings'])
