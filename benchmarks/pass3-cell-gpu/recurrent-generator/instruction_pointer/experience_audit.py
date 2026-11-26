"""P0: independently check the historical controls against their tapes and native terminal states."""

import json
from collections import Counter
from math import prod
from pathlib import Path

from coverage_report import frozen_results
from discovery_score import write_csv
from discovery_states import cli, read, replay
from recursive_coverage import Target, snapshot
from recursive_train import folder
from response_study import memory


def audit(a):
    root = a.out.parent / "coverage-loss" / "confirmed"
    dest = a.out / "accounting"
    dest.mkdir(parents=True, exist_ok=True)
    rows = []
    stalls = []
    for case in a.cases:
        d = folder(a.data, case)
        target = Target(
            read(d / "program.json"),
            snapshot(a.data, d, "reference", "-", None, dest / "reference.json")[0],
        )
        initial = target.match(
            snapshot(a.data, d, "reference", "-", 0, dest / "reference.json")[0]
        )
        m = memory(a, d)
        for path in sorted(root.glob(f"native/*/*/native-address/{case}/*/run.json")):
            v = read(path)
            directory = path.parent / (case + "-stream-multi")
            f = dest / "memory.jsonl"
            played = replay(
                a, case, directory / "issued.json", "--memory", f, "--ept-origins"
            )
            verdict = v["verdicts"]
            assert played["state_sha"] == v["state_sha"]
            assert played["counts"]["accepted"] == verdict.get("accepted", 0)
            assert sum(verdict.values()) == v["paid"] == v["trace"][-1]["paid"]
            ops = sum(played["ept"]["signed_external"]) + sum(
                played["ept"]["signed_internal"]
            )
            assert ops == v["signed_ops"]
            assert (
                set(v["facts"])
                == target.match(read(directory / "state.json")) - initial
            )
            by = Counter()
            ports = {}
            grant = 0
            with f.open() as stream:
                for frame in map(json.loads, stream):
                    for addr in frame["retired"]:
                        by[ports.pop((addr["token"], addr["op"]))] -= 1
                    for addr, rr in frame["updates"]:
                        key = addr["token"], addr["op"]
                        if key in ports:
                            by[ports[key]] -= 1
                        ports[key] = rr["table"]
                        by[rr["table"]] += 1
                    ids = m.template_options([r for r, _ in frame["rules"]])
                    grant += min(
                        32, sum(prod(by[t] for t in m.roles[r]) for r, _ in ids)
                    )
            complete = v["work"]["final_tokens"]
            short = v["device"].get("complete_shortfall", 0)
            unscheduled = grant - complete - short
            assert unscheduled >= 0, (path, grant, complete, short)
            rows.append(
                {
                    "case": case,
                    "arm": v["method"],
                    "seed": path.relative_to(root).parts[1],
                    "block": v["block"],
                    "facts": len(v["facts"]),
                    "paid": v["paid"],
                    "ops": ops,
                    "offered": grant,
                    "complete": complete,
                    "attempted_shortfall": short,
                    "unattempted": unscheduled,
                    "graph": v["state_sha"],
                }
            )
        if not case.startswith("grammar"):
            unit = a.out.parent / "discovery-control" / "rollout" / case / "3"
            for kind in ("oracle", "stream"):
                tape = read(unit / (kind + ".json"))
                rr = replay(a, case, unit / (kind + ".json"), 3, "--ept-origins")
                origins = dict(rr["ept"]["origins"])
                winners = [
                    q
                    for q in tape["requests"]
                    if q["run"] == 3 and origins.get(q["token"], 0) > 0
                ]
                assert [q["rule"] for q in winners] == [575, 575]
                stalls.append(
                    {
                        "case": case,
                        "run": 3,
                        "mode": kind,
                        "productive": len(winners),
                        "ops": sum(origins[q["token"]] for q in winners),
                    }
                )
        print(case, len(rows), flush=True)
    write_csv(dest / "replay.csv", rows)
    write_csv(dest / "stalls.csv", stalls)
    frozen_results(root, dest)
    historical = Path(__file__).parent / "run-recall" / "coverage-loss"
    for name in ("frozen.csv", "frozen-seeds.csv", "run3.csv"):
        if (historical / name).read_bytes() != (dest / name).read_bytes():
            raise ValueError(f"historical frozen accounting changed in {name}")


if __name__ == "__main__":
    audit(cli().parse_args())
