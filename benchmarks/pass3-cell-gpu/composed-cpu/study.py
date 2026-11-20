"""Measure published single-parent headers and computed multi-parent ports on the same programs."""
import argparse
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("paired_source", HERE.parent / "pair-source-frontier/study.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

HEADER_ARMS = {"headers", "combined", "combined-lazy"}
EAGER_ARMS = {"arithmetic", "combined"}
LAZY_ARMS = {"lazy", "combined-lazy"}


def choices(request, _args):
    arithmetic = dict(request, derived_ports={"mode": 1, "cache": True})
    lazy = dict(arithmetic, lazy_equations=4)
    return {
        "off": request,
        "arithmetic": arithmetic,
        "headers": dict(request, header_mode=3),
        "combined": dict(arithmetic, header_mode=3),
        "lazy": lazy,
        "combined-lazy": dict(lazy, header_mode=3),
    }


def inspect(name, output, result, rows):
    result.update(header=output["header_view"], equations=output["multi"]["equations"], lazy=output["multi"]["lazy_eq"])
    if name in EAGER_ARMS:
        assert result["equations"]["numeric_requests"] > 0
    if name in LAZY_ARMS:
        assert result["lazy"]["computed"] > 0 and result["lazy"]["table_hits"] > 0
    if name in HEADER_ARMS | LAZY_ARMS:
        reference = rows["off" if name == "headers" else "arithmetic"]
        for field in ("raw", "multi", "physical", "commits", "children", "cells"):
            assert result[field] == reference[field], (name, field)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("exp", "native", "out"):
        parser.add_argument(arg, type=Path)
    parser.add_argument("--cases", nargs="+", default=["sum-bits", "dot-product", "jacobi-1d", "conjugate-gradient"])
    parser.add_argument("--seed", type=int, choices=(1703, 1709), default=1703)
    parser.add_argument("--repeats", type=int, default=6)
    base.study(parser.parse_args(), choices, inspect, None)
