"""Same-state native audits; teacher evidence is offline only."""

from collections import defaultdict
from time import perf_counter

import numpy as np

from discovery_states import cli, read, replay, save
from discrete_cells import from_q
from parallel_fit import TRAIN
from recursive_train import folder


def select_runs(pages, executed):
    first = {p["run"]: p for p in pages if p["page"] == 0}
    active = sorted(r for r in first if executed[r])
    idle = sorted(set(first) - set(active))

    def repeats(r):
        cells = list(map(str, first[r]["generated"]))
        return len(cells) - len(set(cells))

    high = sorted(first, key=lambda r: (-repeats(r), r))[:8]
    rng = np.random.default_rng(673)
    strata = defaultdict(list)
    for tag, pool in [("active", active), ("idle", idle)]:
        for r in rng.choice(pool, min(8, len(pool)), replace=False):
            strata[int(r)].append(tag)
    for r in high:
        strata[r].append("repeat")
    if active:
        gap = next((r for r in idle if r > active[0]), None)
        if gap:
            strata[gap].append("first_gap")
    return strata


def build(a, case, source):
    dest = a.out / "experience" / case / source
    dest.mkdir(parents=True, exist_ok=True)
    tape = (
        dest / (case + "-stream-multi") / "issued.json"
        if source == "self"
        else folder(a.data, case) / "tape.json"
    )
    rows = read(tape)
    original = rows["requests"]
    audit = replay(a, case, tape, "--memory", dest / "frames.jsonl", "--ept-origins")
    assert audit["counts"]["accepted"] == len(original)
    gains = dict(audit["ept"]["origins"])
    by = defaultdict(list)
    executed = defaultdict(list)
    for q in original:
        by[q["run"]].append(q)
        if gains.get(q["token"], 0):
            executed[q["run"]].append(q)
    preissued = {}
    if source == "self":
        assert audit["state_sha"] == read(dest / "run.json")["state_sha"]
        raw = read(dest / "pages.json")
        receipts = read(dest / "responses.json")
        for p in raw:
            if p["page"] == 0:
                r = p["run"]
                preissued[r] = {
                    v["id"] for v in receipts[: p["paid_before"]] if v["run"] == r
                }
        assert all(p["epoch"] is not None for p in raw)
        strata = select_runs(raw, executed)
    else:
        strata = {
            int(p.name.split("-teacher-")[1].split(".")[0]): ["teacher"]
            for p in (a.contract / "train/env").glob(case + "-teacher-*.pkl.gz")
        }
    labels = []
    for r, tags in sorted(strata.items()):
        start = perf_counter()
        prefix = [q for q in original if q["run"] < r]
        base = prefix + by[r]
        candidates = replay(a, case, tape, r - 1, "--audit-next-proofs")
        known = {from_q(q) for q in by[r]}
        extra = []
        uid = max((q["token"] for q in base), default=0) + 1
        for q in candidates:
            assert q["run"] == r
            c = from_q(q)
            if c not in known:
                known.add(c)
                extra.append(dict(q, token=uid + len(extra)))
        logged = {}
        omitted = []
        if extra:
            path = dest / f"fork-{r}.json"
            save(path, dict(rows, requests=base + extra))
            trial = replay(a, case, path, r, "--ept-origins")
            orig = replay(a, case, tape, r, "--ept-origins")
            pre = dict(orig["ept"]["origins"])
            post = dict(trial["ept"]["origins"])
            stable = all(
                post.get(q["token"], 0) == pre.get(q["token"], 0) for q in base
            )
            for q in extra:
                gain = post.get(q["token"], 0)
                if gain and stable:
                    omitted.append([q, gain])
            counts = [
                sum(report["ept"]["signed_external"])
                + sum(report["ept"]["signed_internal"])
                for report in (orig, trial)
            ]
            if stable and counts[1] - counts[0] != sum(gain for _, gain in omitted):
                raise ValueError(
                    "extra receipts do not account for total signed effect difference"
                )
            logged = {
                "unchanged_original_credits": stable,
                "baseline": counts[0],
                "fork_total": counts[1],
                "attempted": len(extra),
                "fork_counts": trial["counts"],
            }
        used = [
            [q, gains[q["token"]]]
            for q in executed[r]
            if q["token"] not in preissued.get(r, ())
        ]
        labels.append(
            {
                "run": r,
                "strata": tags,
                "program_sha256": rows["program_sha256"],
                "source": source,
                "origin_tape": str(tape),
                "already_issued": sorted(preissued.get(r, ())),
                "executed": used,
                "omitted": omitted,
                "audit": logged,
                "native_certificates": len(candidates),
                "seconds": perf_counter() - start,
            }
        )
    save(dest / "labels.json", labels)
    print(
        case,
        source,
        len(labels),
        sum(len(s["executed"]) for s in labels),
        sum(len(s["omitted"]) for s in labels),
        flush=True,
    )


if __name__ == "__main__":
    a = cli().parse_args()
    for case in sorted({c for c, _ in TRAIN}):
        for source in ("teacher", "self"):
            build(a, case, source)
