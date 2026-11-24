"""Compare symbolic A/B, symbolic candidates with ranking C, and neural execution D."""

import argparse
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryFile
from time import perf_counter

import torch

from alternate_proofs import digest
from anchor_set_audit import check
from composition_relation import Interfaces, Store
from evaluate_field_retrieval import identities
from higher_cell import read
from join_controls import Generator
from relation_cases import select_runs

TRACKS = dict(
    A="Symbolic Execution",
    B="Symbolic Execution",
    C="Symbolic Execution / neural ranking control",
    D="Neural Execution",
)


def measure_frame(gen, frame, ledger):
    seconds, inserts, deletes = gen.advance(frame)
    ledger.append((seconds, inserts, deletes))


def costs(gen, ledger, events):
    previous_union = [False] + [any(e[0] == "union" for e in group) for group in events]
    selected = [v for v, union in zip(ledger, previous_union) if union]
    return dict(
        phases=dict(gen.times),
        work=dict(gen.count),
        index_writes=gen.index.writes,
        index_removals=gen.index.removes,
        prior_union_frames=len(selected),
        prior_union_index_seconds=sum(x[0] for x in selected),
        prior_union_writes=sum(x[1] for x in selected),
        prior_union_removals=sum(x[2] for x in selected),
    )


def shadow(root, case, out, order="ABCD"):
    folder = root / case
    binary = root / "whole-fork-credit/receiver"
    tape = read(folder / "tape.json")
    ref = read(folder / "capture.json")
    runs = set(select_runs(tape, ref["runs"], 72331, 32))
    teacher = {p["token"]: p for p in tape["requests"] if p["run"] in runs}
    eligible = {
        k
        for k, p in teacher.items()
        if 1 <= len({q["address"]["token"] for q in p["parents"]}) <= 2
    }
    # Evaluation-only stratification. No mask, label or signature enters issue().
    novel = identities(read(root / "relation-experiment/train/train.json"))
    evaluation_store = Store(Interfaces(read(folder / "program.json")))
    selected = defaultdict(list)
    for token in eligible:
        selected[teacher[token]["run"]].append(token)
    heldout = set()
    with (folder / "memory.jsonl").open() as stream:
        for line in stream:
            frame = json.loads(line)
            evaluation_store.advance(frame)
            for token in selected[frame["run"]]:
                q = teacher[token]
                keys = [
                    (a["address"]["token"], a["address"]["op"]) for a in q["parents"]
                ]
                if novel(
                    evaluation_store.iface.key(q["rule"], keys, evaluation_store.types)
                ):
                    heldout.add(token)
    data = {}
    result = {}
    for arm in order:
        started = perf_counter()
        gen = Generator(root, read(folder / "program.json"), arm)
        ledger = []
        pack = {}
        with (folder / "memory.jsonl").open() as stream:
            for line in stream:
                f = json.loads(line)
                measure_frame(gen, f, ledger)
                if f["run"] in runs:
                    for k, ps in gen.issue(f, rank_all=True).items():
                        pack[f["run"], k] = ps
        data[arm] = pack
        result[arm] = dict(
            track=TRACKS[arm],
            generation_wall=perf_counter() - started,
            **costs(gen, ledger, ref["events"]),
        )
    # Historical ANN payment gives an external ceiling. Sample equally many requests
    # per program. No event, Run or rule receives information about another arm's candidates.
    historical = read(
        Path(__file__).parent / "run-recall/structured-retrieval" / f"{case}.json"
    )
    budget = min(
        historical["arms"]["multi_ann"]["paid"],
        *(sum(map(len, data[k].values())) for k in "BCD"),
    )
    for arm, pack in data.items():
        start = perf_counter()
        offers = [item for ps in pack.values() for item in ps]
        natural = len(offers)
        if arm == "A":
            rows = [p for _, p in offers]
        else:
            import random

            rng = random.Random(1124)
            ranked = sorted(
                ((score, rng.random(), i) for i, (score, _) in enumerate(offers)),
                reverse=True,
            )
            rows = [offers[i][1] for _, _, i in ranked[:budget]]
            rows.sort(key=lambda p: p["run"])
        result[arm]["generation_wall"] += perf_counter() - start
        for i, p in enumerate(rows, 1):
            p["token"] = i
        started = perf_counter()
        audit = check(folder, binary, tape, rows)
        elapsed = perf_counter() - started
        verdicts = audit["recall_verdicts"]
        hits = {w for _, _, w, _ in verdicts if w is not None}
        accepted = sum(w is not None for _, _, w, _ in verdicts)
        reasons = Counter(reason for _, _, w, reason in verdicts if w is None)
        result[arm].update(
            natural=natural,
            paid=len(rows),
            valid=accepted,
            duplicates=accepted - len(hits),
            reject=reasons,
            distinct=len(hits),
            eligible_hits=len(hits & eligible),
            unseen_pair_hits=len(hits & heldout),
            audited_replay_wall=elapsed,
            generation_plus_replay=result[arm]["generation_wall"] + elapsed,
            reference_repair_seconds=audit["repair_phase_seconds"],
            teacher_and_probe_verify_seconds=audit["verify_seconds"],
            per_run=[
                [
                    r,
                    sum(p["run"] == r for p in teacher.values()),
                    sum(teacher[t]["run"] == r for t in hits),
                ]
                for r in sorted(runs)
            ],
        )
    assert len({result[k]["paid"] for k in "BCD"}) == 1
    return dict(
        mode="native shadow",
        teacher=len(teacher),
        eligible=len(eligible),
        unseen_pairs=len(heldout),
        reference_runs=ref["runs"],
        binary=digest(binary),
        compose=digest(root / "relation-experiment/train/model.pt"),
        field=digest(root / "structured-retrieval/field.pt"),
        arms=result,
    )


def coordinate(step):
    return (step[0], tuple(step[1]), tuple(step[2]))


def lineage(ref, requests, report, accepted, folder):
    # After divergence, align named proofs through their accepted ancestors and source-schedule coordinates.
    # A target with a different proof or an unaligned repair event remains uncredited.
    lookup = {}
    grouped = defaultdict(list)
    visible = {}
    for p in requests:
        grouped[p["run"]].append(p)

    def evidence(schedule, version, hashes):
        return (
            coordinate(schedule[version - 1]) if version > 0 else None,
            tuple(hashes),
        )

    with (folder / "memory.jsonl").open() as frames:
        for line in frames:
            frame = json.loads(line)
            for a in frame["retired"]:
                visible.pop((a["token"], a["op"]))
            for a, row in frame["updates"]:
                visible[a["token"], a["op"]] = row
            for p in grouped[frame["run"]]:
                named = []
                for v in p["parents"]:
                    k = v["address"]["token"], v["address"]["op"]
                    row = visible[k]
                    assert row["version"] == v["version"]
                    named.append(
                        (*k, evidence(ref["schedule"], v["version"], row["hashes"]))
                    )
                key = (
                    coordinate(ref["schedule"][p["run"] - 1]),
                    p["rule"],
                    tuple(named),
                )
                if key in lookup:
                    raise ValueError("ambiguous reference coordinate")
                lookup[key] = p["token"]
    mapping = {}
    hits = set()
    by_run = Counter()
    for p in accepted:
        parents = []
        for a, hashes in zip(p["parents"], p["fields"], strict=True):
            token = a["address"]["token"]
            if token in mapping:
                t = mapping[token]
            elif token < 0 and token % 2:
                t = token
            else:
                break
            parents.append(
                (
                    t,
                    a["address"]["op"],
                    evidence(report["schedule"], a["version"], hashes),
                )
            )
        else:
            step = coordinate(report["schedule"][p["run"] - 1])
            w = lookup.get((step, p["rule"], tuple(parents)))
            if w is not None:
                mapping[p["token"]] = w
                if w not in hits:
                    by_run[p["run"]] += 1
                    hits.add(w)
    return len(hits), [[i, by_run[i]] for i in range(1, report["runs"] + 1)]


def exclusive(root, case, arm, cap=None, limit=None):
    folder = root / case
    program = read(folder / "program.json")
    ref = read(folder / "capture.json")
    binary = root / "whole-fork-credit/receiver"
    requests = read(folder / "tape.json")["requests"]
    gen = Generator(root, program, arm)
    ledger = []
    issued = 0
    accepted = []
    last = 0
    previous = {}
    started = perf_counter()
    cmd = [binary, "online", folder / "program.json", "-", "audit"]
    if limit is not None:
        cmd.append(str(limit))
    with (
        TemporaryFile(mode="w+") as err,
        subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True
        ) as proc,
    ):
        report = None
        overflow = None
        try:
            for line in proc.stdout:
                frame = json.loads(line)
                if "role" in frame:
                    report = frame
                    break
                last = frame["run"]
                for p in frame["accepted"]:
                    accepted.append(dict(**p, fields=previous[p["token"]]))
                previous = {}
                measure_frame(gen, frame, ledger)
                if last % 100 == 0:
                    print(case, arm, cap, last, issued, flush=True)
                try:
                    choices = (
                        gen.issue(
                            frame,
                            bootstrap=True,
                            live=True,
                            remaining=None if cap is None else cap - issued,
                        )
                        if cap is None or cap > issued
                        else {}
                    )
                except OverflowError as exc:
                    overflow = str(exc)
                    proc.kill()
                    break
                rows = [q for ps in choices.values() for q in ps]
                if cap is not None:
                    rows = rows[: cap - issued]
                for q in rows:
                    issued += 1
                    q["token"] = issued
                    previous[issued] = [
                        gen.store.visible[a["address"]["token"], a["address"]["op"]][
                            "hashes"
                        ]
                        for a in q["parents"]
                    ]
                proc.stdin.write(json.dumps(rows) + "\n")
                proc.stdin.flush()
            proc.stdin.close()
            code = proc.wait()
            err.seek(0)
            error = err.read().strip()
        finally:
            if proc.poll() is None:
                proc.kill()
    elapsed = perf_counter() - started
    if report is None:
        if (not overflow and "source panic" not in error) or limit is not None:
            raise RuntimeError((code, error, last))
        prefix = exclusive(root, case, arm, cap, last - 1)
        prefix.update(
            failure_run=last,
            failure_reason=overflow or "native source panic",
            failed_attempt_wall=elapsed,
            failed_attempt_paid=issued,
        )
        return prefix
    assert not code and not report["unused"]
    counts = report["counts"]
    assert issued == counts["accepted"] + counts["duplicates"] + sum(
        counts["rejected"].values()
    )
    common = 0
    for i, s in enumerate(report["schedule"]):
        if i >= ref["runs"] or any(
            report[k][i] != ref[k][i] for k in ("schedule", "writes", "rhs")
        ):
            break
        common += 1
    count, by_run = lineage(ref, requests, report, accepted, folder)
    return dict(
        track=TRACKS[arm],
        mode="exclusive",
        cap=cap,
        runs=report["runs"],
        reference_runs=ref["runs"],
        paid=issued,
        counts=counts,
        matches=report["matches"],
        reference_matches=ref["matches"],
        final_equal=ref["state_sha"] == report["state_sha"],
        state_sha=report["state_sha"],
        failure_run=None,
        exact_common_runs=common,
        exact_common_commits=sum(s[4] for s in ref["schedule"][:common]),
        lineage_winners=count,
        lineage_increments=by_run,
        unobserved_last_receipts=counts["accepted"] - len(accepted),
        wall=elapsed,
        native_verify=report["verify_seconds"],
        native_repair=report["repair_phase_seconds"],
        **costs(gen, ledger, report["events"]),
    )


def run_exclusive(root, case, out):
    # One paid request per reference commit as a workload-level budget.
    # Generation sees no rule-specific or per-event teacher allocation.
    quota = read(root / case / "capture.json")["matches"]
    arms = {}
    for arm in "ABCD":
        arms[arm] = exclusive(root, case, arm, None if arm == "A" else quota)
    realized = min(arms[k].get("failed_attempt_paid", arms[k]["paid"]) for k in "BCD")
    if realized < quota:
        quota = realized
        for k in "BCD":
            if arms[k].get("failed_attempt_paid", arms[k]["paid"]) != quota:
                arms[k] = exclusive(root, case, k, quota)
    assert all(
        arms[k].get("failed_attempt_paid", arms[k]["paid"]) == quota for k in "BCD"
    )
    return dict(mode="exclusive", budget=quota, arms=arms)


def natural(root, case, out):
    return dict(
        mode="exclusive, uncapped program budget, eight per event",
        arms={arm: exclusive(root, case, arm) for arm in "BCD"},
    )


def timing(root, case, out):
    """Rotate arm order and time two fresh native controls each round."""
    folder = root / case
    binary = root / "whole-fork-credit/receiver"
    reference = read(folder / "capture.json")["state_sha"]
    baseline = read(out / f"{case}-shadow.json")["arms"]
    rounds = []
    for round_id, order in enumerate(("ABCD", "BCDA", "CDAB", "DABC")):
        controls = {}
        for mode in (
            ("reference", "replay") if round_id % 2 == 0 else ("replay", "reference")
        ):
            tape = folder / "tape.json" if mode == "replay" else "-"
            start = perf_counter()
            res = subprocess.run(
                [binary, mode, folder / "program.json", tape, "audit"],
                check=True,
                capture_output=True,
            )
            wall = perf_counter() - start
            native = json.loads(res.stdout)
            assert native["state_sha"] == reference
            controls[mode] = wall
        arms = shadow(root, case, out, order)["arms"]
        for k, v in arms.items():
            for metric in ("paid", "eligible_hits", "distinct", "duplicates", "reject"):
                assert v[metric] == baseline[k][metric], (case, k, metric)
        rounds.append(
            dict(
                order=order,
                native=controls,
                arms={
                    k: {
                        m: v[m]
                        for m in (
                            "generation_wall",
                            "audited_replay_wall",
                            "generation_plus_replay",
                            "phases",
                            "teacher_and_probe_verify_seconds",
                            "reference_repair_seconds",
                            "prior_union_index_seconds",
                        )
                    }
                    for k, v in arms.items()
                },
            )
        )
    return dict(mode="shadow, paired audited CPU observations", rounds=rounds)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=("shadow", "exclusive", "timing", "natural"))
    p.add_argument("root", type=Path)
    p.add_argument("case")
    a = p.parse_args()
    torch.set_num_threads(1)
    out = a.root / "track-diagnostic"
    out.mkdir(exist_ok=True)
    fn = dict(shadow=shadow, exclusive=run_exclusive, timing=timing, natural=natural)[
        a.mode
    ]
    (out / f"{a.case}-{a.mode}.json").write_text(
        json.dumps(fn(a.root, a.case, out), indent=2) + "\n"
    )
