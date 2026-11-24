"""Offline native interventions on when a static training recipe runs.

Paired arms start from identical input and differ on one occupancy interval.
Only equal final state hashes earn cost credit. Evaluation never calls this teacher.
"""

import argparse
from collections import Counter
from pathlib import Path
import torch

from benefit_corpus import sources
from protocol_learning import LearningPolicy, LearningStream
from protocol_experiment import dump
from transaction_native import execute
from txn_policy import ReadPlan, ResponseStream, plans

TRAIN = (
    "grammar-17118",
    "grammar-stride2-17118",
    "grammar-stride3-17119",
    *(n for n, _ in sources("") if "-held-" not in n),
    "loopfact",
)
CUTS = (0, 3, 12, 1000000000)


class Probe(LearningPolicy):
    def __init__(self, root, threshold):
        super().__init__(root, "B", route="chain")
        self.threshold = threshold
        self.events = Counter()
        self.used_plans = Counter()

    def run_snapshot(self, frame, pub, rd, model, txn, stats, deadline):
        for rule, wm in frame["rules"]:
            stream = ProbeStream(rd, model, rule, wm, stats, study=self)
            stream.transaction = txn
            for paths in stream.path_batches("stream", 0, deadline):
                txn.proofs_from_paths(stream, paths)


class ProbeStream(LearningStream):
    logits = ResponseStream.logits
    select_query = ResponseStream.select_query

    def programs(self, depth):
        compiled = plans(self.rd, self.rule, depth, True)
        if not getattr(self.study, "alternate", False):
            return compiled
        result = []
        ir = self.rd.iface.rules[self.rule]
        for plan in compiled:
            steps = []
            outputs = []
            for pc, operands in plan.steps:
                changed = []
                for link in operands:
                    if link is not None and link[0] == "local":
                        alternatives = [
                            i
                            for i, t in enumerate(outputs)
                            if i != link[1] and t == outputs[link[1]]
                        ]
                        if alternatives:
                            link = ("local", alternatives[0])
                    changed.append(link)
                steps.append((pc, tuple(changed)))
                slot = ir["query"][pc]["args"][-1]["slot"]
                outputs.append(ir["slots"][slot]["sort"]["name"])
            result.append(
                ReadPlan(plan.atom, steps[-1][1], plan.output_column, tuple(steps[:-1]))
            )
        return result

    def route_logits(self, features):
        values, counts = features.unique(dim=0, return_counts=True)
        for v, c in zip(values.tolist(), counts.tolist()):
            self.study.events[tuple(v)] += c
        return features[:, 1].expm1().round() - self.study.threshold

    def issue_program(self, plan, inputs):
        self.study.used_plans[self.rule, len(plan.steps), plan.atom] += len(inputs[0])
        return super().issue_program(plan, inputs)


def measure(root, dest, cases):
    torch.manual_seed(71423)
    torch.set_num_threads(1)
    dest.mkdir(exist_ok=True, parents=True)
    for case in cases:
        rows = []
        for rep, order in enumerate((CUTS, CUTS[::-1])):
            for cut in order:
                s = Probe(root, cut)
                m = execute(
                    root,
                    case,
                    study=s,
                    series=f"benefit-training/counter-{cut}",
                    seconds=180,
                )
                assert m["termination"] == "schedule_end"
                work = m["work"]
                rows.append(
                    dict(
                        cut=cut,
                        rep=rep,
                        sha=m["state_sha"],
                        wall=m["wall"],
                        paid=m["paid"],
                        visits=work.get("visits", 0),
                        failures=m["proof_paid"] - m["committed_tokens"],
                        accepted=m["committed_tokens"],
                        issued_plan_counts=[
                            [*key, n] for key, n in s.used_plans.items()
                        ],
                        features=[[*v, n] for v, n in s.events.items()]
                        if not rep
                        else [],
                        native=m["native_verify_seconds"],
                        encode=work.get("value_encode_seconds", 0),
                        ipc=work.get("request_write_seconds", 0)
                        + work.get("receipt_wait_seconds", 0),
                    )
                )
        dump(dest / (case + ".json"), rows)
        print(case, [r["paid"] for r in rows[:4]], flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("dest", type=Path)
    p.add_argument("cases", nargs="*")
    a = p.parse_args()
    measure(a.root, a.dest, a.cases or TRAIN)
