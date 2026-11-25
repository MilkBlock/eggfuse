"""Pack reproducible independent measurements and receipt-level attribution."""

import argparse
from collections import Counter
from pathlib import Path

from protocol_experiment import dump
from recursive_train import read


def measurements(row):
    work = row["work"]
    regions = [s for s in row["structures"] if s["mode"] == "Evidence"]
    tot = Counter()
    for s in regions:
        for k in (
            "operations",
            "bindings",
            "additional_attempts",
            "issued",
            "horizontal",
            "vertical",
            "later",
        ):
            tot[k] += s[k]
    if tot["operations"] != row["new_suffix_operations"].get("Evidence", 0):
        raise ValueError("native operation ledger mismatch")
    if sum(len(s["tokens"]) for s in regions) != len({t for s in regions for t in s["tokens"]}):
        raise ValueError("double-counted accepted token")
    return {
        "runs": row["runs"],
        "state_sha": row["state_sha"],
        "exact_endpoint": row["exact_endpoint"],
        "facts": row["facts"],
        "reference": row["reference"],
        "coverage": row["facts"] / row["reference"],
        "effective_operations": row["signed_ops"],
        "CCP_requests": row["paid"],
        "requests_and_decisions": row["charged_with_decisions"],
        "ept": row["ept"],
        "ept_including_decisions": row["signed_ops"] / row["charged_with_decisions"],
        "visits": work["visits"],
        "terminal_scores": work["complete_candidate_scores"],
        "parent_scores": work["parent_candidate_scores"],
        "interface_reads": work["interface_reads"],
        "synchronizations": row["synchronizations"],
        "verdicts": row["verdicts"],
        "open_actions": row["open_actions"],
        "activated": len(regions),
        "region_counts": dict(tot),
        "ear": tot["operations"] / tot["bindings"] if tot["bindings"] else None,
        "additional_binding_strata": {
            str(i): {
                "activations": sum(s["bindings"] == i + 1 for s in regions),
                "operations": sum(s["operations"] for s in regions if s["bindings"] == i + 1),
            }
            for i in (0, 1)
        },
        "extra_direct_branches": sum(max(0, s["horizontal"] - 1) for s in regions),
        "productive_activations": sum(s["operations"] > 0 for s in regions),
        "skip_and_overhead": {
            k: v
            for k, v in work.items()
            if k.startswith("evidence_")
            or k
            in (
                "struct_skip_evidence",
                "structure_scores",
                "boundary_scores",
                "open_partner_scores",
                "receipt_position_probes",
                "receipt_prefix_checks",
                "template_branch_scores",
            )
        },
    }


def summarize(store, destination):
    destination.mkdir(parents=True, exist_ok=True)

    def rows(case, arm):
        runs = [read(store / f"{case}-{arm}-{i}.json") for i in range(2)]
        if any(r["termination"] != "schedule_end" for r in runs):
            raise ValueError("incomplete schedule")
        metrics = measurements(runs[0])
        if metrics != measurements(runs[1]):
            raise ValueError(f"nondeterministic paired work on {case}/{arm}")
        if arm != "late":
            acts = [r for r in runs[0]["structures"] if r["mode"] == "Evidence"]
            dump(destination / f"{case}-{arm}-activations.json", acts)
        wall = [r["wall"] for r in runs]
        setup = [r["setup_seconds"] for r in runs]
        return dict(
            metrics,
            wall_seconds=wall,
            setup_seconds=setup,
            eps=[r["eps"] for r in runs],
            eps_with_policy_setup=[runs[0]["signed_ops"] / (w + s) for w, s in zip(wall, setup, strict=True)],
            measured_costs=[{k: v for k, v in r["work"].items() if k.endswith("_seconds")} for r in runs],
        )

    result = {}
    for case in ("fact", "loopfact", "sum-divisors"):
        arms = {arm: rows(case, arm) for arm in ("late", "early", "rl")}
        result[case] = {"arms": arms, "same_endpoint": len({m["state_sha"] for m in arms.values()}) == 1}
    dump(destination / "results.json", result)
    train = sorted(store.glob("sum-train-*-*.json"))
    if len(train) != 8:
        raise ValueError("expected eight mirrored exploration episodes")
    dump(destination / "training-work.json", {p.stem: measurements(read(p)) for p in train})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("store", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    summarize(args.store, args.destination)
