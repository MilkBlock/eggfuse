"""Build a frozen transferable menu from actual, versioned training edges; no tape access when linking."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from entry_closure import Tape, named
from int_parameters import StructuralBake, link_layouts
from receipt_takeover import replay_many
from recursive_train import binary, folder, read
from ripsat_layout import signatures
from scaling_bake import save

DONORS = ("sum", "dot", "grammar-benefit-fork-17118")


def mine(tape):
    consumers = defaultdict(list)
    for q in tape.tape:
        for owner in {p["address"]["token"] for p in q["parents"]}:
            consumers[owner].append(q["token"])
    counts, sample = Counter(), {}
    for root in tape.tape:
        rid = root["rule"]
        if not root["parents"]:
            continue
        unit = tape.rules.root(rid)
        ext = {named(p): (-1, i) for i, p in enumerate(root["parents"])}
        tokens = (root["token"],)
        producers = {tokens[0]: 0}
        frontier = set(consumers[tokens[0]])
        while frontier:
            following = None
            for token in sorted(frontier, key=lambda k: (tape.q[k]["run"], k)):
                q = tape.q[token]
                if q["run"] <= tape.q[tokens[-1]]["run"]:
                    continue
                wires = []
                for p in q["parents"]:
                    owner, op, ver = named(p)
                    if owner in producers and str(op) in tape.rules.rules[tape.q[owner]["rule"]]["outputs"]:
                        wires.append((producers[owner], op))
                    elif (owner, op, ver) in ext:
                        wires.append(ext[owner, op, ver])
                    else:
                        break
                if len(wires) != len(q["parents"]):
                    continue
                step = (q["rule"], len(unit), tuple(wires))
                if tape.extend(tokens, step) == (*tokens, token):
                    following = (token, step)
                    break
            if following is None:
                break
            token, step = following
            frontier.remove(token)
            frontier.update(consumers[token])
            producers[token] = len(unit)
            unit += (step,)
            tokens += (token,)
            counts[unit] += 1
            sample.setdefault(unit, tokens)
    return counts, sample


def build(root, out):
    manifests = []
    audit = {}
    for donor in DONORS:
        tick = perf_counter()
        d = folder(root, donor)
        tape = Tape(d, binary(root))
        counts, sample = mine(tape)
        # One action per primitive root in the frozen decoder. Require reuse in training.
        ranked = sorted((u for u in counts if counts[u] >= 2), key=lambda u: (-len(u), -counts[u], u))
        chosen = {}
        for u in ranked:
            chosen.setdefault(u[0][0], u)
        layouts = list(chosen.values())
        passed, rejected = [], []
        ref = read(d / "capture.json")
        with TemporaryDirectory(dir=out) as tmp:
            path = Path(tmp) / "units.json"
            save(path, layouts)
            groups = []
            for i, u in enumerate(layouts):
                ts = sample[u]
                for occupied, jobs in groups:
                    if not occupied.intersection(ts):
                        break
                else:
                    occupied, jobs = set(), []
                    groups.append((occupied, jobs))
                occupied.update(ts)
                jobs.append((i, ts))

            def certify(jobs):
                try:
                    result = replay_many(d, binary(root), path, jobs, tape.tape, ref)
                except ValueError as err:
                    if len(jobs) == 1:
                        rejected.append(dict(index=jobs[0][0], reason=str(err)[:400]))
                        return
                    mid = len(jobs) // 2
                    certify(jobs[:mid])
                    certify(jobs[mid:])
                    return
                passed.extend(dict(index=i, witness=ts, checks=result["checks"]) for i, ts in jobs)

            for _, jobs in groups:
                certify(jobs)
        valid = [layouts[p["index"]] for p in sorted(passed, key=lambda p: p["index"])]
        manifests.append(
            dict(
                donor=donor,
                signatures=signatures(tape.program),
                layouts=valid,
                frequencies=[counts[u] for u in valid],
                **StructuralBake(tape.program).manifest(valid),
            )
        )
        audit[donor] = dict(
            seconds=perf_counter() - tick,
            roots=len(tape.tape),
            found_sizes=dict(Counter(map(len, counts))),
            frequencies=[counts[u] for u in layouts],
            proposed=layouts,
            passed=passed,
            rejected=rejected,
        )
        save(out / "donors.json", audit)
        print(donor, len(counts), len(valid), flush=True)
    save(out / "menu.json", manifests)


def linked(program, manifests):
    choices = {}
    for donor in manifests:
        for i, unit in link_layouts(program, donor):
            r = unit[0][0]
            rank = len(unit), donor["frequencies"][i], donor["structural_keys"][i]
            if r not in choices or choices[r][0] < rank:
                choices[r] = rank, unit
    return {r: u for r, (_, u) in choices.items()}


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    build(a.root, a.out)
