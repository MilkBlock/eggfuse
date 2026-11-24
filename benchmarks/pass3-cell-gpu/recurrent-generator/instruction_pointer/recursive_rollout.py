"""Native exclusive rollouts, offline expert aggregation and frozen strata."""

import argparse
import json
import random
import subprocess
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryFile
from time import perf_counter

import torch

from anchor_set_audit import check
from join_controls import Generator
from recursive_agent import RUN_PACKETS, Compose, Policy
from recursive_train import TRAIN, binary, folder, keys, read
from relation_cases import request

EVAL = (
    "fact",
    "loopfact",
    "sum-divisors",
    "jacobi",
    "cyk801",
    "grammar-17122",
    "grammar-91627433",
    "grammar-72102993",
    "grammar-layout-832749",
)


def get_policy(root, d, arm, phase):
    program = read(d / "program.json")
    if arm == "legacy":
        return Generator(root, program, "D")
    model = Compose()
    model.load_state_dict(
        torch.load(root / "recursive-agent" / (phase + ".pt"), weights_only=True)
    )
    return Policy(
        program, root, model.eval(), arm == "pending", 2 if arm == "two" else None
    )


def online(root, case, arm, out, phase="dagger", limit=None, collect=False):
    d = folder(root, case)
    out.mkdir(exist_ok=True, parents=True)
    torch.manual_seed(1861)
    policy = get_policy(root, d, arm, phase)
    start = perf_counter()
    args = [binary(root), "online", d / "program.json", "-", "audit"]
    if limit is not None:
        args.append(str(limit))
    args += ["--export", out / "state.json", "--ept"]
    sent = []
    trace = []
    final = None
    failure = None
    with (
        TemporaryFile(mode="w+") as err,
        (out / "memory.jsonl").open("w") as frames,
        subprocess.Popen(
            args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err, text=True
        ) as proc,
    ):
        try:
            for line in proc.stdout:
                f = json.loads(line)
                if "role" in f:
                    final = f
                    break
                arrived = perf_counter() - start
                if collect:
                    frames.write(line)
                if arm == "legacy":
                    policy.advance(f)
                    owners = set()
                    groups = policy.issue(
                        f,
                        bootstrap=True,
                        live=True,
                        remaining=RUN_PACKETS,
                        frontier=owners,
                    )
                    rows = [x for group in groups.values() for x in group]
                    visited = (
                        policy.count["typed_positions_tested"]
                        + policy.count["postings_visited"]
                    )
                    front = len(owners)
                else:
                    rows = policy.issue(f, explore=collect)
                    visited = (
                        policy.reader.count["visited"]
                        + policy.reader.count["bucket_visits"]
                    )
                    front = policy.last_frontier
                for q in rows:
                    q["token"] = len(sent) + 1
                    sent.append(q)
                trace.append(
                    [
                        f["run"],
                        perf_counter() - start,
                        len(sent),
                        visited,
                        len(policy.pool) if arm == "pending" else 0,
                        front,
                        arrived,
                    ]
                )
                proc.stdin.write(json.dumps(rows) + "\n")
                proc.stdin.flush()
        except OverflowError as exc:
            failure = str(exc)
            proc.kill()
        finally:
            proc.stdin.close()
            code = proc.wait()
            err.seek(0)
            error = err.read()
    elapsed = perf_counter() - start
    if final is None:
        failure = failure or error
        if limit is not None or (
            not failure
            or "source panic" not in failure
            and "projections" not in failure
        ):
            raise RuntimeError((case, arm, code, failure))
        # Replaying only the last completed prefix discards the failing request.
        # Keep the original input tape independently of the prefix-state export.
        failed_tape = read(d / "tape.json")
        failed_tape["requests"] = sent
        (out / "failed-issued.json").write_text(json.dumps(failed_tape))
        result = online(root, case, arm, out, phase, max(0, f["run"] - 1), collect)
        result.update(
            failure=failure,
            termination="execution_failure"
            if "source panic" in failure
            else "budget_exhausted",
            prefix_paid=result["paid"],
            trace=trace[: result["runs"]],
            paid=len(sent),
            wall=elapsed,
            ept=result["signed_ops"] / max(1, len(sent)),
            eps=result["signed_ops"] / elapsed,
            visits=policy.count["typed_positions_tested"]
            + policy.count["postings_visited"]
            if arm == "legacy"
            else policy.reader.count["visited"] + policy.reader.count["bucket_visits"],
            unobserved_verdicts=len(sent) - result["paid"],
            failed_run=f["run"],
            failed_wall=elapsed,
            failed_paid=len(sent),
        )
        (out / "metrics.json").write_text(json.dumps(result))
        return result
    assert code == 0 and final["unused"] == 0
    counts = final["counts"]
    assert len(sent) == counts["accepted"] + counts["duplicates"] + sum(
        counts["rejected"].values()
    )
    tape = {k: v for k, v in read(d / "tape.json").items() if k != "requests"}
    tape["requests"] = sent
    (out / "issued.json").write_text(json.dumps(tape))
    ref = read(d / "capture.json")
    common = next(
        (
            i
            for i in range(min(final["runs"], ref["runs"]))
            if any(final[k][i] != ref[k][i] for k in ["schedule", "rhs", "writes"])
        ),
        min(final["runs"], ref["runs"]),
    )
    equal = final["state_sha"] == ref["state_sha"]
    ops = sum(final["ept"]["signed_external"]) + sum(final["ept"]["signed_internal"])
    # A finite source schedule can end without being a mathematical fixed point.
    terminal = "verified_reference_endpoint" if equal else "neural_quiescence"
    if limit is not None:
        terminal = "budget_exhausted"
    if not equal and (
        policy.count["bounded_runs"]
        or arm == "legacy"
        and any(
            (p[2] - (trace[i - 1][2] if i else 0)) == RUN_PACKETS
            for i, p in enumerate(trace)
        )
    ):
        terminal = "budget_exhausted"
    if equal and case.startswith(("cyk", "grammar")) and not final["schedule"][-1][-1]:
        terminal = "verified_fixed_point"
    result = dict(
        arm=arm,
        case=case,
        termination=terminal,
        final_equal=equal,
        state_sha=final["state_sha"],
        reference_sha=ref["state_sha"],
        runs=final["runs"],
        paid=len(sent),
        counts=counts,
        ops=final["ept"],
        signed_ops=ops,
        ept=ops / max(1, len(sent)),
        eps=ops / elapsed,
        wall=elapsed,
        trace=trace,
        common=common,
        work=dict(policy.count),
        read_work={} if arm == "legacy" else dict(policy.reader.count),
        failure=None,
        visits=trace[-1][3] if trace else 0,
    )
    (out / "metrics.json").write_text(json.dumps(result))
    return result


def expert(root, case):
    d = folder(root, case)
    out = root / "recursive-agent" / ("own-" + case)
    result = online(root, case, "free", out, "teacher", limit=32, collect=True)
    # Sample bounded exact expert menus on the learner's own trajectory offline.
    # Enumerate coherent substitutions, then let Rust check primitives, effects'
    # preconditions, visibility, watermark and dirty state. No proposal goes live.
    policy = get_policy(root, d, "free", "teacher")
    rd = policy.reader
    probes = []
    visited = 0
    rng = random.Random(70121)
    for line in (out / "memory.jsonl").open():
        f = json.loads(line)
        rd.advance(f)
        for rid, wm in f["rules"]:
            roles = rd.iface.roles[rid]
            if not roles:
                continue
            budget = 1600
            found = []

            def extend(path, slots):
                nonlocal budget, visited
                if not budget or len(found) >= 24:
                    return
                if len(path) == len(roles):
                    found.append(request(f["run"], rid, path, rd.store))
                    return
                table, cols = roles[len(path)]
                pool = list(rd.live[rd.tabs[table]])
                rng.shuffle(pool)
                for k in pool:
                    if not budget or len(found) >= 24:
                        break
                    budget -= 1
                    visited += 1
                    row = rd.store.visible[k]
                    copy = slots.copy()
                    if all(
                        v is None or copy.setdefault(v, h) == h
                        for v, h in zip(cols, row["hashes"], strict=True)
                    ):
                        extend((*path, k), copy)

            extend((), {})
            probes += found
    # --recall on a replay of the issued prefix, with the identical Run limit.
    tape = read(out / "issued.json")
    for i, p in enumerate(probes, 1):
        p["token"] = i
    probe = out / "probes.json"
    probe.write_text(json.dumps({**tape, "requests": probes}))
    report = json.loads(
        subprocess.check_output(
            [
                binary(root),
                "replay",
                d / "program.json",
                out / "issued.json",
                "audit",
                "32",
                "--recall",
                probe,
            ]
        )
    )
    assert report["state_sha"] == result["state_sha"] and report["unused_recall"] == 0
    positive = [
        probes[i - 1]
        for _, i, w, reason in report["recall_verdicts"]
        if w is not None or reason == "off_reference"
    ]
    (out / "labels.json").write_text(json.dumps(positive))
    return dict(
        case=case,
        probes=len(probes),
        expert_visits=visited,
        positive=len(positive),
        off_policy=sum(x[3] == "off_reference" for x in report["recall_verdicts"]),
    )


def frozen(root, case, arm):
    d = folder(root, case)
    negative = read(
        Path(__file__).parent / "run-recall/shared-composition" / f"{case}-higher.json"
    )["negative_ids"]
    missed = read(Path(__file__).parent / "run-recall/oracle-headroom/divergence.json")[
        case
    ]
    first = {p["token"] for p in missed["missing"]}
    targets = set(negative) | first
    tape = read(d / "tape.json")
    wanted = {p["run"] for p in tape["requests"] if p["token"] in targets}
    policy = get_policy(root, d, arm, "dagger")
    proposals = []
    byrun = defaultdict(list)
    for q in tape["requests"]:
        if q["token"] in targets:
            byrun[q["run"]].append(q)
    stages = defaultdict(set)
    witnesses = set()
    for line in (d / "memory.jsonl").open():
        f = json.loads(line)
        # Replay the full policy history for every arm, including rule recency.
        paths = defaultdict(list)
        if arm != "legacy":
            for q in byrun[f["run"]]:
                path = tuple(keys(q)[j] for j in policy.reader.order(q["rule"]))
                paths[q["rule"]].append((q["token"], path))

            def observe(r, seq, dom):
                for tok, path in paths.get(r, ()):
                    stages["rule_read"].add(tok)
                    if path[: len(seq)] != seq:
                        continue
                    if path[len(seq)] in dom:
                        stages[
                            "first_retrieved" if not seq else "partial_retrieved"
                        ].add(tok)
                    if len(seq) + 1 == len(path) and path[-1] in dom:
                        stages["complete_tuple_scored"].add(tok)

            policy.observer = observe if paths else None
        if arm == "legacy":
            policy.advance(f)
            groups = policy.issue(f, bootstrap=True, remaining=RUN_PACKETS)
            rows = [q for group in groups.values() for q in group]
        else:
            rows = policy.issue(f)
        if f["run"] in wanted:
            signatures = {(q["rule"], keys(q)) for q in rows}
            witnesses.update(
                q["token"]
                for q in byrun[f["run"]]
                if (q["rule"], keys(q)) in signatures
            )
            proposals += rows
    for i, p in enumerate(proposals, 1):
        p["token"] = i
    res = check(d, binary(root), tape, proposals)
    hits = {w for _, _, w, _ in res["recall_verdicts"] if w is not None}
    return dict(
        case=case,
        arm=arm,
        first=[len(first & hits), len(first)],
        higher=[len(set(negative) & hits), len(negative)],
        paid=len(proposals),
        hits=len(hits),
        target_union=len(targets),
        funnel={k: len(v) for k, v in stages.items()},
        original_issued=len(witnesses),
        distinct_verified_targets=len(hits & targets),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("mode", choices=["expert", "frozen", "online"])
    p.add_argument("cases", nargs="*")
    p.add_argument("--arms", nargs="+", default=["two", "free", "pending"])
    a = p.parse_args()
    root = a.root.resolve()
    out = root / "recursive-agent"
    torch.set_num_threads(1)
    if a.mode == "expert":
        v = [expert(root, c) for c in (a.cases or TRAIN)]
        (out / "expert.json").write_text(json.dumps(v, indent=2))
    else:
        for c in a.cases or EVAL:
            for arm in a.arms:
                if a.mode == "online":
                    v = online(root, c, arm, out / (c + "-" + arm))
                    print(
                        c,
                        arm,
                        v["paid"],
                        v["counts"]["accepted"],
                        v["wall"],
                        flush=True,
                    )
                else:
                    v = frozen(root, c, arm)
                    (out / (c + "-" + arm + "-frozen.json")).write_text(json.dumps(v))
                    print(v, flush=True)
