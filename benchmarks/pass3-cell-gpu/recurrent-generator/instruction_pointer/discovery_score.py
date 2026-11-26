"""Offline semantic validation against the same prefix, with all comparisons paired by state and seed."""

import csv
import json
from collections import Counter, defaultdict

from discovery_states import cli, read, replay, save
from discrete_cells import from_q
from discrete_draft import Cell
from query_witnesses import groups


def token(row):
    r, h, refs = row
    return Cell(r, tuple(map(tuple, refs)), h)


def packet(c, run, ident):
    return dict(
        run=run,
        token=ident,
        rule=c.rule,
        parents=[dict(address=dict(token=t, op=o), version=v) for t, o, v in c.refs],
    )


def write_csv(path, rows):
    with path.open("w") as f:
        w = csv.DictWriter(
            f, list(dict.fromkeys(k for row in rows for k in row)), lineterminator="\n"
        )
        w.writeheader()
        w.writerows(rows)


def score(a, case, source):
    dest = a.out / source / case
    aliases = groups(a, case, "teacher", True) if source == "teacher" else {}
    summaries = []
    selected = {v["run"] for v in read(dest / "states.json")}
    live = {}
    for line in (dest / "frames.jsonl").open():
        frame = json.loads(line)
        for addr in frame["retired"]:
            live.pop((addr["token"], addr["op"]), None)
        for addr, row in frame["updates"]:
            live[addr["token"], addr["op"]] = row["version"]
        r = frame["run"]
        if r not in selected:
            continue
        unit = dest / str(r)
        cached = unit / "measured.csv"
        if cached.exists():
            with cached.open() as f:
                saved = list(csv.DictReader(f))
            if len(saved) == len(read(unit / "samples.json")["records"]) * 6 * 4:
                summaries.extend(saved)
                continue
        gold = read(unit / "gold.json")
        refs = {q["token"]: gain for q, gain in gold}
        slots = read(unit / "samples.json")
        tape = read(unit / "oracle.json")
        previous = {q["token"] for q in tape["requests"] if q["run"] < r}
        legal = []
        good = defaultdict(set)

        def note(c):
            good[c.rule].update(c.refs[:i] for i in range(len(c.refs) + 1))

        for q, g in sorted(gold, key=lambda x: -x[1]):
            c = from_q(q)
            if all(live.get(p[:2]) == p[2] for p in c.refs):
                legal.append(c)
                if g:
                    note(c)
                    for v in aliases.get((r, c), ()):
                        note(v)
        allcells = {}
        batches = {}
        for s in slots["records"]:
            for arm, b in s["batches"].items():
                cells = list(map(token, b["items"]))
                batches[arm, s["seed"]] = (cells, b["attempts"])
            n = s["n"]
            seq = (
                (legal * ((n + len(legal) - 1) // len(legal)))[:n]
                if legal
                else list(map(token, s["batches"]["uniform"]["items"]))
            )
            batches["oracle", s["seed"]] = (seq, 0)
        # Cache only offline verifier results; restore all draws and duplicates before counting.
        for cells, _ in batches.values():
            for c in cells:
                key = Cell(c.rule, c.refs)
                if key not in allcells:
                    allcells[key] = len(allcells) + 1
        probe = unit / "validation-input.json"
        save(probe, dict(tape, requests=[packet(c, r, i) for c, i in allcells.items()]))
        report = replay(a, case, unit / "oracle.json", r, "--recall", probe)
        assert report["unused_recall"] == 0 and len(report["recall_verdicts"]) == len(
            allcells
        )
        verdict = {
            i: (owner, why)
            for run, i, owner, why in report["recall_verdicts"]
            if run == r
        }
        save(unit / "validation.json", report["recall_verdicts"])
        # Prefix membership uses one shared pool including native-certified alias hits.
        for c, i in allcells.items():
            owner, why = verdict[i]
            if why == "match" and refs.get(owner, 0) > 0:
                note(c)
        prefix = [q for q in tape["requests"] if q["run"] < r]
        for (arm, seed), (cells, attempts) in batches.items():
            # Actual ordered admission and EPT for the full-budget counterfactual.
            # All arms use the identical pre-Run state. Token IDs cannot collide with its signed history.
            base = max(previous, default=0) + 1
            fork = unit / "paid-fork.json"
            save(
                fork,
                dict(
                    tape,
                    requests=prefix
                    + [packet(c, r, base + i) for i, c in enumerate(cells)],
                ),
            )
            actual = replay(a, case, fork, r, "--ept-origins")
            credit = dict(actual["ept"]["origins"])
            accepted = actual["counts"]["accepted"] - len(prefix)
            for cut in (4, 16, 64, 256):
                draw = cells[:cut]
                ctr = Counter()
                owners = set()
                for c in draw:
                    owner, why = verdict[allcells[Cell(c.rule, c.refs)]]
                    ctr["reply_" + why] += 1
                    p = good.get(c.rule, set())
                    ctr["template_ok"] += int(() in p)
                    for j in range(len(c.refs)):
                        stage = "first" if j == 0 else "later"
                        if c.refs[:j] in p:
                            ctr[stage + "_den"] += 1
                            ctr[stage + "_ok"] += int(c.refs[: j + 1] in p)
                    if why != "match":
                        continue
                    if owner in previous or owner in owners:
                        ctr["semantic_duplicates"] += 1
                    if refs.get(owner, 0) > 0:
                        ctr["productive_draws"] += 1
                    owners.add(owner)
                new = owners & refs.keys()
                n = len(draw)
                summaries.append(
                    dict(
                        case=case,
                        source=source,
                        run=r,
                        arm=arm,
                        seed=seed,
                        budget=cut,
                        n=n,
                        domain=slots["size"],
                        attempts_full=attempts,
                        physical_repeat=n - len(set(draw)),
                        distinct=len(new),
                        productive=sum(refs[k] > 0 for k in new),
                        oracle_operations=sum(refs[k] for k in new),
                        higher_entries=sum(c.higher for c in draw),
                        actual_full_accepted=accepted,
                        actual_full_productive=sum(
                            credit.get(base + i, 0) > 0 for i in range(len(cells))
                        ),
                        actual_full_ops=sum(
                            credit.get(base + i, 0) for i in range(len(cells))
                        ),
                        **ctr,
                    )
                )
            # Unmatched valid binds are unknown with respect to the oracle ledger, but get actual native credit above.
            if not any(
                verdict[allcells[Cell(c.rule, c.refs)]][1] == "off_reference"
                for c in cells
            ):
                assert accepted == len(
                    {verdict[allcells[Cell(c.rule, c.refs)]][0] for c in cells}
                    & refs.keys()
                )
        write_csv(unit / "measured.tmp", [v for v in summaries if v["run"] == r])
        (unit / "measured.tmp").replace(cached)
    write_csv(dest / "measured.csv", summaries)
    print(case, source, len(summaries), flush=True)


if __name__ == "__main__":
    a = cli().parse_args()
    for case in a.cases:
        for source in ("teacher", "rollout"):
            score(a, case, source)
