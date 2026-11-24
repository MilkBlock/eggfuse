"""Lower explicit Bake choices into unchanged CCP PROVE batches; account every lowered request."""

import argparse, hashlib
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter
import numpy as np
import torch
from generation_higher import BAKE, Layouts, Recognizer, fit
from replacement_stream import ReplacementStream
from ripsat_replay import unpack
from stream_guard import Study
from recursive_coverage import Target, snapshot
from recursive_train import folder, read
from transaction_native import execute
from protocol_experiment import dump


def split(u):
    pair = tuple(r for r, _, _ in u[:2])
    if (
        int.from_bytes(hashlib.sha256(str(pair).encode()).digest()[:2], "little") % 4
        == 0
    ):
        return "pair"
    if int.from_bytes(hashlib.sha256(repr(u).encode()).digest()[:2], "little") % 4 == 0:
        return "layout"
    return "fit"


def send(txn, rule, rows):
    n, k, _ = rows.shape
    refs = np.full((n, k, 4), -1, np.int64)
    refs[:, :, :3] = rows
    op = np.zeros((n, 5), np.int64)
    op[:, 2] = rule
    op[:, 3] = -1
    op[:, 4] = np.arange(1, n + 1) * k
    return txn.collect(txn.enqueue(op, refs.reshape(-1, 4), 0)).rows.numpy()


class LearnedReplacementStream(ReplacementStream):
    def score_children(self, h, depth, paths, parents):
        score, z = super().score_children(h, depth, paths, parents)
        if depth + 1 < len(self.roles):
            model = self.study.prefix
            score = torch.maximum(
                score, model(model.evidence(self, depth, paths, z, look=False))
            )
        return score, z


class Policy:
    def __init__(self, case, root, out, arm, blind, learned_prefix):
        self.arm = arm
        self.cat = Layouts(read(folder(root, case) / "program.json"))
        units = unpack(read(BAKE / "catalog.json"))
        self.groups = [split(units[i]) for i in self.cat.original]
        self.net = Recognizer(self.cat.codes.shape[1]).eval()
        self.net.load_state_dict(torch.load(out / "higher.pt", weights_only=True))
        self.study = Study(bits=8, symmetric=True, delta_buckets=True)
        self.stream = ReplacementStream
        if learned_prefix:
            from train_reachability import Prefix

            self.study.prefix = Prefix().eval()
            self.study.prefix.load_state_dict(
                torch.load(out / "prefix.pt", weights_only=True)
            )
            self.stream = LearnedReplacementStream
        self.waiting = []
        self.expected = set()
        self.internal = set()
        self.completed = set()
        self.count = Counter()
        self.menu = {
            rid: [
                uid
                for uid in lst
                if all(i == g for i, (_, g, w) in enumerate(self.cat.units[uid]))
                and (
                    not blind
                    or self.groups[uid] == blind
                    or (
                        blind == "unseen-long"
                        and self.groups[uid] != "fit"
                        and len(self.cat.units[uid]) > 2
                    )
                )
            ]
            for rid, lst in self.cat.by.items()
        }

    def advance(self, rd, pub, txn, rules):
        accepted = set(map(int, pub[3][:, 0]))
        assert self.expected <= accepted
        self.completed.update(self.expected)
        self.expected.clear()
        done = defaultdict(set)
        pending = []
        batches = defaultdict(list)
        for uid, boundary, history, versions in self.waiting:
            u = self.cat.units[uid]
            step = len(history)
            if step == len(u):
                self.count["completed_" + self.groups[uid]] += 1
                self.count[f"completed_size_{len(u)}"] += 1
                continue
            # Latch a returned port only at its first committed publication.
            ok = True
            for _, _, w in u[step:]:
                for owner, op in w:
                    if owner == step - 1 and (owner, op) not in versions:
                        row = rd.store.visible.get((history[owner], op))
                        if row is None:
                            ok = False
                        else:
                            versions[owner, op] = row["version"]
            if not ok:
                self.count["missing_return"] += 1
                continue
            rid, _, w = u[step]
            if rid not in rules:
                pending.append((uid, boundary, history, versions))
                continue
            parents = tuple(
                boundary[op] if owner < 0 else (history[owner], op, versions[owner, op])
                for owner, op in w
            )
            batches[rid, len(w)].append((parents, (uid, boundary, history, versions)))
        for (rid, k), work in batches.items():
            for i in range(0, len(work), txn.capacity):
                group = work[i : i + txn.capacity]
                rows = np.asarray([x[0] for x in group], dtype=np.int64).reshape(
                    len(group), k, 3
                )
                for resp, (parents, (uid, boundary, history, versions)) in zip(
                    send(txn, rid, rows), group, strict=True
                ):
                    self.count["lowered_steps"] += 1
                    if resp[1] != 0:
                        self.count["rejected_step"] += 1
                        continue
                    token = int(resp[0])
                    done[rid].add(parents)
                    self.expected.add(token)
                    self.internal.add(token)
                    pending.append((uid, boundary, history + (token,), versions))
        self.waiting = pending
        return done

    def run_snapshot(self, frame, pub, rd, model, txn, stats, deadline):
        rules = dict(frame["rules"])
        done = self.advance(rd, pub, txn, rules)
        for rid, wm in rules.items():
            s = self.stream(rd, model, rid, wm, stats, study=self.study)
            covered = s.covered_paths(done[rid]) if self.arm in ("C", "D") else set()
            s.exclusions = covered if self.arm == "D" else set()
            menu = self.menu.get(rid, ()) if self.arm != "A" else ()
            for paths in s.path_batches("stream", 0, deadline):
                if covered and (self.arm == "C" or paths.shape[1] == 0):
                    paths = s.remove_scored(paths, covered, self.count)
                if not len(paths):
                    continue
                if menu:
                    tick = perf_counter()
                    ctx = (
                        torch.stack(
                            [s.tables[j][1][paths[:, j]] for j in range(paths.shape[1])]
                        ).mean(0)
                        if paths.shape[1]
                        else torch.zeros(len(paths), 24)
                    )
                    x = torch.cat((ctx, rd.meta(rid).expand(len(paths), -1)), 1)
                    score, idx = self.net(
                        x[:, None, :], self.cat.codes[menu][None, :, :]
                    ).max(1)
                    choices = torch.where(
                        score > 0, torch.tensor(menu)[idx], -1
                    ).numpy()
                    self.count["recognized"] += int((choices >= 0).sum())
                    self.count["recognition_scores"] += len(paths) * len(menu)
                    self.count["recognition_seconds"] += perf_counter() - tick
                else:
                    choices = np.full(len(paths), -1)
                refs = np.empty((len(paths), len(s.order), 3), np.int64)
                for j, role in enumerate(s.order):
                    refs[:, role] = s.port_refs(j)[paths[:, j]].numpy()
                for start in range(0, len(paths), txn.capacity):
                    subset = refs[start : start + txn.capacity]
                    uids = choices[start : start + len(subset)]
                    resp = send(txn, rid, subset)
                    for i in np.flatnonzero((resp[:, 1] == 0) & (uids >= 0)):
                        token = int(resp[i, 0])
                        self.expected.add(token)
                        self.waiting.append(
                            (
                                int(uids[i]),
                                tuple(map(tuple, subset[i].tolist())),
                                (token,),
                                {},
                            )
                        )


def run(root, out, case, arm, rep, blind=None, learned_prefix=False):
    policy = Policy(case, root, out, arm, blind, learned_prefix)
    tag = (blind or "") + ("-learned" if learned_prefix else "")
    series = "replacement/" + arm + tag
    m = execute(root, case, study=policy, series=series, seconds=200)
    assert m["termination"] == "schedule_end"
    work = root / series / (case + "-stream-multi")
    d = folder(root, case)
    p = work / "align.json"
    tape = read(work / "issued.json")
    assert policy.internal <= {q["token"] for q in tape["requests"]}
    t = Target(
        read(d / "program.json"), snapshot(root, d, "reference", "-", None, p)[0]
    )
    seed = t.match(snapshot(root, d, "reference", "-", 0, p)[0])
    m.pop("trace")
    m.pop("guard_failures")
    m.update(
        arm=arm,
        blind=blind,
        learned_prefix=learned_prefix,
        repeat=rep,
        derived=len(t.match(read(work / "state.json")) - seed),
        den=len(t.gold) - len(seed),
        replacement=dict(policy.count),
        internal_committed=len(policy.internal),
    )
    dump(out / f"higher-{case}-{arm}{tag}-{rep}.json", m)
    print(
        case,
        arm,
        blind,
        m["derived"],
        m["paid"],
        m["work"].get("visits"),
        m["replacement"],
        flush=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    p.add_argument("--donor", type=Path)
    p.add_argument("--cases", nargs="*", default=[])
    p.add_argument("--arms", nargs="+", default=list("ABCD"))
    p.add_argument("--learned-prefix", action="store_true")
    p.add_argument("--blind", choices=("layout", "pair", "unseen-long"))
    p.add_argument("--reps", type=int, default=1)
    a = p.parse_args()
    torch.set_num_threads(1)
    if a.donor:
        units = unpack(read(BAKE / "catalog.json"))
        fit(a.root, a.out, a.donor, lambda i: split(units[i]) == "fit")
    for c in a.cases:
        for rep in range(a.reps):
            for arm in a.arms if rep % 2 == 0 else a.arms[::-1]:
                run(a.root, a.out, c, arm, rep, a.blind, a.learned_prefix)
