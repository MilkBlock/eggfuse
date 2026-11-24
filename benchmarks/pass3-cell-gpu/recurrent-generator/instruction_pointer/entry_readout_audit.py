"""Compare same-family readout collisions and teacher-root preferences."""
from argparse import ArgumentParser
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path
import torch

from entry_model import scores
from event_templates import BranchNet
from receipt_bake import save
from train_entry_ranking import contexts, evaluate


@torch.no_grad()
def audit(data, root, out, name):
    rows, codes, held = contexts(data, root / name, out, False)
    models = {}
    for arm in codes:
        model = BranchNet().eval()
        model.load_state_dict(torch.load(out / (arm + ".pt"), weights_only=True))
        models[arm] = model
    families = {key for _, key, _, _ in rows}
    ties = {}
    for arm in models:
        twins = set()
        for key in families:
            c = codes[arm][key]
            for i, j in combinations(range(len(c)), 2):
                if torch.equal(c[i], c[j]):
                    twins.add((key[0], i, j))
        ties[arm] = sorted(twins)
    cases = {}
    preferences = defaultdict(lambda: defaultdict(Counter))
    for x, key, known, ids in rows:
        for r, i, j in ties["rank"]:
            if r != key[0] or i not in known or j not in known:
                continue
            pair = f"{ids[i]}/{ids[j]}"
            c = cases.setdefault(pair, Counter())
            c["measured_together"] += 1
            if known[i] == known[j]:
                c["equal_gain"] += 1
                continue
            prefer_i = known[i] > known[j]
            preferences[pair][key, x.numpy().tobytes()][prefer_i] += 1
            c["prefer_first" if prefer_i else "prefer_second"] += 1
            pred = scores(models["wired"], x[None], codes["wired"][key])[0]
            c["correct_strict"] += int((pred[i] > pred[j] if prefer_i else pred[j] > pred[i]).item())
            c["predicted_first"] += int((pred[i] > pred[j]).item())
    for pair, grouped in preferences.items():
        cases[pair]["distinct_observable_inputs"] = len(grouped)
        cases[pair]["conflicting_observable_inputs"] = sum(len(counts) > 1 for counts in grouped.values())
        cases[pair]["empirical_best_given_input"] = sum(max(counts.values()) for counts in grouped.values())
    report = {arm: evaluate(m, rows, codes[arm], held) for arm, m in models.items()}
    report["collision_pairs_by_source_family"] = {k:len(v) for k,v in ties.items()}
    report["measured_collisions"] = cases
    return report


if __name__ == "__main__":
    p = ArgumentParser()
    for k in ("data", "root", "out"):
        p.add_argument(k, type=Path)
    p.add_argument("names", nargs="+")
    a = p.parse_args()
    torch.set_num_threads(1)
    for n in a.names:
        save(a.out / (n + "-ranking.json"), audit(a.data, a.root, a.out, n))
