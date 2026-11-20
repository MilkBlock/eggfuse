"""Measure header or scalar frontiers before any multi-parent value read."""
import argparse
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("source_study", HERE.parent / "pair-source-frontier/study.py")
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)
MODES = {"headers": 1, "headers-cut": 2, "scalar": 3, "scalar-cut": 4,
         "threshold": 5, "proof": 6, "carry": 7}


def settings(request, args):
    common = dict(request, derived_ports=dict(mode=1, cache=True), header_mode=3, lazy_equations=4)
    return {"off": common, **{arm: dict(common, source_watermarks=MODES[arm]) for arm in args.arms}}


def observe(arm, out, row, _):
    multi = out["multi"]
    row.update(frontier=multi["watermarks"], frame_rebuilds=multi["counts"]["table_rebuilds"],
               frame_rows=multi["counts"]["visible_rows"], incremental_frames=multi["delta_stats"])


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("exp", "native", "out"):
        p.add_argument(key, type=Path)
    p.add_argument("--arms", choices=MODES, nargs="+", default=list(MODES))
    p.add_argument("--cases", nargs="+", default=["sum-bits", "conjugate-gradient"])
    p.add_argument("--seed", type=int, default=1703)
    p.add_argument("--repeats", type=int, default=4)
    study.study(p.parse_args(), settings, observe, None)
