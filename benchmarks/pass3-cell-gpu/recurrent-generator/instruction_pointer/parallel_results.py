"""Publish independently replayed request credit, costs and witnessed set recall."""

import argparse
import csv
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

from draft_results import csvfile
from recursive_train import binary, folder, read


def digest(value):
    return hashlib.sha256(value).hexdigest()


def compute(out, data, dest):
    dest.mkdir(parents=True, exist_ok=True)
    rows = []
    curves = []
    frozen = []
    cache = {}
    for path in sorted(out.glob("native/*/*/run.json")):
        x = read(path)
        case = x["case"]
        w = Counter(x["work"])
        dc = Counter(x["device_counts"])
        tape = path.parent / (case + "-stream-multi") / "issued.json"
        key = (case, digest(tape.read_bytes()))
        if key not in cache:
            result = json.loads(
                subprocess.check_output(
                    [
                        binary(data),
                        "replay",
                        folder(data, case) / "program.json",
                        tape,
                        "audit",
                        "--ept-origins",
                    ]
                )
            )
            cache[key] = dict(result["ept"]["origins"])
        gains = cache[key]
        assert sum(gains.values()) == x["signed_ops"]
        qr = read(tape)["requests"]
        direct = read(path.parent / "receipts.json")
        issued = {r[1] for r in direct}
        assert len(issued) == len(direct)
        verified = {
            (
                q["run"],
                q["rule"],
                tuple(
                    (p["address"]["token"], p["address"]["op"], p["version"])
                    for p in q["parents"]
                ),
            )
            for q in qr
            if q["token"] in issued
        }
        base = {k: x[k] for k in ("case", "arm", "slots", "steps", "pages", "block")}
        forwards = w["edit_forward_calls"]
        decisions = w["address_forward_calls"]
        row = dict(
            **base,
            covered=len(x["facts"]),
            reference=x["reference"],
            paid=x["paid"],
            effective=x["signed_ops"],
            ept=x["ept"],
            eps=x["cold_eps"],
            wall=x["cold_wall"],
            setup=x["cold_wall"] - x["wall"],
            state_sha=x["state_sha"],
            fact_sha=digest(json.dumps(x["facts"]).encode()),
            termination=x["termination"],
            pending=x["pending"],
            unissued_failed_dependency=w["unissued_failed_dependency"],
            waiting_at_selection=w["selected_waiting_dependency"],
            verified_distinct_direct=len(verified),
            credited_direct=sum(gains.get(r, 0) > 0 for r in issued),
            credited_all=sum(v > 0 for v in gains.values()),
            higher_completed=w["higher_completed"],
            repeat_signed=w["same_run_repeat_signed"],
            repeat_page=w["postedit_duplicate_excess"],
            duplicate_receipts=x["verdicts"].get("duplicate", 0),
            draft_compute=x["compute_paid"],
            computed=x["verdicts"].get("computed", 0),
            proof_accepted=x["committed_tokens"],
            edit_forwards=forwards,
            batched_decode_passes=dc["pages"] * x["steps"],
            direct_valid_per_decode_pass=len(verified)
            / max(1, dc["pages"] * x["steps"]),
            direct_credited_per_decode_pass=sum(gains.get(r, 0) > 0 for r in issued)
            / max(1, dc["pages"] * x["steps"]),
            address_decisions=decisions,
            valid_per_edit_pass=len(verified) / forwards if forwards else "",
            valid_per_address_decision=len(verified) / decisions if decisions else "",
            template_reads=w["template_address_reads"],
            parent_tree_and_copy=w["parent_tree_and_copy_decisions"],
            pivot_visits=w["device_pivot_visits"],
            local_port_checks=w["device_local_scan_steps"],
            projection_reads=w["owner_projection_reads"],
            action_sites=dc["action_sites"],
            mark_draws=w["mark_draws"],
            physical_lanes=dc["allocated_mark_lanes"],
            max_simultaneous_jobs=dc["largest_edit_batch"],
            readbacks=dc["boundary_readbacks"],
            uploads=dc["uploads"],
            upload_bytes=dc["upload_bytes"],
            download_bytes=dc["download_bytes"],
            ccp_sync=x["synchronizations"],
            sample_seconds=w["sampling_seconds"],
            memory_seconds=w["memory_seconds"],
            native_ns=x["txn_stats"]["execute_ns"],
            verdicts=json.dumps(x["verdicts"], sort_keys=True),
        )
        rows.append(row)
        if x["block"] == 0:
            g = Counter()
            signed = Counter()
            for q in qr:
                g[q["run"]] += gains.get(q["token"], 0)
                signed[q["run"]] += int(q["token"] in issued)
            total = valid = 0
            for z in x["trace"]:
                r = z["run"]
                total += g[r]
                valid += signed[r]
                if r in (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, x["last_run"]):
                    curves.append(
                        dict(
                            **base,
                            run=r,
                            paid=z["paid"],
                            accepted=z["accepted"],
                            direct_accepted=valid,
                            eventual_origin_ops=total,
                            elapsed=z["elapsed"] + row["setup"],
                        )
                    )
    for file in sorted(out.glob("frozen-*.json")):
        for x in read(file):
            row = {k: v for k, v in x.items() if k not in ("stats", "device")}
            s = Counter(x["stats"])
            d = Counter(x["device"])
            row.update(
                edit_calls=s["edit_forward_calls"],
                address_decisions=s["address_forward_calls"],
                template_reads=s["template_address_reads"],
                local_checks=s["device_local_scan_steps"],
                pivots=s["device_pivot_visits"],
                pages_read=d["boundary_readbacks"],
            )
            frozen.append(row)
    for name, items in (
        ("native", rows),
        ("curves", curves),
        ("frozen", frozen),
        ("budgets", read(out / "budget.json")),
        ("twins", read(out / "twins.json")),
        ("reference-frozen", read(out / "reference-frozen.json")),
    ):
        csvfile(dest / (name + ".csv"), items)
    audit = read(out / "audit-draws.json")
    for row in audit:
        for k in ("wrong_template", "incomplete", "repeat", "root_outside_witnesses"):
            row.setdefault(k, 0)
    csvfile(dest / "draws.csv", audit)
    weights = {f.name: digest(f.read_bytes()) for f in out.glob("*.pt")}
    (dest / "checkpoints.json").write_text(json.dumps(weights, indent=2) + "\n")
    for name in ("fit", "semantic"):
        (dest / (name + ".json")).write_bytes((out / (name + ".json")).read_bytes())
    with (Path(__file__).parent / "run-recall/draft-set/runs.csv").open() as f:
        csvfile(
            dest / "historical-stream.csv",
            [r for r in csv.DictReader(f) if r["arm"] == "stream"],
        )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("out", "data", "dest"):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    compute(a.out, a.data, a.dest)
