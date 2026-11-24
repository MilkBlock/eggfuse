"""Isolate computed evidence on independent rollouts, after freezing the policy."""

import argparse
from pathlib import Path
import torch
from benefit_policy import BenefitNet, BenefitPolicy, BenefitStream
from protocol_experiment import dump
from recursive_coverage import Target, snapshot
from recursive_train import folder, read
from transaction_native import execute


class InterventionStream(BenefitStream):
    def programs(self, depth):
        return (
            [] if self.study.intervention == "no-compute" else super().programs(depth)
        )

    def issue_program(self, plan, inputs):
        reply = super().issue_program(plan, inputs).clone()
        # Swap the returned hash only for successful computations from this
        # static program. Preserve typed bytes, status and observation presence.
        ix = torch.where(reply[:, 1] == 14)[0]
        if len(ix):
            old = reply[ix, 3].clone()
            new = old.roll(1)
            new[0] = self.study.previous.get(plan.steps, int(old[-1]))
            self.study.previous[plan.steps] = int(old[-1])
            reply[ix, 3] = new
            self.stats["changed_result_hashes"] += int((old != new).sum())
        return reply


class EvidencePolicy(BenefitPolicy):
    stream_class = InterventionStream


def run(root, out, cases):
    torch.set_num_threads(1)
    results = {}
    for case in cases:
        d = folder(root, case)
        path = root / "computation-benefit" / case / "align.json"
        target = Target(
            read(d / "program.json"), snapshot(root, d, "reference", "-", None, path)[0]
        )
        init = target.match(snapshot(root, d, "reference", "-", 0, path)[0])
        rows = {}
        for kind in ("initial-bypass", "no-compute", "swapped-result"):
            net = BenefitNet().eval()
            net.load_state_dict(torch.load(out / "residual.pt", weights_only=True))
            s = EvidencePolicy(
                root,
                net,
                "residual",
                "chain" if "benefit-" in case or "stride" in case else "learned",
                activate=kind != "initial-bypass",
            )
            s.intervention = kind
            s.previous = {}
            series = "benefit-evidence/" + kind
            m = execute(root, case, study=s, series=series, seconds=300)
            assert m["termination"] == "schedule_end"
            if kind == "initial-bypass":
                baseline = read(out / (case + ".json"))["arms"]["A"][0]
                assert all(
                    m[key] == baseline[key]
                    for key in ("state_sha", "paid", "verdicts", "proof_paid")
                )
            state = read(root / series / (case + "-stream-multi") / "state.json")
            rows[kind] = dict(
                derived=len(target.match(state) - init),
                paid=m["paid"] + m["work"].get("neural_controls", 0),
                visits=m["work"]["visits"],
                sha=m["state_sha"],
                changed=m["work"].get("changed_result_hashes", 0),
                proofs=m["proof_paid"],
                work=m["signed_ops"],
                wall=m["wall"],
            )
        results[case] = rows
        dump(out / "evidence.json", results)
        print(case, rows, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("cases", nargs="+")
    a = p.parse_args()
    run(a.root, a.out, a.cases)
