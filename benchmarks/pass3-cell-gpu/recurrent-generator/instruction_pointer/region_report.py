"""Preserve every native result and compute measured Pareto points and same-graph comparisons."""

import argparse
import csv
import json
import shutil
from collections import defaultdict
from pathlib import Path
from statistics import median

from recursive_train import read
from region_transfer import HELD


def table(path, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def report(out, dest):
    dest.mkdir(exist_ok=True, parents=True)
    catalog_fit = sum(v["seconds"] for v in read(out / "donors.json").values())
    groups = defaultdict(list)
    catalogs = {}
    with (dest / "runs.jsonl").open("w") as f:
        for path in sorted((out / "runs").glob("*.json")):
            info = read(path)
            if path.name.endswith("catalog.json"):
                catalogs[path.name] = info
                continue
            label = path.name.split(".")[0][len(info["case"]) + 1 :]
            info["label"] = label
            f.write(json.dumps(info, sort_keys=True, separators=(",", ":")) + "\n")
            groups[info["case"], label, info["mode"]].append(info)
    expected = {f"pair{n}": ("ABCDE", 2) for n in (1, 2, 4, 8, 16, 32)}
    expected.update(
        {
            "seed137": ("ABCDE", 2),
            "seed211": ("ABCDE", 2),
            "clean32": ("ABCDE", 4),
            "confirm32": ("ABCDE", 4),
            "profile": ("ABCDE", 1),
            "routes32": ("E", 1),
        }
    )
    for label in ("common4", "common8"):
        expected[label] = (("common-topo", "common-trace"), 2)
    for case in HELD:
        for label, (arms, repeats) in expected.items():
            for arm in arms:
                rows = groups[case, label, arm]
                if sorted(r["block"] for r in rows) != list(range(repeats)):
                    raise ValueError(("incomplete timing series", case, label, arm))
                for row in rows:
                    if row["termination"] != "schedule_end" or row["paid"] != sum(row["verdicts"].values()):
                        raise ValueError(("incomplete native execution", case, label, arm))
    for n in (64, 128, 256, 512, 1024, 2048):
        case = f"scale-fork-{n}-1-17"
        for mode in ("old-scale", "owned-scale"):
            series = groups[case, "sizes", mode]
            if len(series) != 2 or any(not r["all_expected_values"] or r["covered"] != n for r in series):
                raise ValueError(("numerical reference mismatch", case, mode))
    (dest / "catalogs.json").write_text(json.dumps(catalogs, sort_keys=True, separators=(",", ":")) + "\n")
    with (dest / "publications.jsonl").open("w") as log:
        for path in sorted((out / "runs").glob("*-profile.*.jsonl")):
            for line in path.read_text().splitlines():
                log.write(
                    json.dumps(dict(series=path.stem, **json.loads(line)), separators=(",", ":")) + "\n"
                )
    frontier = []
    matched = []
    scales = []
    for (case, label, mode), runs in sorted(groups.items()):
        first = runs[0]
        if any(
            (r["state_sha"], r["covered"], r["paid"]) != (first["state_sha"], first["covered"], first["paid"])
            for r in runs
        ):
            raise RuntimeError(("unpaired outcomes", case, label, mode))
        if label == "sizes":
            profile = groups[case, "sizeprofile", mode][0]["work"]
            scales.append(
                dict(
                    size=int(case.split("-")[2]),
                    mode=mode,
                    covered=first["covered"],
                    paid=first["paid"],
                    median_wall=median(v["wall"] for v in runs),
                    median_eps=median(v["eps"] for v in runs),
                    median_continuation_s=median(v["work"]["continuation_seconds"] for v in runs),
                    min_continuation_s=min(v["work"]["continuation_seconds"] for v in runs),
                    max_continuation_s=max(v["work"]["continuation_seconds"] for v in runs),
                    future_wire_scans=profile.get("suffix_wire_inspections", 0),
                    compile_wire_reads=profile.get("compile_wire_reads", 0),
                    register_reads=profile.get("register_named_reads", 0),
                    publication_probes=profile.get("publication_probes", 0),
                    pin_writes=profile.get("publication_pins", 0),
                    operand_reads=profile.get("named_receipt_reads", 0),
                )
            )
        if not label.startswith(("pair", "seed", "common", "confirm", "clean")):
            continue
        w = first["work"]
        spent = [r["wall"] for r in runs]
        row = dict(
            case=case,
            label=label,
            arm=mode,
            covered=first["covered"],
            reference=first["reference"],
            coverage=first["covered"] / first["reference"],
            state_sha=first["state_sha"],
            paid=first["paid"],
            effective=first["signed_ops"],
            ept=first["ept"],
            eps=median(r["eps"] for r in runs),
            wall=median(spent),
            min_wall=min(spent),
            max_wall=max(spent),
            cold_eps=median(r["deployment_eps"] for r in runs),
            draft_tokens=w.get("final_tokens", 0),
            external_refs=w.get("generated_external_bindings", 0),
            forwards=first["policy_forwards"],
            port_probes=w.get("port_probe", 0),
            template_probes=w.get("template_probe", 0),
            selected=w.get("selected_high", 0),
            accepted_roots=w.get("instantiated", 0),
            completed=w.get("higher_completed", 0),
            suffix_rejects=w.get("suffix_rejected", 0),
            stale=w.get("stale_released", 0),
            still_open=w.get("open_instances", 0),
            duplicate=first["verdicts"].get("duplicate", 0),
            primitive_reused=w.get("neural_primitive_receipt_reuses", 0),
            suffix_reused=w.get("higher_overlap_reuses", 0),
            singleton_reads_avoided=w.get("avoided_singleton_reads", 0),
            bake_s=first["bake_seconds"],
            gnn_s=first["structure_seconds"],
            bake_ms_per_accepted=1000
            * (first["bake_seconds"] + first["structure_seconds"])
            / w["instantiated"]
            if w.get("instantiated")
            else "",
            pareto="",
        )
        for reuse in (1, 10, 100):
            row[f"amortized_eps_{reuse}"] = median(
                r["signed_ops"]
                / (
                    r["wall"]
                    + r["runtime_setup_seconds"]
                    + (
                        r["encoder_seconds"]
                        + r["policy_load_seconds"]
                        + r["bake_seconds"]
                        + r["structure_seconds"]
                        + (catalog_fit if mode in ("D", "E", "common-trace") else 0)
                    )
                    / reuse
                )
                for r in runs
            )
        frontier.append(row)
    for r in frontier:
        if not r["label"].startswith("pair"):
            continue

        def dominates(q):
            return (
                q["case"] == r["case"]
                and q["label"].startswith("pair")
                and all(q[k] >= r[k] for k in ("coverage", "eps", "ept"))
                and any(q[k] > r[k] for k in ("coverage", "eps", "ept"))
            )

        r["pareto"] = not any(dominates(q) for q in frontier)
    for a in frontier:
        for b in frontier:
            if (
                a["case"] != b["case"]
                or a["state_sha"] != b["state_sha"]
                or (a["arm"], b["arm"]) not in (("A", "E"), ("B", "C"), ("D", "E"), ("B", "D"))
            ):
                continue
            if a["label"] != b["label"] and not (
                a["arm"] == "A" and a["label"].startswith("pair") and b["label"].startswith("pair")
            ):
                continue
            matched.append(
                dict(
                    case=a["case"],
                    left=a["arm"],
                    right=b["arm"],
                    left_budget=a["label"],
                    right_budget=b["label"],
                    covered=a["covered"],
                    paid_saved=a["paid"] - b["paid"],
                    eps_delta=b["eps"] - a["eps"],
                    wall_saved=a["wall"] - b["wall"],
                )
            )
    table(dest / "frontier.csv", frontier)
    table(dest / "same-graph.csv", matched)
    table(dest / "continuation.csv", sorted(scales, key=lambda r: (r["size"], r["mode"])))
    for name in (
        "menu.json",
        "donors.json",
        "transfer.json",
        "overlap.json",
        "own-prefix-oracle.json",
        "semantic.json",
        "tests.log",
        "scale-fork-1024-1-17.json",
        "scale-fork-2048-1-17.json",
    ):
        shutil.copyfile(out / name, dest / name)

    with (dest / "neural-prefixes.jsonl").open("w") as f:
        for path in sorted((out / "signed").glob("*-routes32.0.E.empty.json")):
            f.write(json.dumps(dict(series=path.stem, **read(path)), separators=(",", ":")) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("dest", type=Path)
    a = p.parse_args()
    report(a.out, a.dest)
