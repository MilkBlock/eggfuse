"""Native runs; gold sets and origin accounting are read only after execution."""

import json
import subprocess
from collections import Counter
from time import perf_counter

import torch

from continuation_audit import arguments
from discrete_reference import Reference
from draft_dispatch import Dispatch
from metal_scaling import CASES, models
from recursive_coverage import Target, snapshot
from recursive_train import binary, folder, read
from resident_page import Page
from response_study import memory
from transaction_native import execute


@torch.no_grad()
def run(a):
    cases = a.cases
    for b in range(a.blocks):
        jobs = [(c, s) for c in cases for s in a.arms]
        for case, arm in jobs if b % 2 == 0 else reversed(jobs):
            dest = (a.out / a.label / f"{a.device}-s{a.seed}-{arm}-{b}").resolve()
            dest.mkdir(parents=True, exist_ok=True)
            result = dest / (case + ".json")
            if result.exists():
                continue
            d = folder(a.data, case)
            setup = perf_counter()
            dc = Counter()
            if arm == "stream":
                pol = Reference(original_order=True)
            else:
                m = memory(
                    a, d, read(d / "layouts.json")[0] if a.declared_layout else None
                )
                marks, rates = models("1M")
                weights = a.previous / f"s{a.seed}/1M-n1000000/weights.pt"
                for net, sd in zip(
                    (marks, rates), torch.load(weights, weights_only=True), strict=True
                ):
                    net.load_state_dict(sd)
                    net.eval()
                address = (
                    a.out / (arm.split("-")[1] + ".pt")
                    if arm in ("page-single", "page-multi")
                    else a.address
                )
                if address:
                    marks.load_state_dict(torch.load(address, weights_only=True))
                if arm in ("rule", "first", "later"):
                    from draft_stages import Hybrid

                    pol = Hybrid(m, marks, arm, a.draws)
                else:
                    if a.device == "mps":
                        marks.resident_page = Page(m, marks, rates, dc)
                    pol = Dispatch(
                        m,
                        marks,
                        {"flow": rates},
                        "empty",
                        4,
                        536,
                        2,
                        mode=arm.split("-")[0],
                    )
            if isinstance(pol, Dispatch) and a.switch_run:
                pol.switch_run = a.switch_run
            setup = perf_counter() - setup
            row = execute(a.data, case, study=pol, series=str(dest), seconds=a.seconds)
            work = dest / (case + "-stream-multi")
            tape = work / "issued.json"
            target = Target(
                read(d / "program.json"),
                snapshot(a.data, d, "reference", "-", None, dest / "ref.json")[0],
            )
            initial = target.match(
                snapshot(a.data, d, "reference", "-", 0, dest / "ref.json")[0]
            )
            facts = sorted(target.match(read(work / "state.json")) - initial)
            wall = setup + row["wall"] + row["runtime_setup_seconds"]
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
            origins = dict(rep["ept"]["origins"])
            gains = Counter()
            for q in read(tape)["requests"]:
                gains[q["run"]] += origins.get(q["token"], 0)
            assert sum(gains.values()) == row["signed_ops"]
            curve = []
            total = 0
            for tr in row.pop("trace"):
                r = tr["run"]
                total += gains[r]
                curve.append(
                    [
                        r,
                        tr["elapsed"] + wall - row["wall"],
                        getattr(pol, "by_run", {}).get(r),
                        tr["paid"],
                        total,
                    ]
                )
            row.update(
                case=case,
                arm=arm,
                seed=a.seed,
                block=b,
                covered=len(facts),
                facts=facts,
                reference=len(target.gold) - len(initial),
                cold_wall=wall,
                cold_eps=row["signed_ops"] / wall,
                device_counts=dict(dc),
                curve=curve,
            )
            if isinstance(pol, Dispatch):
                row.update(
                    catalog_higher=len(pol.m.menu),
                    zero_primitive=[r for r, v in enumerate(pol.m.roles) if not v],
                    zero_higher=[r for r in pol.m.menu if not pol.m.roles[r]],
                    unissued=len(pol.draft),
                    unpublished=sum(map(len, pol.delayed)),
                    pages=pol.journal,
                    receipts=pol.receipts,
                )
            result.write_text(json.dumps(row) + "\n")
            print(
                case,
                arm,
                b,
                row["termination"],
                len(facts),
                row["paid"],
                row["signed_ops"],
                round(wall, 2),
                flush=True,
            )


if __name__ == "__main__":
    p = arguments()
    p.add_argument("--device", choices=["cpu", "mps"], default="mps")
    p.add_argument("--arms", nargs="+", default=["fifo", "set", "page"])
    p.add_argument("--cases", nargs="+", default=CASES)
    p.add_argument("--seed", type=int, default=243)
    p.add_argument("--blocks", type=int, default=2)
    p.add_argument("--seconds", type=int, default=600)
    p.add_argument("--draws", type=int, default=4)
    p.add_argument("--label", default="")
    p.add_argument("--switch-run", type=int)
    p.add_argument("--declared-layout", action="store_true")
    p.add_argument("--address")
    torch.set_num_threads(1)
    run(p.parse_args())
