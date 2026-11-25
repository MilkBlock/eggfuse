"""Native-verified relabeling and controlled two-action decoding on new Recipe graphs."""

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
import torch

from entry_closure import Tape
from higher_replacement import send
from latent_cell_flow import WIDTH, ZERO, Flow, Frozen, Published
from receipt_takeover import replay_many
from recursive_train import binary, read
from ripsat_policy import CellScorer, GraphBank
from rule_read import load_actor
from transaction_native import execute

SHAPES = {
    "chain2": [(-1,), (0,)],
    "chain3": [(-1,), (0,), (1,)],
    "chain5": [(-1,), (0,), (1,), (2,), (3,)],
    "diamond": [(-1,), (0,), (0,), (1, 2)],
    "shared": [(-1,), (0,), (0, -1), (1, 2)],
}


def fixture(root, compiler, name, family, value, scenario, *, dependencies=None):
    deps = SHAPES[family] if dependencies is None else dependencies
    symbols = ["Port" + str(i) for i in range(len(deps))] + ["Evidence"]
    script = [f"(relation {t} (i64))" for t in symbols]
    for i, src in enumerate(deps):
        atoms = " ".join(f"({symbols[j]} x)" for j in src)
        if scenario.startswith("guard") and i == 1:
            atoms += " (= x 41)"
        script.extend([f"(ruleset s{i})", f"(rule ({atoms}) (({symbols[i]} x)) :ruleset s{i})"])
    script.append(f"(Evidence {value})")
    if scenario in ("partial", "duplicate"):
        for symbol in symbols[: 1 if scenario == "partial" else len(deps)]:
            script.append(f"({symbol} {value})")
    script.append(
        "(run-schedule " + " ".join(f"(run s{i})" for i in [*range(len(deps)), len(deps) - 1]) + ")"
    )
    d = root / "recursive-agent" / name
    egg = d.with_suffix(".egg")
    egg.write_text("\n".join(script) + "\n")
    if not (d / "program.json").exists():
        with TemporaryDirectory(dir=d.parent) as scratch:
            target = Path(scratch) / "compiled"
            subprocess.run(
                [compiler, "compile", "--source", egg, "--output", target],
                stdout=subprocess.DEVNULL,
                check=True,
            )
            d.mkdir(exist_ok=True)
            (d / "program.json").write_bytes((target / "program.json").read_bytes())
    cap = subprocess.check_output(
        [
            binary(root),
            "capture",
            d / "program.json",
            d / "tape.json",
            "audit",
            "--memory",
            d / "memory.jsonl",
            "--ept",
        ]
    )
    (d / "capture.json").write_bytes(cap)
    tape = Tape(d, binary(root))
    # Lower the unique named producer for each static table. Ambiguity is outside this fixture.
    external = tape.rules.inputs[0][0]
    sources = {external: (-1, 0)}
    unit = []
    for rid, tabs in enumerate(tape.rules.inputs):
        wires = [sources[t] for t in tabs]
        unit.append((rid, rid, wires))
        for pc, s in tape.rules.rules[rid]["outputs"].items():
            if s["table"] in sources:
                raise ValueError("ambiguous static producer")
            sources[s["table"]] = (rid, int(pc))
    layout = d / "layouts.json"
    layout.write_text(json.dumps([unit]))
    occurrences = tape.occasions(unit)
    if len(occurrences) != 1 and scenario == "fresh":
        raise ValueError((name, occurrences))
    audit = (
        replay_many(d, binary(root), layout, [(0, occurrences[0])], tape.tape, read(d / "capture.json"))
        if occurrences
        else {"complete_teacher_instance": False}
    )
    return d, unit, audit


def pack(enc, unit, scorer):
    return GraphBank([unit], enc.cat, enc.nodes).encode(scorer)[0]


def predict(net, z, action, h=1, future=False):
    return net(
        z[None],
        torch.zeros(1, WIDTH * 2),
        action[None],
        torch.tensor([[float(h)]]),
        torch.tensor([[float(future), 0.0]]),
    )[0]


def example(d, unit, actor, scorer):
    enc = Frozen(read(d / "program.json"), actor, scorer)
    graph = pack(enc, unit, scorer)
    state = Published(enc)
    steps = []
    packets = {q["run"]: q for q in read(d / "tape.json")["requests"]}
    for f in map(json.loads, (d / "memory.jsonl").read_text().splitlines()):
        state.change(f, True)
        if f["run"] in packets:
            steps.append((state.total.float(), enc.token(packets[f["run"]], state.live)))
    if not steps or 0 not in [q["rule"] for q in packets.values()]:
        raise ValueError("fixture has no verified entry")
    if len(packets) != len(read(d / "tape.json")["requests"]):
        raise ValueError("multiple background proofs per stage")
    start, primitive = steps[0]
    high = torch.cat((graph, primitive[WIDTH:]))
    return enc, graph, (start, high, state.total.float() - start, steps)


def fit(base, examples):
    net = deepcopy(base)
    opt = torch.optim.AdamW(net.parameters(), lr=0.0005)
    for _ in range(80):
        losses = []
        for z, high, target, steps in examples:
            end = z + target
            predicted = predict(net, z, high)
            path = sum(predict(net, s, t) for s, t in steps)
            losses.extend(
                [
                    (predicted - target).square().mean(),
                    (predicted - path).square().mean(),
                    (predict(net, z, ZERO.repeat(2), len(steps), True) - target).square().mean(),
                ]
            )
            for i, (s, t) in enumerate(steps):
                actual = (steps[i + 1][0] if i + 1 < len(steps) else end) - s
                losses.append((predict(net, s, t) - actual).square().mean())
        opt.zero_grad()
        torch.stack(losses).mean().backward()
        opt.step()
    return net.eval()


class Choice:
    """Two actions at the entry event. CCP only consumes explicit, scheduled named requests."""

    def __init__(self, net, enc, unit, graph, arm):
        self.net = net
        self.enc = enc
        self.unit = unit
        self.graph = graph
        self.arm = arm
        self.state = Published(enc)
        self.wait = None
        self.count = Counter()

    def run_snapshot(self, frame, pub, rd, model, txn, stats, deadline):
        rows, _, retired, _ = pub
        self.state.change(
            dict(
                retired=[dict(token=int(t), op=int(o)) for t, o in retired],
                updates=[
                    (dict(token=int(r[0]), op=int(r[1])), rd.store.visible[int(r[0]), int(r[1])])
                    for r in rows
                ],
            ),
            True,
        )
        for rid, wm in frame["rules"]:
            # A selected, unfinished program may read only its specifically named receipts.
            exact = None
            if self.wait:
                ext, owners = self.wait
                j = len(owners)
                r, _, wires = self.unit[j]
                if r == rid:
                    addresses = [ext[p][:2] if s < 0 else (owners[s], p) for s, p in wires]
                    if all(a in self.state.live for a in addresses):
                        refs = [(*a, self.state.live[a][0]["version"]) for a in addresses]
                        if all(s >= 0 or refs[k] == ext[p] for k, (s, p) in enumerate(wires)):
                            exact = refs
                            receipt = send(txn, r, np.array([refs], dtype=np.int64))[0]
                            self.count["lowered_suffix"] += 1
                            self.count["suffix_rejected"] += int(receipt[1] != 0)
                            if receipt[1] == 0:
                                owners.append(int(receipt[0]))
                                self.count["completed"] += int(len(owners) == len(self.unit))
                            if receipt[1] != 0 or len(owners) == len(self.unit):
                                self.wait = None
            # Shared primitive proposal mechanism on the single-entry fixtures. No knowledge
            # of the teacher's bindings or future facts. Every physically typed row is scored.
            h = self.enc.graphs[rid][None]
            refs = []
            for slot, (table, _) in enumerate(rd.iface.roles[rid]):
                keys = list(rd.live[rd.tabs[table]])
                if not keys:
                    break
                vec = torch.stack([self.state.live[a][1] for a in keys])
                self.count["pointer_reads"] += len(keys)
                idx = (self.enc.actor.query(h) @ vec.T).argmax().item()
                a = keys[idx]
                refs.append((*a, self.state.live[a][0]["version"]))
                h = self.enc.actor.next_read(
                    vec[idx : idx + 1] + self.enc.nodes[self.enc.cat.inputs["generated", rid][slot]], h
                )
            if len(refs) != len(rd.iface.roles[rid]) or (exact is not None and exact == refs):
                continue
            choose = False
            if rid == 0 and self.arm != "primitive":
                q = dict(rule=rid, parents=[dict(address=dict(token=t, op=o), version=v) for t, o, v in refs])
                p = self.enc.token(q, self.state.live)
                h = torch.cat((self.graph, p[WIDTH:]))
                z = self.state.total.float()
                hp, pp = (predict(self.net, z, t) for t in (h, p))
                if self.arm == "desired":
                    desired = predict(self.net, z, ZERO.repeat(2), len(self.unit), True)
                    choose = bool((hp - desired).norm() < (pp - desired).norm())
                else:
                    choose = bool(hp.norm() > pp.norm())
                if self.arm == "forced":
                    choose = True
                self.count["menus"] += 1
                self.count["high_chosen"] += int(choose)
            answer = send(txn, rid, np.array([refs], dtype=np.int64))[0]
            self.count["network_actions"] += 1
            if choose and answer[1] == 0:
                self.wait = (refs, [int(answer[0])])
                self.count["instantiated"] += 1


def main():
    p = argparse.ArgumentParser()
    for arg in ("root", "compiler", "actor", "store"):
        p.add_argument(arg, type=Path)
    args = p.parse_args()
    root = args.root
    torch.set_num_threads(1)
    torch.manual_seed(137)
    actor = load_actor(args.actor, True)
    scorer = CellScorer(WIDTH).eval()
    scorer.load_state_dict(
        torch.load("run-recall/parameterized-deep-ripsat/event-gnn.pt", weights_only=True)["model"]
    )
    base = Flow().eval()
    base.load_state_dict(torch.load(args.store / "state137.pt", weights_only=True))

    def build(name, family, value, scenario="fresh"):
        d, u, audit = fixture(root, args.compiler, name, family, value, scenario)
        with torch.no_grad():
            enc, g, e = example(d, u, actor, scorer)
        return d, u, audit, enc, g, e

    records = [build("flow-train-" + str(i), "chain2", i * 11 + 3) for i in range(8)]
    donors = [r[-1] for r in records]
    signatures = {enc.cat.int_bake.key(u) for _, u, _, enc, _, _ in records}
    tuned = fit(base, donors)
    weights = args.store / "higher-flow.pt"
    torch.save(tuned.state_dict(), weights)
    results = {
        "donor_signatures": sorted(signatures),
        "donor": "chain2",
        "donors": 8,
        "weight_sha_before_eval_bake": hashlib.sha256(weights.read_bytes()).hexdigest(),
        "tests": {},
    }
    cases = [(f, "fresh", 101 + len(f)) for f in ("chain3", "chain5", "diamond", "shared")]
    cases.extend(
        ("chain3", s, 41 if s == "guard_true" else 42)
        for s in ("guard_true", "guard_false", "partial", "duplicate")
    )
    for family, scenario, value in cases:
        label = family if scenario == "fresh" else family + "-" + scenario
        case = "flow-test-" + label
        d, u, audit, enc, g, (z, h, target, steps) = build(case, family, value, scenario)
        if enc.cat.int_bake.key(u) in signatures:
            raise ValueError("leaked donor layout")

        def mse(x):
            return float((x - target).square().mean().detach())

        outputs = []
        with torch.no_grad(), TemporaryDirectory(dir=args.store) as tmp:
            for block in range(4):
                arms = ["primitive", "primitive_fit", "composed", "desired", "forced"]
                for arm in arms if block % 2 == 0 else arms[::-1]:
                    net = base if arm in ("primitive", "primitive_fit") else tuned
                    tick = perf_counter()
                    choice = Choice(net, enc, u, g, arm)
                    row = execute(root, case, study=choice, series=tmp)
                    row.pop("trace", None)
                    outputs.append(
                        dict(
                            arm=arm,
                            block=block,
                            counts=dict(choice.count),
                            same_end=row["state_sha"] == read(d / "capture.json")["state_sha"],
                            paid=row["paid"],
                            ept=row["ept"],
                            effective=row["signed_ops"],
                            eps=row["signed_ops"] / (row["wall"] + row["runtime_setup_seconds"]),
                            wall=row["wall"],
                            total_harness=perf_counter() - tick,
                        )
                    )
        results["tests"][label] = dict(
            layout=u,
            static_signature=enc.cat.int_bake.key(u),
            oracle=audit,
            zero_mse=mse(ZERO),
            primitive_fit_mse=mse(predict(base, z, h)),
            composed_mse=mse(predict(tuned, z, h)),
            runs=outputs,
        )
        (args.store / "higher.json").write_text(json.dumps(results, indent=2) + "\n")
        print(family, outputs[-3], flush=True)


if __name__ == "__main__":
    main()
