"""Archive the independent runs and derive cost frontiers, paired dispersion and setup amortization."""

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from shutil import copyfile
from statistics import median


def read(p):
    return json.loads(p.read_text())


def dump(p, v):
    p.write_text(json.dumps(v, indent=2, sort_keys=True) + "\n")


def csvfile(path, rows):
    with path.open("w") as file:
        w = csv.DictWriter(file, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def collect(a):
    report = a.report
    report.mkdir(parents=True, exist_ok=True)
    import platform

    import torch

    from recursive_train import binary, folder

    def digest(path):
        with path.open("rb") as file:
            return hashlib.file_digest(file, "sha256").hexdigest()

    cases = ("fact", "loopfact", "sum-divisors", "grammar-benefit-left-17119")
    inputs = {
        case: {
            key: digest(folder(a.root, case) / key)
            for key in ("program.json", "tape.json", "capture.json", "memory.jsonl")
        }
        for case in cases
    }
    inputs.update(
        runtime=digest(binary(a.root)),
        compiler=digest(a.compiler),
        base="0d3c4451",
        python=platform.python_version(),
        torch=torch.__version__,
        machine=platform.machine(),
    )
    dump(report / "inputs.json", inputs)
    datasets = {p.stem: read(p) for p in sorted((a.raw / "cases").glob("*.json"))}
    dump(report / "programs.json", datasets)
    copyfile(a.raw / "wiring.json", report / "wiring.json")
    copyfile(a.raw / "natural-witness.json", report / "natural-witness.json")
    copyfile(a.raw / "acceptance/semantic.json", report / "semantic.json")
    cats = {}
    groups = defaultdict(list)
    with (report / "native-runs.jsonl").open("w") as file:
        for p in sorted((a.raw / "runs").glob("*.json")):
            r = read(p)
            if p.name.endswith(".catalog.json"):
                cats[p.name.removesuffix(".catalog.json")] = r
                continue
            case = r["case"]
            label = p.name[len(case) + 1 :].split(".")[0]
            if r["protocol"] != "ccp-v0.1" or r["termination"] != "schedule_end":
                raise ValueError(p)
            print(json.dumps(dict(id=p.stem, series=label, **r), separators=(",", ":")), file=file)
            groups[case, label, r["mode"], r["method"], r["seed"]].append(r)
    dump(report / "catalogs.json", cats)
    summary = []
    for (case, series, mode, method, seed), rows in groups.items():
        r = rows[0]
        w = r["work"]
        if len({(s["state_sha"], s["paid"]) for s in rows}) != 1:
            raise ValueError("nondeterministic pair")
        walls = [s.get("deployment_wall", s["cold"]) for s in rows]
        warm = median(s["runtime_setup_seconds"] + s["wall"] for s in rows)
        fixed = median(walls) - warm
        src = datasets.get(case, {}).get("compile_seconds", 0)
        summary.append(
            dict(
                case=case,
                series=series,
                mode=mode,
                method=method,
                seed=seed,
                n=len(rows),
                covered=r["covered"],
                reference=r["reference"],
                coverage=r["covered"] / r["reference"],
                terminal=r["state_sha"],
                coverage_set=r["coverage_sha"],
                exact_endpoint=r["exact_endpoint"],
                paid=r["paid"],
                effective=r["signed_ops"],
                neural_tokens=w.get("final_tokens", 0),
                selected=w.get("selected_high", 0),
                bound=w.get("instantiated", 0),
                complete=w.get("higher_completed", 0),
                open_at_end=w.get("open_instances", 0),
                suffix_paid=w.get("lowered_suffix", 0),
                external_bindings=w.get("generated_external_bindings", 0),
                parent_probes=w.get("port_probe", 0),
                template_probes=w.get("template_probe", 0),
                decision_forwards=r["policy_forwards"],
                untriggered=r["untriggered_rate"],
                facts_per_paid=r["facts_per_paid"],
                ept=r["ept"],
                eps=r["signed_ops"] / median(walls),
                seconds=median(walls),
                min_seconds=min(walls),
                max_seconds=max(walls),
                includes_shared_load="deployment_wall" in r,
                source_compile_s=src,
                menu_bake_s=r["bake_seconds"],
                code_s=r["structure_seconds"],
                gnn_setup_s=r["encoder_seconds"],
                sample_s=median(s["work"].get("sampling_seconds", 0) for s in rows),
                native_execute_s=median(s["txn_stats"]["execute_ns"] * 1e-9 for s in rows),
                warm_s=warm,
                per_job_1=warm + (fixed + src),
                per_job_10=warm + (fixed + src) / 10,
                per_job_100=warm + (fixed + src) / 100,
            )
        )
    csvfile(report / "paired.csv", summary)
    natural = [
        r
        for r in summary
        if not r["case"].startswith("scale-") and r["series"] in ("clean", "budget1", "budget4", "budget8")
    ]

    def dominates(q, r):
        return all(q[k] >= r[k] for k in ("coverage", "ept", "eps")) and any(
            q[k] > r[k] for k in ("coverage", "ept", "eps")
        )

    frontier = [
        dict(r, pareto=not any(dominates(q, r) for q in natural if q["case"] == r["case"])) for r in natural
    ]
    csvfile(report / "natural-frontier.csv", frontier)
    parents = Path("run-recall")
    files = [
        (parents / "discrete-computation-flow" / (name + ".pt"))
        for name in ("marks", "editor", "flow", "mask")
    ]
    files += [
        parents / "discrete-computation-flow/primitive-fit" / (name + ".pt")
        for name in ("marks", "editor", "flow", "mask")
    ]
    files += [parents / "parameterized-deep-ripsat/event-gnn.pt", parents / "cell-stream/multi.pt"]
    weights = report / "weights"
    weights.mkdir(exist_ok=True)
    for src, name in ((a.actor, "actor.pt"), (a.root / "structured-retrieval/field.pt", "field.pt")):
        if src.resolve() != (weights / name).resolve():
            copyfile(src, weights / name)
        files.append(weights / name)
    dump(report / "weights.json", {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in files})


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("raw", "report", "root", "actor"):
        p.add_argument(k, type=Path)
    p.add_argument("--compiler", type=Path, required=True)
    collect(p.parse_args())
