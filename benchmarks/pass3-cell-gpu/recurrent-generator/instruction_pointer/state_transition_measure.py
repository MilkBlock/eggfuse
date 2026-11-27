"""Measure complete named-token probabilities, conditioned on published native snapshots."""

import json
import os
import pickle
from itertools import product
from pathlib import Path

import torch

from cell_kv_study import digest
from cell_kv_world import World
from cell_transaction import STATUS
from competition_corpus import out
from competition_corpus import world as old_world
from competition_results import table
from partner_index_worlds import args
from state_transition_corpus import folder, world
from state_transition_train import load


def read(p):
    return pickle.loads(p.read_bytes())


def score(w, net, r):
    m = net.state(w, r["state"])
    return {t: float((-net.token_loss(w, m, t)).exp()) for t in r["labels"]}, m


def groups(before, after, tid_limit):
    a = {t for t, v in before["labels"].items() if v["positive"]}
    b = {t for t, v in after["labels"].items() if v["positive"]}
    achieved = after["baseline"] - before["baseline"]
    finished = {t for t in a - b if set(before["labels"][t]["gain"]) <= achieved}
    return {
        "completed": finished,
        "persistent": a & b,
        "new": b - a,
        "other_lost": a - b - finished,
        "newly_productive_higher": {t for t in b - a if t[0] >= tid_limit},
    }


def mass(p, ts):
    return sum(p.get(t, 0.0) for t in ts)


def run(a, d):
    actor = load(a, "frozen", 71).actor
    corpus = []
    example = []
    signatures = {split: set() for split in ("train", "test")}
    for p in sorted(out(a).glob("train-*.pkl")):
        data = read(p)
        initial_higher = set()
        # In the prior corpus, Higher roots can be found via the world's real catalogue.
        _, kind, i = p.stem.split("-")

        w = old_world(a, actor, kind, int(i), True)
        flags = []
        for s, _, v, _ in data:
            hs = [t for t in v if t[0] >= w.primitives]
            flags.append(bool(hs))
            initial_higher.update(t for t in hs if any(ref[0] >= 0 for ref in t[1]))
        corpus.append(
            {
                "source": "previous",
                "program": p.stem,
                "states": len(data),
                "positive_tokens": sum(len(v) for _, _, v, _ in data),
                "positive_states": len(data),
                "auto": 0,
                "extra": 0,
                "pairs": 0,
                "higher_with_generated_parent": len(initial_higher),
                "higher_after_first": sum(flags[1:]),
            }
        )
    for split in ("train", "test"):
        for p in sorted(folder(a).glob(f"{split}-*.pkl")):
            r = read(p)
            w = world(a, actor, int(p.stem.split("-")[1]), split == "train")
            signatures[split].update(digest(w))
            rows = r["states"]
            positive = lambda row: any(l["positive"] for l in row["labels"].values())
            live = set(r["autonomous"])
            corpus.append(
                {
                    "source": split,
                    "program": p.stem,
                    "states": len(rows),
                    "distinct_snapshots": len(
                        {repr(x["state"]) for x in rows.values()}
                    ),
                    "candidate_interventions": sum(
                        len(x["labels"]) for x in rows.values()
                    ),
                    "positive_states": sum(map(positive, rows.values())),
                    "auto": len(live),
                    "extra": len(rows) - len(live),
                    "pairs": len(r["pairs"]),
                    "auto_positive": sum(positive(rows[k]) for k in live),
                    "positive_tokens": sum(
                        sum(v["positive"] for v in row["labels"].values())
                        for row in rows.values()
                    ),
                    "higher_with_generated_parent": sum(
                        sum(
                            v["positive"]
                            and t[0] >= w.primitives
                            and any(ref[0] > 0 for ref in t[1])
                            for t, v in row["labels"].items()
                        )
                        for row in rows.values()
                    ),
                }
            )
    assert not signatures["train"] & signatures["test"]
    table(d, "corpus", corpus)
    raw = []
    flip = []
    versions = []
    within = []
    autopath = []
    for arm, seed in product(("frozen", "teacher", "transition"), (71, 113)):
        net = load(a, arm, seed)
        for i in range(6):
            r = read(folder(a) / f"test-{i}.pkl")
            w = world(a, net.actor, i, False)
            net.prepare(w)
            rows = r["states"]
            scores = {
                k: score(w, net, x) for k, x in rows.items() if x["state"]["menu"]
            }
            for k in r["autonomous"]:
                row = rows[k]
                p, _ = scores[k]
                good = {t for t, l in row["labels"].items() if l["positive"]}
                autopath.append(
                    {
                        "arm": arm,
                        "seed": seed,
                        "case": i,
                        "window": len(k),
                        "targets": len(good),
                        "positive": mass(p, good),
                        "higher": mass(p, [t for t in good if t[0] >= w.primitives]),
                        "complete_mass": sum(p.values()),
                    }
                )
            for pair in r["pairs"]:
                k, j, n = [pair[x] for x in ("before", "blank", "after")]
                x, y = rows[k], rows[n]
                ps, _ms = scores[k]
                pj, mj = scores[j]
                pn, mn = scores[n]
                if (
                    i == 0
                    and len(k) == 0
                    and pair["token"][0] == w.outnames["Ready"]
                    and seed == 71
                ):
                    ts = groups(x, y, w.primitives)["newly_productive_higher"]
                    example.append(
                        {
                            "arm": arm,
                            "before": x["state"],
                            "after": y["state"],
                            "blank": rows[j]["state"],
                            "request": pair["token"],
                            "receipt": pair["receipt"],
                            "update": pair["publication"],
                            "new_higher": [
                                {
                                    "token": t,
                                    "p_before": ps.get(t, 0),
                                    "p_blank": pj.get(t, 0),
                                    "p_after": pn[t],
                                    "verified_rows": y["labels"][t]["gain"],
                                }
                                for t in ts
                            ],
                        }
                    )
                for cat, ts in groups(x, y, w.primitives).items():
                    raw.append(
                        {
                            "arm": arm,
                            "seed": seed,
                            "case": i,
                            "window": len(k),
                            "first": pair["token"][0],
                            "category": cat,
                            "targets": len(ts),
                            "before": mass(ps, ts),
                            "blank": mass(pj, ts),
                            "after": mass(pn, ts),
                            "in_old_domain": sum(t in ps for t in ts),
                            "gated": sum(
                                t in y["labels"]
                                and STATUS[y["labels"][t]["receipt"][1]]
                                in ("untriggered_rule", "watermark")
                                for t in ts
                            ),
                            "ctx_vs_empty": float((mn["ctx"] - mj["ctx"]).norm()),
                        }
                    )
            # Matched states after two interchangeable producers, with different actual payloads.
            siblings = read(folder(a) / f"siblings-{i}.pkl")
            pair = []
            for t, s in siblings:
                p, _m = score(w, net, s)
                (good,) = [
                    u
                    for u, v in s["labels"].items()
                    if u[0] >= w.primitives and v["positive"]
                ]
                hi = {u for u in p if u[0] >= w.primitives}
                correct = p[good]
                pair.append(
                    (good, correct, max(p[u] for u in hi - {good}), mass(p, hi), s)
                )
            l, h = pair
            assert l[0][1] == h[0][1] and l[0][0] != h[0][0]
            assert [(p[0], p[3]) for p in l[4]["state"]["ports"]] == [
                (p[0], p[3]) for p in h[4]["state"]["ports"]
            ]
            for asid, ok, wrong, total, _ in pair:
                flip.append(
                    {
                        "arm": arm,
                        "seed": seed,
                        "case": i,
                        "correct": ok,
                        "other": wrong,
                        "all_higher": total,
                        "within_higher": ok / total if total else 0,
                        "both": l[1] > l[2] and h[1] > h[2],
                        "correct_tid": asid[0],
                    }
                )
            probe = read(folder(a) / f"within-{i}.pkl")
            p, _ = scores[()]
            pp, _ = score(
                w, net, {"state": probe["post_submit"], "labels": probe["labels"]}
            )
            for t, label in probe["labels"].items():
                orig = rows[()]["labels"][t]
                within.append(
                    {
                        "arm": arm,
                        "seed": seed,
                        "case": i,
                        "selected": t == probe["first"],
                        "status": STATUS[label["receipt"][1]],
                        "before": p[t],
                        "after": pp[t],
                        "was_positive": orig["positive"],
                        "new_rows": len(label["gain"]),
                    }
                )
        v = read(folder(a) / "versions.pkl")
        w = World(v["dir"], net.actor, entry_table=None, sides="")
        net.prepare(w)
        for phase in ("initial", "blank", "after"):
            r = v[phase]
            p, _ = score(w, net, r)

            values = {t for t, l in r["labels"].items() if l["positive"]}
            versions.append(
                {
                    "arm": arm,
                    "seed": seed,
                    "phase": phase,
                    "stale": mass(p, v["stale"]),
                    "observed": mass(p, values),
                    "targets": len(values),
                    "versions": str([p[0] for p in r["state"]["ports"]]),
                    "stale_replay": ",".join(STATUS[x[1]] for x in v["stale"].values()),
                }
            )
    (d / "example.json").write_text(json.dumps(example, indent=2) + "\n")
    for name, rs in (
        ("transitions", raw),
        ("matched-higher", flip),
        ("before-seal", within),
        ("versions", versions),
        ("autonomous-states", autopath),
    ):
        table(d, name, rs)


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    d = Path(os.getenv("RESULTS_DIR", "run-recall/state-transition"))
    d.mkdir(parents=True, exist_ok=True)
    with torch.no_grad():
        run(a, d)
