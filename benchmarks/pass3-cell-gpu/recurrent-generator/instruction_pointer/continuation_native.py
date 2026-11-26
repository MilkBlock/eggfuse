"""Independent GPU-resident generation, offline prefix exports and native EPT curves."""

import json
import subprocess
from collections import Counter
from time import perf_counter

import torch

from continuation_audit import arguments
from metal_scaling import CASES, models
from recursive_coverage import Target, snapshot
from recursive_train import binary, folder, read
from resident_stream import StreamPage
from response_plan import ResponsePolicy
from response_study import memory
from transaction_native import execute


@torch.no_grad()
def run(a):
    jobs = [(c, s, h) for c in a.cases for s in a.seeds for h in a.arms]
    series = "cost-prefix" if a.paid_curves else "native"
    for b in range(1 if a.paid_curves else 2):
        for case, seed, arm in jobs if b == 0 else reversed(jobs):
            out = a.out / f"{series}/s{seed}/{arm}/b{b}"
            out.mkdir(exist_ok=True, parents=True)
            endfile = out / f"{case}.json"
            if endfile.exists():
                continue
            d = folder(a.data, case)
            exp = out / f"{case}-export.json"
            target = Target(
                read(d / "program.json"),
                snapshot(a.data, d, "reference", "-", None, exp)[0],
            )
            initial = target.match(snapshot(a.data, d, "reference", "-", 0, exp)[0])
            started = perf_counter()
            m = memory(a, d)
            marks, rates = models("1M")
            weights = (
                a.previous / f"s{seed}/1M-n1000000"
                if arm == "prior"
                else a.out / f"s{seed}" / arm
            ) / "weights.pt"
            for net, sd in zip((marks, rates), torch.load(weights, weights_only=True)):
                net.load_state_dict(sd)
            counts = Counter()
            marks.device_stream = StreamPage(m, marks, rates, counts)
            editor = arm.startswith("editor")
            pol = ResponsePolicy(
                m,
                marks,
                {"editor" if editor else "flow": rates},
                "supervised-empty" if editor else "empty",
                1 if editor else 4,
                536,
                2,
            )
            journal = []
            if a.paid_curves:
                from continuation_budget import budget_curve, condition

                condition(pol, journal)
            setup = perf_counter() - started
            row = execute(
                a.data, case, study=pol, series=str(out.resolve()), seconds=480
            )
            work = out / f"{case}-stream-multi"
            assert row["termination"] == "schedule_end"
            wall = setup + row["runtime_setup_seconds"] + row["wall"]
            facts = sorted(target.match(read(work / "state.json")) - initial)
            reference = len(target.gold) - len(initial)
            tape = work / "issued.json"
            rep = json.loads(
                subprocess.check_output(
                    [
                        binary(a.data),
                        "replay",
                        d / "program.json",
                        tape,
                        "audit",
                        "--ept-origins",
                    ]
                )
            )
            eff = rep["ept"]
            ext = eff["signed_external"]
            internal = eff["signed_internal"]
            assert sum(ext) + sum(internal) == row["signed_ops"]
            curve = []
            for i in sorted(
                {
                    1,
                    2,
                    4,
                    8,
                    16,
                    row["runs"] // 4,
                    row["runs"] // 2,
                    3 * row["runs"] // 4,
                    row["runs"],
                }
            ):
                if not (1 <= i <= row["runs"]):
                    continue
                trace = row["trace"][i - 1]
                # Facts can retire. Export exact reference identities at each checkpoint.
                graph = snapshot(a.data, d, "replay", tape, i, exp)[0]
                curve.append(
                    {
                        "run": i,
                        "facts": len(target.match(graph) - initial),
                        "paid": trace["paid"],
                        "seconds": trace["elapsed"]
                        + setup
                        + row["runtime_setup_seconds"],
                    }
                )
            origins = dict(eff["origins"])
            per_run = Counter()
            for q in read(tape)["requests"]:
                per_run[q["run"]] += origins.get(q["token"], 0)
            assert sum(per_run.values()) == row["signed_ops"]
            row.pop("trace")
            row.update(
                arm=arm,
                seed=seed,
                block=b,
                cold_wall=wall,
                cold_eps=row["signed_ops"] / wall,
                reference=reference,
                facts=facts,
                coverage=len(facts) / reference,
                curve=curve,
                credited_by_request_run=dict(per_run),
                device=dict(counts),
            )
            if a.paid_curves:
                timed = read(a.out / f"native/s{seed}/{arm}/b0" / f"{case}.json")
                assert all(
                    timed[k] == row[k]
                    for k in ("paid", "facts", "state_sha", "signed_ops")
                )
                row["paid_curve"] = budget_curve(
                    a.data, d, out, tape, target, initial, journal, row
                )
            endfile.write_text(json.dumps(row) + "\n")
            print(
                b,
                case,
                seed,
                arm,
                len(facts),
                row["signed_ops"],
                row["paid"],
                round(wall, 2),
                flush=True,
            )


if __name__ == "__main__":
    p = arguments()
    p.add_argument("--seeds", type=int, nargs="+", default=[243, 536, 8201])
    p.add_argument("--arms", nargs="+", default=["prior", "editor", "flow"])
    p.add_argument("--paid-curves", action="store_true")
    p.add_argument("--cases", nargs="+", default=CASES)
    torch.set_num_threads(1)
    run(p.parse_args())
