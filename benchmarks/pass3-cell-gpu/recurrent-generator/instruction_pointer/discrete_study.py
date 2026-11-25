"""Train matched editors on native forks and evaluate frozen snapshots without oracle marks at inference."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
from torch.nn import functional as F

from discrete_cells import Cell, Local, Marks, from_q, setup
from discrete_draft import plan, script
from discrete_editor import sampler, train_positions
from latent_cell_flow import TEST, TRAIN, VALID
from latent_composition import fixture
from recursive_train import folder, read


def views(row):
    a, b, bad = (from_q(row[k]) for k in ("a", "b", "bad"))
    cases = row["cases"]

    def published(k):
        return {(v["table"], tuple(v["hashes"])) for _, v in cases[k]["frame"]["updates"]}

    pairs = []
    if (
        cases["aa"]["frame"] == cases["a"]["frame"]
        and cases["aa"]["counts"]["duplicates"] == cases["a"]["counts"]["duplicates"] + 1
    ):
        pairs += [("duplicate", [a, a], [a]), ("keep", [a], [a])]
    # The reference path confirms a named output. A native after-frame must contain
    # a newly published payload relative to the other treatment, not just an accepted signature.
    if published("a") - published("empty"):
        pairs += [("repair", [bad], [a]), ("empty", [], [a])]
    if (
        published("ab") - published("a")
        and cases["ab"]["counts"]["accepted"] == cases["a"]["counts"]["accepted"] + 1
    ):
        pairs += [("partial", [a], [a, b]), ("empty_multi", [], [a, b]), ("keep_multi", [a, b], [a, b])]
    return pairs


def record(m, src, dst):
    src, dst = plan(src), plan(dst)
    return m.state, m.event, src, dst, {x.cell: m.embed(x.cell) for x in (*src, *dst)}, script(src, dst)


def marks_fit(rows):
    x = torch.stack([q for q, _, _ in rows])
    y = torch.tensor([a for _, a, _ in rows]).float()
    weights = torch.tensor([w for _, _, w in rows])
    torch.manual_seed(8201)
    net = Marks()
    opt = torch.optim.AdamW(net.parameters(), lr=0.002)
    for _ in range(36):
        for ids in torch.randperm(len(y)).split(512):
            p = net.choice(x[ids]).flatten()
            loss = (weights[ids] * F.binary_cross_entropy_with_logits(p, y[ids], reduction="none")).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
    return net.eval()


def dataset(args, name, visit):
    d = folder(args.root, name.removesuffix("-roll"))
    path = args.rollout / "sum-native-memory.jsonl" if name == "sum-roll" else d / "memory.jsonl"
    rs = {r["run"]: r for r in map(json.loads, (args.forks / (name + ".jsonl")).read_text().splitlines())}
    m = setup(args.root, d, args.actor)
    with path.open() as f:
        for frame in map(json.loads, f):
            m.update(frame)
            if frame["run"] in rs:
                visit(m, views(rs[frame["run"]]), frame["run"])


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2) + "\n")


def train(a):
    verified = read(a.out / "suffix-audit.json")
    assert all(verified[k]["verified_repeats"] for k in TRAIN)
    rng = np.random.default_rng(42)
    addresses = []
    records = []
    counts = Counter()
    net = Marks()

    def visit(m, pairs, run):
        for kind, src, dst in pairs:
            records.append(record(m, src, dst))
            counts[kind] += 1
            # Integrate the oracle mark NLL over uniform bridge time. Each
            # prefix length is equally probable; only outstanding marked jumps train routing.
            path = records[-1][-1]
            for k, (current, i, kind, cell) in enumerate(path):
                if cell is not None and (cell.rule, cell.higher) in m.ids_index:
                    net.draw(
                        m,
                        rng,
                        Counter(),
                        current[i].cell if kind == 2 else None,
                        cell,
                        addresses,
                        prefix=current[:i],
                        weight=(len(path) - k) / (len(path) + 1),
                    )

    signatures = set()
    with torch.no_grad():
        for n in TRAIN:
            dataset(a, n, visit)
        donors = [("chain2", "fresh", v) for v in (5, 7, 11, 17)] + [
            ("chain2", "guard_true", 41),
            ("chain2", "guard_false", 42),
            ("chain2", "duplicate", 19),
        ]
        for i, (shape, scene, value) in enumerate([] if a.primitives_only else donors):
            d, u, audit = fixture(a.root, a.compiler, "edit-donor-" + str(i), shape, value, scene)
            m = setup(a.root, d, a.actor, u)
            f = json.loads((d / "memory.jsonl").read_text().splitlines()[0])
            m.update(f)
            tape = read(d / "tape.json")["requests"]
            q = from_q(tape[0])
            h = Cell(q.rule, q.refs, True)
            signatures.add(m.enc.cat.int_bake.key(u))
            if scene in ("fresh", "guard_true"):
                assert all(audit["checks"].values())
                seq = [q] + [
                    Cell(r, tuple(Local(owner, pc) if owner >= 0 else q.refs[pc] for owner, pc in wires))
                    for r, _, wires in u[1:]
                ]
                visit(m, [("fold", seq, [h]), ("activate", [], [h])], 0)
            elif scene == "guard_false":
                assert not audit.get("complete_teacher_instance") and len(tape) == 1
                from discrete_donor_check import certify

                save(a.out / "guard-certificate.json", certify(a.root, d, u, m, a.out))
                m.pub = type(m.pub)(m.enc)
                m.update(f)
                visit(m, [("failed_macro", [h], [q])], 0)
            # Existing output facts need not imply that all publications and proofs are redundant.
            # Leave the duplicate donor unlabeled unless a whole-suffix equivalence check is available.
    marks = marks_fit(addresses)
    torch.save(marks.state_dict(), a.out / "marks.pt")
    for method in ("editor", "mask", "flow"):
        net = train_positions(records, method, 243)
        torch.save(net.state_dict(), a.out / (method + ".pt"))
    save(
        a.out / "fit.json",
        dict(
            counts=counts,
            branch_labels=len(addresses),
            training=TRAIN,
            signatures=sorted(signatures),
            seed=243,
        ),
    )
    print(counts, len(addresses), flush=True)


def load(a):
    from discrete_editor import Rates

    marks = Marks().eval()
    marks.load_state_dict(torch.load(a.out / "marks.pt", weights_only=True))
    nets = {}
    for k in ("editor", "mask", "flow"):
        nets[k] = Rates().eval()
        nets[k].load_state_dict(torch.load(a.out / (k + ".pt"), weights_only=True))
    return marks, nets


@torch.no_grad()
def frozen(a):
    marks, nets = load(a)
    summary = {}
    for name in (VALID, *TEST):
        stats = defaultdict(Counter)

        def visit(m, pairs, run):
            for index, (task, src, dst) in enumerate(pairs):
                for method, steps in [
                    ("editor", 1),
                    *[(k, s) for k in ("mask", "flow") for s in (1, 2, 4, 8)],
                ]:
                    c = stats[method + str(steps) + "/" + task]
                    rng = np.random.default_rng(12345 + run * 17 + index)
                    new = [
                        item.cell
                        for item in sampler(nets[method], marks, m, plan(src), method, steps, rng, c)
                    ]
                    c["n"] += 1
                    c["exact"] += int(new == dst)
                    c["target_tokens"] += len(dst)
                    c["emitted"] += len(new)
                    c["recovered"] += sum((Counter(new) & Counter(dst)).values())
                    c["known_target_missing"] += sum((Counter(dst) - Counter(new)).values())
                    c["kept_excess_exact_copies"] += sum(
                        max(0, n - dst.count(v)) for v, n in Counter(new).items() if v in dst
                    )

        dataset(a, name, visit)
        summary[name] = dict(stats)
        save(a.out / "frozen.json", summary)


def arguments():
    p = argparse.ArgumentParser()
    for k in ("action", "root", "forks", "rollout", "actor", "compiler", "out"):
        p.add_argument(k, type=str if k == "action" else Path)
    p.add_argument(
        "--primitives-only", action="store_true", help="omit all macro demonstrations from fitting"
    )
    return p.parse_args()


if __name__ == "__main__":
    args = arguments()
    torch.set_num_threads(1)
    if args.action == "train":
        train(args)
    elif args.action == "frozen":
        frozen(args)
    else:
        raise ValueError(args.action)
