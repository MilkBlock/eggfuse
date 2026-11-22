"""Summarize same-build source, smaller-first and trained first-read runs."""
import argparse
import json
from pathlib import Path

CASES = ("sum-bits", "dot-product", "gemm-bias-relu", "stable-argmax",
         "jacobi-1d", "conjugate-gradient", "3mm", "deriche")
CHECKS = ("rhs", "writes", "state_sha", "schedule", "mutation_trace")
WORK = ("candidate_visits", "order_decisions", "order_swaps", "route_probes",
        "route_build_rows", "first_scores", "second_scores", "summary_reads",
        "epoch_reads", "reads", "encoded_fields", "issued")


def compare(root):
    result = {}
    for case in CASES:
        arms = {}
        accounting = None
        for mode in ("source", "smaller", "learned"):
            row = json.loads((root / f"{case}-{mode}.json").read_bytes())
            counts = row["issuer"]
            if (row["failure"] is not None or counts["denied_budget"] or counts["abstained"] or
                row["aligned_prefix"] != row["runs"] or row["runs"] != row["source_runs"] or
                not all(row["checks"][name] for name in CHECKS)):
                raise ValueError((case, mode, row))
            receipts = (row["runs"], row["source_rhs"], counts["issued"], row["accepted"],
                        row["rejected"], row["named_reads"])
            if accounting is not None and receipts != accounting:
                raise ValueError((case, mode, "receipt counts changed", accounting, receipts))
            accounting = receipts
            arms[mode] = {key: counts[key] for key in WORK}
            arms[mode]["strict_trace"] = all(row["checks"].values())
        result[case] = dict(runs=accounting[0], rhs=accounting[1], accepted=accounting[3],
                            rejected=accounting[4], named_reads=accounting[5], arms=arms)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(compare(args.artifacts), indent=2) + "\n")
