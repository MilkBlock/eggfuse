"""Export reproducible measurements and verify budget, timing and accounting parity."""

import csv
import hashlib
import json
import sys
from pathlib import Path
from statistics import median


def load(p):
    return json.loads(p.read_text())


def csv_rows(dest, rows):
    with dest.open("w") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def emit(d, out):
    out.mkdir(parents=True, exist_ok=True)
    lengths = []
    timing = []
    free = []
    details = []
    identities = {}
    inputs = set()

    def read(name):
        path = d / name
        inputs.add(path)
        return load(path)

    def fields(r):
        a = r["stats"]
        c = r["count"]
        response = r["receipts"]
        fail = response["rejected"]
        assert c["signed"] == a["neural_tokens"] and a["paid"] == a[
            "neural_tokens"
        ] + a.get("internal", 0)
        assert a["paid"] == response["accepted"] + response["duplicates"] + sum(
            fail.values()
        )
        assert sum(c.get(f"length_{k}", 0) for k in range(4)) == c["opportunities"]
        assert sum(k * c.get(f"length_{k}", 0) for k in range(4)) == c["signed"]
        if r["budget"] == "paid":
            assert a["paid"] <= 96
        if r["budget"] == "slots":
            assert c["offered"] <= 384
        identities[r["graph"]] = r["facts"]
        return dict(
            case=r["case"],
            arm=r["arm"],
            budget=r["budget"],
            covered=r["covered"],
            reference=r["reference"],
            coverage=r["coverage"],
            ops=r["ops"],
            paid=a["paid"],
            budget_shortfall=96 - a["paid"] if r["budget"] == "paid" else "",
            ept=r["ept"],
            graph=r["graph"],
            signed=c["signed"],
            capacity=c["offered"],
            opportunities=c["opportunities"],
            **{f"length_{k}": c.get(f"length_{k}", 0) for k in range(4)},
            end_events=c.get("sampled_end", 0),
            boundary_readouts=c.get("boundary_readouts", 0),
            state_encodes=c["state_encodes"],
            untriggered=fail.get("untriggered_rule", 0),
            binding=fail.get("binding", 0),
            guard=fail.get("guard", 0),
            watermark=fail.get("watermark", 0),
            duplicate=response["duplicates"],
            accepted=response["accepted"],
            pending=r["pending"],
        )

    for case in ("fact", "loopfact", "sum-divisors"):
        for budget in ("slots", "paid", "full"):
            for seed in (71, 113):
                for arm in (
                    "fixed_iid",
                    "fixed_unique",
                    "variable_iid",
                    "variable_unique",
                ):
                    runs = [
                        read(f"{case}-{seed}-{budget}-{i}-{arm}.json") for i in range(4)
                    ]
                    r = runs[0]
                    for z in runs[1:]:
                        assert all(
                            z[k] == r[k]
                            for k in ("graph", "facts", "ops", "stats", "count")
                        )
                    ws = [v["wall"] for v in runs[2:]]
                    lengths.append(
                        dict(
                            **fields(r),
                            seed=seed,
                            productive_requests=r["productive_requests"],
                            distinct_productive_named=r["different_productive_named"],
                            complete_arity=json.dumps(r["arity"]),
                            distribution_reads=r["count"].get("distribution_reads", 0),
                            wall=median(ws),
                            wall_min=min(ws),
                            wall_max=max(ws),
                            eps=r["ops"] / median(ws),
                        )
                    )
                    for z in runs:
                        timing.append(
                            {
                                k: z[k]
                                for k in (
                                    "case",
                                    "arm",
                                    "budget",
                                    "seed",
                                    "rep",
                                    "wall",
                                    "eps",
                                    "decode",
                                    "prepare",
                                )
                            }
                        )
            for arm in ("KV", "sparse", "flat"):
                name = "sparse-paired" if arm == "sparse" else arm
                rs = [
                    read(f"free-binding-{case}-{budget}-{i}-{name}.json")
                    for i in range(2)
                ]
                r = rs[0]
                assert rs[1]["graph"] == r["graph"] and rs[1]["facts"] == r["facts"]
                wall = median(z["wall"] for z in rs)
                free.append(
                    dict(
                        **fields(r),
                        wall=wall,
                        eps=r["ops"] / wall,
                        wall_forward=r["wall"],
                        wall_reverse=rs[1]["wall"],
                        decode=median(z["decode"] for z in rs),
                        publication=median(z["publication_s"] for z in rs),
                        index_slots=r["count"].get("index_slots", 0),
                        fallback_slots=r["count"].get("fallback_slots", 0),
                    )
                )
        details.extend(read(f"binding-{case}.json"))
    csv_rows(out / "generation.csv", lengths)
    csv_rows(out / "timings.csv", timing)
    csv_rows(out / "free-binding.csv", free)
    (out / "interventions.jsonl").write_text(
        "".join(json.dumps(x, separators=(",", ":")) + "\n" for x in details)
    )
    (out / "facts.json").write_text(json.dumps(identities, separators=(",", ":")))
    windows = {}
    training = {}
    for seed in (71, 113):
        training[seed] = read(f"training-{seed}.json")
        inputs.add(d / f"boundary-{seed}.pt")
        for case in ("fact", "loopfact", "sum-divisors"):
            windows[f"{case}-{seed}"] = read(f"windows-{case}-{seed}.json")
    (out / "windows.json").write_text(json.dumps(windows, separators=(",", ":")))
    (out / "training.json").write_text(json.dumps(training, indent=2))
    (out / "device.json").write_text(json.dumps(read("device.json")))
    matched = []
    for arm in ("KV", "flat"):
        for rep in (2, 3):
            r = read(f"free-binding-loopfact-full-{rep}-{arm}.json")
            assert all(
                r[k] == read("free-binding-loopfact-full-0-KV.json")[k]
                for k in ("facts", "graph", "ops")
            )
            matched.append(
                {k: r[k] for k in ("case", "arm", "rep", "ops", "wall", "eps", "graph")}
            )
    csv_rows(out / "matched-binding.csv", matched)
    (out / "manifest.json").write_text(
        json.dumps(
            {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(inputs)
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    emit(Path(sys.argv[1]), Path(sys.argv[2]))
