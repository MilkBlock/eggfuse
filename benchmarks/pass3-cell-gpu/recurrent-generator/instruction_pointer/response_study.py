"""Native counterfactual supervision and independent paired CCP experiments."""

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
import torch

from boundary_inputs import BASE, native
from discrete_cells import Cell, Local, Marks, from_q, load_enc
from discrete_editor import Rates, train_positions
from discrete_study import marks_fit, record, views
from latent_cell_flow import TRAIN
from latent_composition import fixture
from recursive_coverage import Target, snapshot
from recursive_train import binary, folder, read
from region_bake import linked
from region_owner import Ownership
from response_open import OPEN, build
from response_plan import ResponseMemory, ResponsePolicy
from scaling_bake import save
from transaction_native import execute

OUT = Path("run-recall/response-edit")
OLD = Path("run-recall/discrete-computation-flow")
HELD = "response-held-merge6"


def memory(a, d, layout=None, bare=False):
    prog = read(d / "program.json")
    enc, scorer = load_enc(prog, a.actor)
    ct = native(binary(a.data), "receipt-contract", d / "program.json")
    menu = {layout[0][0]: layout} if layout else linked(prog, read(BASE / "menu.json"))
    return ResponseMemory(enc, ct, {} if bare else menu, scorer)


def train(a):
    rng = np.random.default_rng(123)
    net = Marks()
    records, addresses = [], []
    counts = Counter()
    sigs = set()

    def add(m, kind, src, dst):
        rec = record(m, src, dst)
        records.append(rec)
        counts[kind] += 1
        path = rec[-1]
        for k, (x, i, op, cell) in enumerate(path):
            if cell is not None:
                net.draw(
                    m,
                    rng,
                    Counter(),
                    x[i].cell if op == 2 else None,
                    cell,
                    addresses,
                    prefix=x[:i],
                    weight=(len(path) - k) / (len(path) + 1),
                )

    with torch.no_grad():
        for case in TRAIN:
            suff = read(OLD / "suffix-audit.json")[case]
            assert all(suff["checks"].values())
            d = folder(a.data, case.removesuffix("-roll"))
            m = memory(a, d)
            forks = {
                r["run"]: r
                for r in map(
                    json.loads, (a.forks / (case + ".jsonl")).read_text().splitlines()
                )
            }
            frames = (
                a.rollout / "sum-native-memory.jsonl"
                if case.endswith("-roll")
                else d / "memory.jsonl"
            )
            tape_path = (
                a.rollout / "sum-issued.json"
                if case.endswith("-roll")
                else d / "tape.json"
            )
            tape = read(tape_path)["requests"]
            receipt = native(
                binary(a.data),
                "replay",
                d / "program.json",
                tape_path,
                "time",
                "--ept-origins",
            )
            assert receipt["counts"]["accepted"] == len(tape)
            gains = dict(receipt["ept"]["origins"])
            by_run = defaultdict(list)
            for q in tape:
                if gains[q["token"]] > 0:
                    by_run[q["run"]].append(from_q(q))
            # Choose verified transitions in short consecutive windows. Only the actual
            # preceding Response and current unissued draft reach the encoder.
            windows = [r for r in sorted(by_run) if r - 1 in by_run][:12]
            selected = {v for r in windows for v in (r - 1, r)}
            with frames.open() as source:
                for frame in map(json.loads, source):
                    m.update(frame)
                    if frame["run"] in selected:
                        seq = by_run[frame["run"]][:3]
                        add(m, "published_window", [], seq)
                        if len(seq) > 1:
                            add(m, "published_completion", seq[:1], seq)
                        selected.remove(frame["run"])
                    row = forks.pop(frame["run"], None)
                    if row is None:
                        continue
                    pairs = views(row)
                    for kind, src, dst in pairs:
                        add(m, kind, src, dst)
                    # Same live publication and same unissued draft, opposite immediate CCP replies.
                    # aa vs a proves a repeated accepted request has no incremental effect.
                    # A stale-version rejection cannot have changed the publication.
                    good, bad = (from_q(row[k]) for k in ("a", "bad"))
                    ca = row["cases"]
                    if (
                        any(k == "duplicate" for k, _, _ in pairs)
                        and any(k == "empty" for k, _, _ in pairs)
                        and ca["bad"]["counts"]["rejected"].get("version", 0)
                        > ca["empty"]["counts"]["rejected"].get("version", 0)
                    ):
                        m.reply([(good, True)])
                        add(m, "accepted_remove", [good], [])
                        m.reply([(bad, False)])
                        add(m, "rejected_keep", [good], [good])
                    if not forks and not selected:
                        break
            if forks:
                raise ValueError(f"missing native frames {case}: {list(forks)}")
        if a.macro:
            for i in range(5):
                d, u, proof = fixture(
                    a.data,
                    a.compiler,
                    "response-donor-" + str(i),
                    "chain2",
                    21 + i,
                    "fresh",
                )
                assert all(proof["checks"].values())
                m = memory(a, d, u)
                m.update(json.loads((d / "memory.jsonl").read_text().splitlines()[0]))
                root = from_q(read(d / "tape.json")["requests"][0])
                h = Cell(root.rule, root.refs, True)
                seq = [root] + [
                    Cell(
                        r,
                        tuple(
                            Local(src, pc) if src >= 0 else root.refs[pc]
                            for src, pc in wires
                        ),
                    )
                    for r, _, wires in u[1:]
                ]
                sigs.add(m.enc.cat.int_bake.key(u))
                add(m, "native_fold", seq, [h])
                add(m, "native_activate", [], [h])
    output = a.out / ("composition" if a.macro else "primitive")
    output.mkdir(exist_ok=True, parents=True)
    torch.save(marks_fit(addresses).state_dict(), output / "marks.pt")
    for method in ("flow",) if a.macro else ("editor", "flow"):
        torch.save(
            train_positions(records, method, 243).state_dict(),
            output / (method + ".pt"),
        )
    save(
        output / "fit.json",
        dict(
            labels=counts,
            branch_labels=len(addresses),
            signatures=sorted(sigs),
            sources=TRAIN,
        ),
    )
    print(dict(counts), flush=True)


def weights(a, arm):
    directory = (
        OLD
        if arm in ("P", "O")
        else a.out / ("composition" if arm == "E" else "primitive")
    )
    method = "editor" if arm == "C" else "flow"
    marks, rates = Marks().eval(), Rates().eval()
    for model, key in ((marks, "marks"), (rates, method)):
        model.load_state_dict(torch.load(directory / (key + ".pt"), weights_only=True))
    return marks, {method: rates}


@torch.no_grad()
def run(a):
    case = a.case
    d = folder(a.data, case)
    layout = None
    if case == OPEN:
        d, layout, proof = build(a)
        assert all(proof["checks"].values())
    if case == HELD:
        d, layout, proof = fixture(
            a.data,
            a.compiler,
            case,
            "chain2",
            929,
            "fresh",
            dependencies=[[-1], [0], [0], [1, 2], [1], [3, 4]],
        )
        assert all(proof["checks"].values())
    with TemporaryDirectory() as tmp:
        target = Target(
            read(d / "program.json"),
            snapshot(a.data, d, "reference", "-", None, Path(tmp) / "ref.json")[0],
        )
        initial = target.match(
            snapshot(a.data, d, "reference", "-", 0, Path(tmp) / "ref.json")[0]
        )
        arms = a.arms.split(",")
        for block in range(a.blocks):
            for spec in arms if block % 2 == 0 else reversed(arms):
                arm, steps = spec[0], int(spec[1:])
                tick = perf_counter()
                m = memory(a, d, layout, a.primitive_only)
                if layout:
                    signature = m.enc.cat.int_bake.key(layout)
                    assert (
                        signature
                        not in read(a.out / "composition/fit.json")["signatures"]
                    )
                marks, nets = weights(a, arm)
                if arm in ("U", "P"):
                    m.grouped = False
                policy = ResponsePolicy
                if arm in ("P", "O"):
                    # Frozen mark/rate weights, original state and page dispatcher.
                    m.conditioned = False
                    policy = Ownership
                pol = policy(
                    m,
                    marks,
                    nets,
                    "supervised-empty" if arm == "C" else "empty",
                    steps,
                    536,
                    a.pages,
                )
                if a.fresh_requests:
                    pol.fresh_requests = True
                    m.forced_owned = None
                setup = perf_counter() - tick
                res = execute(a.data, case, study=pol, seconds=a.seconds, series=tmp)
                graph = read(Path(tmp) / (case + "-stream-multi") / "state.json")
                facts = sorted(target.match(graph) - initial)
                res.pop("trace", None)
                wall = setup + res["wall"] + res["runtime_setup_seconds"]
                res.update(
                    arm=arm,
                    primitive_only=a.primitive_only,
                    fresh_requests=a.fresh_requests,
                    steps=steps,
                    case=case,
                    block=block,
                    pages=a.pages,
                    setup=setup,
                    cold_wall=wall,
                    cold_eps=res["signed_ops"] / wall,
                    facts=facts,
                    covered=len(facts),
                    reference=len(target.gold) - len(initial),
                    draft_end=len(getattr(pol, "draft", ())),
                    facts_sha=hashlib.sha256(json.dumps(facts).encode()).hexdigest(),
                )
                accepted = read(Path(tmp) / (case + "-stream-multi") / "issued.json")[
                    "requests"
                ]
                if case == OPEN:
                    roles = read(d / "fixture-roles.json")
                    producer = {q["token"]: q for q in accepted}
                    roots = [q for q in accepted if q["rule"] == roles["Root"]]
                    res["external_writer_bound"] = sum(
                        any(
                            producer.get(p["address"]["token"], {}).get("rule")
                            == roles["Permit"]
                            for p in q["parents"]
                        )
                        for q in roots
                    )
                    res["accepted_sequence"] = [(q["run"], q["rule"]) for q in accepted]
                res["accepted_rules"] = dict(Counter(q["rule"] for q in accepted))
                res["accepted_tape_sha"] = hashlib.sha256(
                    json.dumps(accepted, sort_keys=True).encode()
                ).hexdigest()
                res["leased_pending_steps"] = sum(
                    len(i.unit) - len(i.owners) for i in pol.waiting
                )
                if block == 0 and arm in ("C", "D", "E") and steps in (1, 4):
                    from response_redundancy import audit

                    res["redundancy_offline"] = audit(
                        a.data,
                        Path(tmp) / (case + "-stream-multi"),
                        d / "program.json",
                        res,
                    )
                if layout:
                    res["held_contract"] = [
                        m.wire_contract(layout, j, i)
                        for j, step in enumerate(layout)
                        for i in range(len(step[2]))
                    ]
                    res["held_signature"] = signature
                save(
                    a.out
                    / f"{case}-{spec}{'prim' if a.primitive_only else ''}{'fresh' if a.fresh_requests else ''}-p{a.pages}-b{block}.json",
                    res,
                )
                print(
                    case,
                    spec,
                    block,
                    len(facts),
                    res["termination"],
                    round(wall, 2),
                    flush=True,
                )


def arguments():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=["train", "run"])
    p.add_argument("--data", type=Path, required=True)
    p.add_argument(
        "--actor", type=Path, default=Path("run-recall/higher-scaling/weights/actor.pt")
    )
    p.add_argument("--out", type=Path, default=OUT)
    p.add_argument(
        "--compiler",
        type=Path,
        default=Path("/tmp/cost-audit-build/release/eggfuse-cell-compiler"),
    )
    p.add_argument("--forks", type=Path)
    p.add_argument("--rollout", type=Path)
    p.add_argument("--macro", action="store_true")
    p.add_argument("--primitive-only", action="store_true")
    p.add_argument("--fresh-requests", action="store_true")
    p.add_argument("--case")
    p.add_argument("--arms", default="C1,D1,D2,D4,D8,E4")
    p.add_argument("--blocks", type=int, default=2)
    p.add_argument("--pages", type=int, default=2)
    p.add_argument("--seconds", type=int, default=300)
    return p.parse_args()


if __name__ == "__main__":
    args = arguments()
    torch.set_num_threads(1)
    (train if args.action == "train" else run)(args)
