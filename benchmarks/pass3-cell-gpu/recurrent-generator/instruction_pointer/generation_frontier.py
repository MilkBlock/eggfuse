"""Independent native threshold sweeps and budget prefixes of the same live stream."""

import argparse
from pathlib import Path
from time import perf_counter
import torch
from benefit_policy import BenefitNet, BenefitStream
from protocol_model import ProtocolNet
from protocol_learning import LearningStream, LearningPolicy
from protocol_experiment import dump, digest
from recursive_train import binary, folder, read
from recursive_coverage import Target, snapshot
from transaction_native import execute
from txn_policy import ResponseStream

CASES = ("cyk801", "grammar-benefit-held-deep-11901379", "fact", "sum-divisors")
CUTS = (-6.0, -3.0, -1.0, 0.0, 1.0, 3.0)


class Threshold:
    def score_children(self, h, depth, paths, parents):
        s, z = super().score_children(h, depth, paths, parents)
        return (s - self.study.cut if depth + 1 == len(self.roles) else s), z


class Atomic(Threshold, ResponseStream):
    pass


class Typed(Threshold, LearningStream):
    pass


class Residual(Threshold, BenefitStream):
    pass


class Generator(LearningPolicy):
    def __init__(self, root, arm, cut, case):
        route = "chain" if "benefit-" in case or "stride" in case else "learned"
        model = BenefitNet() if arm == "residual" else ProtocolNet()
        if arm in ("residual", "B"):
            prefix = (
                "computation-benefit/residual.pt"
                if arm == "residual"
                else "protocol-learning/model.pt"
            )
            model.load_state_dict(
                torch.load(Path("run-recall") / prefix, weights_only=True)
            )
        super().__init__(root, "B", model.eval(), route=route)
        self.variant = arm
        self.cut = cut
        self.stream_type = {
            "A": Atomic,
            "B": Typed,
            "residual": Residual,
            "fixed": Atomic,
        }.get(arm)
        if arm == "fixed":
            self.mode = "always"
            self.chains = True

    def run_snapshot(self, frame, pub, rd, model, txn, stats, deadline):
        for row in (*pub[0], *pub[2]):
            self.ports.pop(self.memory_address(*row[:2]), None)
        for rule, wm in frame["rules"]:
            if perf_counter() >= deadline:
                raise TimeoutError
            stream = self.stream_type(
                rd,
                self.agent.compose if self.variant == "residual" else model,
                rule,
                wm,
                stats,
                study=self,
            )
            stream.transaction = txn
            for paths in stream.path_batches("stream", 0.0, deadline):
                txn.proofs_from_paths(stream, paths)


def experiment(root, out, case, arm, cut, repeat=0):
    if arm in ("trained", "unranked"):
        from generation_targets import TrainedGenerator

        study = TrainedGenerator(root, out, arm, cut, case)
    else:
        study = Generator(root, arm, cut, case)
    series = f"generation-frontier/{arm}-{cut:g}"
    dataset = folder(root, case)
    work = root / series / (case + "-stream-multi")
    m = execute(root, case, study=study, series=series, seconds=240)
    assert m["termination"] == "schedule_end", (case, arm, cut, m["termination"])
    ref, _ = snapshot(root, dataset, "reference", "-", None, work / "align.json")
    target = Target(read(dataset / "program.json"), ref)
    seed = target.match(
        snapshot(root, dataset, "reference", "-", 0, work / "align.json")[0]
    )
    trace = m.pop("trace")
    prior = Path("run-recall/computation-benefit") / (case + ".json")
    if prior.exists():
        reference = read(prior)["arms"]["A"][0]
    else:
        base = m if arm == "A" and cut == 0 else read(out / f"{case}_A_0_0.json")
        reference = dict(
            work=base["work"],
            all_paid=base["paid"] + base["work"].get("neural_controls", 0),
            wall=base["wall"],
        )
    # A budget cut consumes the last fully sealed Run within the limit. Nothing
    # from the next publication is credited. The ongoing stream can resume.
    budgets = {}
    for resource, full in (
        ("visits", reference["work"]["visits"]),
        ("tokens", reference["all_paid"]),
        ("elapsed", reference["wall"]),
    ):
        for fraction in (0.1, 0.5, 1.0):
            available = full * fraction
            index = next(
                (
                    i
                    for i, r in enumerate(trace)
                    if (
                        r["paid"] + r["controls"]
                        if resource == "tokens"
                        else r[resource]
                    )
                    > available
                ),
                len(trace),
            )
            budgets[f"{resource}@{fraction}"] = index
    stops = {
        0,
        len(trace),
        *budgets.values(),
        *(round(len(trace) * i / 10) for i in range(1, 10)),
    }
    points = {}
    if repeat:
        stops = {len(trace)}
        budgets = {}
    for i in sorted(stops if repeat == 0 else {len(trace)}):
        r = trace[i - 1] if i else dict(controls=0, paid=0, visits=0, elapsed=0)
        state, report = snapshot(
            root,
            dataset,
            "replay",
            work / "issued.json",
            i,
            work / "align.json",
            ept=True,
        )
        ops = sum(report["ept"]["signed_external"]) + sum(
            report["ept"]["signed_internal"]
        )
        points[i] = dict(
            signed_ops=ops,
            run=i,
            coverage=len(target.match(state) - seed),
            tokens=r["paid"] + r["controls"],
            visits=r["visits"],
            elapsed=r["elapsed"],
        )
    assert points[len(trace)]["coverage"] == len(
        target.match(read(work / "state.json")) - seed
    )
    assert points[len(trace)]["signed_ops"] == m["signed_ops"]
    m["paid_total"] = m["paid"] + m["work"].get("neural_controls", 0)
    m.update(
        arm=arm,
        threshold=cut,
        repeat=repeat,
        coverage=points[len(trace)]["coverage"],
        reference=len(target.gold) - len(seed),
        ept=m["signed_ops"] / max(m["paid_total"], 1),
        budget_stops=budgets,
        points=list(points.values()),
    )
    m.pop("guard_failures", None)
    m["build"] = digest(binary(root))
    if repeat == 0:
        dump(out / f"{case}_{arm}_{cut:g}_{repeat}.json", m)
    print(
        case, arm, cut, m["coverage"], m["paid_total"], round(m["wall"], 2), flush=True
    )
    return m


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--arms", nargs="+", default=["A", "B", "residual", "fixed"])
    p.add_argument("--cases", nargs="+", default=CASES)
    p.add_argument("--cuts", nargs="+", type=float, default=CUTS)
    a = p.parse_args()
    a.out.mkdir(exist_ok=True, parents=True)
    torch.set_num_threads(1)
    for c in a.cases:
        for t in a.cuts:
            for arm in a.arms:
                if arm != "fixed" or t == 0:
                    experiment(a.root, a.out, c, arm, t)
