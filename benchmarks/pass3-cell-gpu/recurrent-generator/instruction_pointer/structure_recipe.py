"""Mine typed wiring programs offline and audit perfect-partner opportunities."""

import argparse
import heapq
import json
import subprocess
from bisect import bisect_right
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory

from entry_closure import Tape, named
from int_parameters import link_layouts
from protocol_experiment import dump
from receipt_bake import save
from receipt_takeover import replay_many
from recursive_train import binary, folder, read
from ripsat_layout import signatures


def root_instances(tape, catalog):
    tails = defaultdict(list)
    for _, unit in link_layouts(tape.program, catalog):
        for seq in tape.occasions(unit):
            tails[seq[-1]].append(tuple(seq))
    for q in tape.tape:
        refs = tuple(map(named, q["parents"]))
        if len(refs) != 2 or refs[0][0] == refs[1][0]:
            continue
        groups = [max(tails.get(ref[0], ((),)), key=lambda s: (len(s), s)) for ref in refs]
        if not any(groups) or set(groups[0]).intersection(groups[1]):
            continue
        if any(refs[1 - i][0] in seq for i, seq in enumerate(groups)):
            continue
        yield q, refs, groups


def fanout(plan, step):
    """An additional same-stage branch sharing at least one producer."""
    _, stage, wires = plan[step]
    sources = {wire[0] for wire in wires}
    return any(
        previous == stage and sources.intersection(w[0] for w in other) for _, previous, other in plan[:step]
    )


def shape_of(plan):
    parallel = any(fanout(plan, i) for i in range(1, len(plan)))
    return "fanout" if parallel else "chain"


class Evidence:
    def __init__(self, data, case, directory=None):
        d = directory or folder(data, case)
        self.t = Tape(d, binary(data))
        self.sigs = signatures(self.t.program)
        rep = json.loads(
            subprocess.check_output(
                [binary(data), "replay", d / "program.json", d / "tape.json", "audit", "--ept-origins"]
            )
        )
        cap = read(d / "capture.json")
        if any(rep[k] != cap[k] for k in ("state_sha", "schedule", "writes", "rhs", "resumes", "events")):
            raise ValueError("native teacher replay diverged")
        self.ops = Counter()
        for token, n in rep["ept"]["origins"]:
            self.ops[token] += n
        self.uses = defaultdict(list)
        for q in self.t.tape:
            for token in {named(p)[0] for p in q["parents"]}:
                self.uses[token].append((q["run"], q["token"]))

        self.next_group = lru_cache(maxsize=8192)(self._next_group)

    def _next_group(self, after, rules):
        schedule = self.t.schedule
        first = min((schedule[r] for r in rules), key=len)
        for run in first[bisect_right(first, after) :]:
            if all((i := bisect_right(schedule[r], run)) and schedule[r][i - 1] == run for r in rules):
                return run

    def mine(self, root, refs, groups, limit=8, *, extra_ref=None):
        t = self.t
        owners = {
            tok: (-i - 1, back) for i, seq in enumerate(groups) for back, tok in enumerate(reversed(seq))
        }
        entry = {ref: (-i - 1, -1, -1) for i, ref in enumerate(refs)}
        if extra_ref is not None:
            # Offline sensitivity only. Charge one additional independent binding.
            entry[extra_ref] = (-3, -1, -1)
        root_time = root["run"]
        times = [root_time]
        program = [(root["rule"], 0, tuple(entry[ref] for ref in refs))]
        tokens = [root["token"]]
        owners[tokens[0]] = (0, 0)
        queue, queued = [], set()

        def add(tok):
            for run, child in self.uses[tok]:
                if child not in queued and root_time <= run <= root_time + 32 and child > tokens[0]:
                    heapq.heappush(queue, (run, child))
                    queued.add(child)

        for tok in set(owners) | {p[0] for p in refs}:
            add(tok)
        while queue and len(program) < limit:
            run, tok = heapq.heappop(queue)
            q = t.q[tok]
            wires = []
            for parent in q["parents"]:
                ref = named(parent)
                if ref in entry:
                    wires.append(entry[ref])
                    continue
                src, op, v = ref
                if src not in owners or t.snap.version(src, op, t.q[src]["run"] + 1) != v:
                    break
                owner, back = owners[src]
                if owner < 0 and t.snap.version(src, op, root_time) != v:
                    break
                wires.append((owner, back, op))
            else:
                sources = {w[0] for w in wires}
                if not sources or (max(sources) < 0 and (len(sources) < 2 or extra_ref is not None)):
                    continue
                if any(w[0] >= 0 and t.q[tokens[w[0]]]["run"] >= run for w in wires):
                    continue
                if run != times[-1]:
                    if self.next_group(times[-1], (q["rule"],)) != run:
                        continue
                    times.append(run)
                owners[tok] = (len(tokens), 0)
                tokens.append(tok)
                program.append((q["rule"], len(times) - 1, tuple(wires)))
                add(tok)
        return tuple(program), tokens

    def match(self, program, root, refs, groups):
        t = self.t
        run = root["run"]
        tokens = [root["token"]]
        for step in range(1, len(program)):
            rule, stage, wires = program[step]
            if stage != program[step - 1][1]:
                rules = tuple(sorted({r for r, g, _ in program if g == stage}))
                run = self.next_group(run, rules)
            if run is None:
                break
            parents = []
            for owner, back, pc in wires:
                if owner < 0 and back < 0:
                    ref = refs[-owner - 1]
                else:
                    if owner < 0:
                        seq = groups[-owner - 1]
                        if back >= len(seq):
                            return tokens
                        tok = seq[-back - 1]
                    else:
                        tok = tokens[owner]
                    v = t.snap.version(tok, pc, t.q[tok]["run"] + 1)
                    if v is None or (owner < 0 and t.snap.version(tok, pc, root["run"]) != v):
                        return tokens
                    ref = tok, pc, v
                if t.snap.version(*ref[:2], run) != ref[2]:
                    return tokens
                parents.append(ref)
            child = t.index.get((run, rule, tuple(parents)))
            if child is None or child in tokens or (run == t.q[tokens[-1]]["run"] and child <= tokens[-1]):
                break
            tokens.append(child)
        return tokens


def validate_program(plan):
    entry = ((-1, -1, -1), (-2, -1, -1))
    if len(plan) < 2 or plan[0][1] != 0 or tuple(map(tuple, plan[0][2])) != entry:
        raise ValueError("recipe requires two independently named inputs")
    for i, (_, stage, wires) in enumerate(plan):
        if i and stage not in (plan[i - 1][1], plan[i - 1][1] + 1):
            raise ValueError("nonconsecutive publication group")
        for owner, back, op in wires:
            if owner < 0:
                if owner not in (-1, -2) or not ((back, op) == (-1, -1) or (back >= 0 and op >= 0)):
                    raise ValueError("invalid structural interface read")
            elif owner >= i or plan[owner][1] >= stage or back != 0 or op < 0:
                raise ValueError("local port read before publication")


def link(program, book):
    ids = defaultdict(list)
    for r, sig in enumerate(signatures(program)):
        ids[sig].append(r)
    menu = defaultdict(list)
    for i, plan in enumerate(book["plans"]):
        validate_program(plan)
        if all(len(ids[r]) == 1 for r, _, _ in plan):
            steps = tuple((ids[r][0], g, tuple(map(tuple, w))) for r, g, w in plan)
            menu[steps[0][0]].append((i, steps))
    return menu


def compile_book(data, store):
    e = Evidence(data, "sum")
    ranks = Counter()
    for root, refs, groups in root_instances(e.t, read(store / "catalog.json")):
        plan, ts = e.mine(root, refs, groups)
        if len(plan) > 1:
            ranks[plan] += sum(e.ops[t] for t in ts[1:])
    chosen = sorted((p for p in ranks if ranks[p]), key=lambda p: (-ranks[p], p))[:64]
    book = {
        "plans": [[(e.sigs[r], g, w) for r, g, w in p] for p in chosen],
        "training_program": "sum",
        "observed_distinct": len(ranks),
    }
    dump(store / "structure-book.json", book)


def native_unit(plan, tokens, tape):
    external = {}
    unit = []
    for (rule, stage, inputs), token in zip(plan, tokens, strict=True):
        wires = []
        for (source, _, op), ref in zip(inputs, tape.q[token]["parents"], strict=True):
            if source < 0:
                wires.append((-1, external.setdefault(named(ref), len(external))))
            else:
                wires.append((source, op))
        unit.append((rule, stage, wires))
    return unit


def audit(data, store, case):
    e = Evidence(data, case)
    menu = link(e.t.program, read(store / "structure-book.json"))
    totals, covered, singles = Counter(), set(), set()
    witnesses = {}
    local_discovery = Counter()
    distribution = Counter()
    for root, refs, groups in root_instances(e.t, read(store / "catalog.json")):
        kind = "Compose" if all(groups) else "Extend"
        totals["correct_pairs_" + kind] += 1
        singles.add(root["token"])
        # Diagnostic only: repeat the same restricted discovery on this tape.
        # Never export its wiring to the independent policy.
        local_plan, local_tokens = e.mine(root, refs, groups)
        local_ops = sum(e.ops[t] for t in local_tokens[1:])
        local_discovery["roots_with_any_extra_" + kind] += int(len(local_plan) > 1)
        local_discovery["roots_with_positive_extra_" + kind] += int(local_ops > 0)
        local_discovery["roots_with_fanout_" + kind] += int(shape_of(local_plan) == "fanout")
        local_discovery["gross_extra_ops_" + kind] += local_ops
        best_score = 0
        for pid, plan in menu.get(root["rule"], ()):
            ts = e.match(plan, root, refs, groups)
            score = sum(e.ops[t] for t in ts[1:])
            covered.update(ts[1:])
            best_score = max(best_score, score)
            if len(ts) == len(plan):
                label = kind, shape_of(plan)
                if label not in witnesses or score > witnesses[label][0]:
                    witnesses[label] = (score, pid, plan, ts)
        distribution[kind, best_score] += 1
        totals["root_ops_" + kind] += e.ops[root["token"]]
        totals["best_extra_ops_sum_" + kind] += best_score
        totals["multi_effect_pairs_" + kind] += int(best_score > 0)
    checks = []
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "units.json"
        for label, (score, pid, plan, ts) in witnesses.items():
            save(path, [native_unit(plan, ts, e.t)])
            d = folder(data, case)
            rep = replay_many(d, binary(data), path, [(0, ts)], e.t.tape, read(d / "capture.json"))
            checks.append(
                {"kind": label, "pid": pid, "tokens": ts, "extra_ops": score, "checks": rep["checks"]}
            )
    dump(
        store / f"{case}-oracle.json",
        {
            "totals": totals,
            "distinct_root_ops": sum(e.ops[t] for t in singles),
            "local_discovery": local_discovery,
            "union_extra_ops": sum(e.ops[t] for t in covered - singles),
            "distinct_suffix_ops": sum(e.ops[t] for t in covered),
            "best_extra_ops_histogram": [[k, n, c] for (k, n), c in sorted(distribution.items())],
            "native_witnesses": checks,
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("data", type=Path)
    p.add_argument("store", type=Path)
    p.add_argument("tasks", nargs="+")
    a = p.parse_args()
    for task in a.tasks:
        if task == "compile":
            compile_book(a.data, a.store)
        else:
            audit(a.data, a.store, task)
