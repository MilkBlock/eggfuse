"""Fail on a changed decision and summarize paired timings from compare.py."""
import argparse
import json
from pathlib import Path
from statistics import median


def check(decisions):
    for stage in ("run1", "run2"):
        if decisions[stage]["any_discrete_difference_graphs"]:
            raise ValueError(f"{stage} activation, reference or field differs")
    if decisions["pair_symbol_differences"]:
        raise ValueError("The categorical part of Pair differs")


def summarize(report):
    bulk_count = 0
    timed_count = 0
    max_error = 0
    rows = []
    for label, panel in report["panels"].items():
        for kind in ("torch_vs_frozen", "eager_mlx_vs_frozen", "eager_torch_vs_eager_mlx"):
            check(panel[kind])
        if any(panel["changed_whole_graph_verdicts"].values()):
            raise ValueError(f"graph verdict differs in {label}")
        if not panel["audits"]["torch"] == panel["audits"]["mlx"] == panel["audits"]["frozen"]:
            raise ValueError(f"post-hoc audit differs in {label}")
        bulk_count += panel["torch_vs_frozen"]["graphs"]
        max_error = max(max_error, panel["torch_vs_frozen"]["pair_latent_max_abs"])
        timing = report["timings"][label]
        check(timing["direct_batch_one_parity"])
        timed_count += timing["direct_batch_one_parity"]["graphs"]
        lanes = timing["implementations"]
        if lanes["torch"]["audit"] != lanes["mlx"]["audit"]:
            raise ValueError(f"batch-one audit differs in {label}")
        if label.endswith("-none"):
            elapsed = {k:v["median_ms"] for k,v in lanes.items()}
            rows.append(dict(panel=label, **elapsed, ratio=elapsed["torch"]/elapsed["mlx"]))
    if bulk_count != 9216:
        raise ValueError("Incomplete frozen comparison")
    return dict(graph_evaluations=bulk_count, timed_evaluations=timed_count,
                decision_differences=0, frozen_latent_max_absolute_difference=max_error,
                unmasked_panel_ratios_median=median(r["ratio"] for r in rows),unmasked_timings=rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(json.loads(args.report.read_text())),indent=2))
