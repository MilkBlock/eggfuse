"""Run a warmup and three fresh native processes per layout for whole-process peak RSS."""
import argparse
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
run = run_path(str(HERE.parent/"verified-binding-transfer/peak.py"))["run"]
settings = run_path(str(HERE/"study.py"))["settings"]

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for k in ("exp", "native", "timing", "out"):
        p.add_argument(k,type=Path)
    a = p.parse_args()
    a.seed = 1703
    a.cap = 8192
    a.staged = True
    a.policy = json.loads((HERE.parent/"speculative-allocation-policy/policy.json").read_bytes())
    run(a, ("off","packed","group","packed_group"), settings)
