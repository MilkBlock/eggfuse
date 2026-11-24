"""Fit the unchanged B terminal with same-root, verified cost comparisons."""
from argparse import ArgumentParser
from collections import Counter, defaultdict
from itertools import combinations
import json
from pathlib import Path
import numpy as np
import torch
from torch.nn import functional as F

from entry_model import Family, scores
from entry_wiring import use_wiring
from event_addresses import Directory
from event_templates import BranchNet
from receipt_bake import read, save
from recursive_agent import Reader


def contexts(data, folder, out, training):
    program = read(folder / "program.json")
    labels = read(out / (folder.name + "-cost.json"))["roots"]
    rd = Reader(program, data, rename_seed=4321 if training else 581)
    family = Family(rd, program, read(out / "catalog.json"))
    old = family.codes.copy()
    use_wiring(family, torch.load(out / "graph.pt", weights_only=True))
    mem = Directory(rd, Counter())
    packets = defaultdict(list)
    for q in read(folder / "tape.json")["requests"]:
        if str(q["token"]) in labels:
            packets[q["run"]].append(q)
    rows = []
    for frame in map(json.loads, (folder / "memory.jsonl").open()):
        rd.advance(frame)
        rules = dict(frame["rules"])
        for q in packets[frame["run"]]:
            r = q["rule"]
            ids = [-1, *family.menu[r]]
            known = {0: (0, 0)}  # Primitive takes no additional action after root acceptance.
            for uid, cost in labels[str(q["token"])].items():
                if not training or int(uid) not in family.held:
                    known[ids.index(int(uid))] = tuple(cost)
            if len(known) < 2:
                continue
            events = []
            for j, p in enumerate(q["parents"]):
                if p["version"] >= rules[r]:
                    addr = p["address"]
                    bank = mem.bank(mem.roles[r][j])
                    k = bank.positions[rd.store.alias(addr["token"]), addr["op"]]
                    events.append((j, bank.vec[k]))
            if not q["parents"]:
                events.append((-1, np.zeros(16, np.float32)))
            for j, x in events:
                rows.append((torch.from_numpy(x.copy()), (r, j), known, ids))
    return rows, {arm: {k: torch.from_numpy(v) for k, v in d.items()}
                  for arm, d in [("rank", old), ("wired", family.codes)]}, family.held


def comparisons(known):
    for a, b in combinations(known, 2):
        if known[a] == known[b]:
            continue
        hi, lo = (a, b) if known[a] > known[b] else (b, a)
        yield hi, lo


def train(rows, codes):
    torch.manual_seed(4321)
    model = BranchNet()
    model.load_state_dict(torch.load("run-recall/cell-events/template.pt", weights_only=True))
    better, worse = [], []
    for x, key, known, _ in rows:
        for hi, lo in comparisons(known):
            better.append(torch.cat((x, codes[key][hi])))
            worse.append(torch.cat((x, codes[key][lo])))
    hi, lo = torch.stack(better), torch.stack(worse)
    opt = torch.optim.AdamW(model.parameters(), lr=0.001)
    for _ in range(16):
        for ix in torch.randperm(len(hi)).split(128):
            loss = F.softplus(model(lo[ix]) - model(hi[ix])).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
    return model.eval(), len(hi)


@torch.no_grad()
def evaluate(model, rows, codes, held):
    count = Counter()
    for x, key, known, ids in rows:
        logits = scores(model, x[None], codes[key])[0]
        k = logits.argmax().item()
        count["contexts"] += 1
        if k in known:
            count["chosen_verified"] += 1
            count["chosen_positive_net"] += int(known[k] > (0, 0))
            count["known_optimum_chosen"] += int(known[k] == max(known.values()))
        possible = {i for i in known if ids[i] in held and known[i] > (0, 0)}
        if possible:
            count["held_gain_contexts"] += 1
            count["selected_held_gain"] += int(k in possible)
        for hi, lo in comparisons(known):
            count["verified_pairs"] += 1
            count["strict_pair_wins"] += int(logits[hi] > logits[lo])
            count["score_ties"] += int(logits[hi] == logits[lo])
    return count


if __name__ == "__main__":
    p = ArgumentParser()
    for k in ("data", "root", "out"):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    rows, codes, held = contexts(a.data, a.root / "sum", a.out, True)
    for arm in ("rank", "wired"):
        model, pairs = train(rows, codes[arm])
        torch.save(model.state_dict(), a.out / (arm + ".pt"))
        print(arm, len(rows), pairs, flush=True)
    save(a.out / "fit.json", dict(program="sum", root_events=len(rows),
                                  strict_comparisons=pairs, held_ids=sorted(held),
                                  epochs=16, seed=4321))
