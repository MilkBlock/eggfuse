"""Offline report. Repeated clocks do not add extra experience or facts."""

from collections import defaultdict
from statistics import median

from discovery_score import write_csv
from discovery_states import read, save
from execution_control_data import arguments, exit_audit
from recursive_train import folder


def report(a):
    d = a.out / "report"
    d.mkdir(exist_ok=True)
    runs = []
    facts = []
    audits = []
    for path in sorted((a.out / "independent").glob("*/*/result.json")):
        v = read(path)
        facts.append(
            {k: v[k] for k in ("case", "arm", "seed", "block", "sha", "facts")}
        )
        runs.append(
            {k: y for k, y in v.items() if k not in ("device", "facts", "exits")}
            | dict(covered=len(v["facts"]), **v["exits"])
        )
        if (
            v["seed"] == 536
            and not v["block"]
            and v["arm"] in ("A", "C-paired", "C-matched", "C-live")
        ):
            h = read(path.parent / "history.json")["windows"]
            tape = read(path.parent / (v["case"] + "-stream-multi") / "issued.json")
            for r in sorted(
                {n for n in (2, 3, len(h) // 2, len(h)) if 0 < n <= len(h)}
            ):
                result = exit_audit(
                    a.runtime_binary,
                    folder(a.data, v["case"]) / "program.json",
                    tape,
                    r,
                )
                audits.append(
                    dict(
                        case=v["case"],
                        arm=v["arm"],
                        reason=h[r - 1]["reason"],
                        **result,
                    )
                )
    by = defaultdict(list)
    for v in runs:
        by[v["case"], v["arm"]].append(v)
    summary = []
    for (case, arm), rs in by.items():
        first = [v for v in rs if not v["block"]]
        assert len(first) == 2 and len(rs) == 3
        assert all(
            any(
                (v["sha"], v["paid"], v["ops"], v["seed"])
                == (u["sha"], u["paid"], u["ops"], u["seed"])
                for u in first
            )
            for v in rs
        )
        summary.append(
            {
                "case": case,
                "arm": arm,
                "coverage": sum(v["covered"] for v in first)
                / sum(v["reference"] for v in first),
                "ept": sum(v["ops"] for v in first) / sum(v["paid"] for v in first),
                "eps": median(v["eps"] for v in rs),
                "min_seconds": min(v["seconds"] for v in rs),
                "max_seconds": max(v["seconds"] for v in rs),
            }
        )
    live = []
    for file in sorted((a.out / "live").glob("*.json")):
        for p in read(file):
            s, c = p["seal"], p["continue"]
            live.append(
                {
                    "idx": p["idx"],
                    "cohort": p["cohort"],
                    "run": p["run"],
                    "stage": p["stage"][0],
                    "submitted": p["paid_prefix"],
                    "gained": len(p["gained"]),
                    "lost": len(p["lost"]),
                    "same_graph": s["sha"] == c["sha"],
                    "seal_ops": s["ops"],
                    "continue_ops": c["ops"],
                    "seal_seconds": s["wall"],
                    "continue_seconds": c["wall"],
                    "seal_paid": sum(len(v["tokens"]) for v in s["pages"]),
                    "continue_paid": sum(len(v["tokens"]) for v in c["pages"]),
                    "seal_graph": s["sha"],
                    "continue_graph": c["sha"],
                }
            )
    write_csv(d / "live.csv", live)
    write_csv(d / "summary.csv", summary)
    write_csv(d / "runs.csv", runs)
    save(d / "facts.json", facts)
    save(d / "exit-audits.json", audits)


if __name__ == "__main__":
    report(arguments().parse_args())
