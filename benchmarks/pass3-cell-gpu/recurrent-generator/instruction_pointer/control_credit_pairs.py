"""Offline native forks at real drained drafts, plus fine credit on the original requests."""

import gzip
import hashlib
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from cell_transaction import STATUS
from discovery_score import packet, token
from discovery_states import read
from execution_control import CONTINUE, SEAL, SUBMIT
from execution_control_data import arguments, effects
from fine_credit import labels
from recursive_coverage import Target


def digest(value):
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def event_requests(event, accepted):
    """Retain original request IDs, order, named bindings and raw feedback; no deduplication."""
    rows = []
    draft = []
    credits = []
    dirty = {r: b for r, _, b in event["rules"]}
    for i, a in enumerate(event["actions"]):
        if a["action"] == CONTINUE:
            draft.extend(a["tokens"])
        if a["action"] != SUBMIT:
            continue
        for cell, uid, status in zip(draft, a["ids"], a["status"], strict=True):
            q = packet(token(cell), event["run"], uid)
            if status == 0 and accepted[uid] != q:
                raise ValueError("accepted request identity changed")
            rows.append(q)
            credits.append(
                {
                    "request": q,
                    "reply": STATUS[status],
                    "submit_action": i,
                    "dirty": dirty[q["rule"]],
                }
            )
        draft = []
    if draft:
        raise ValueError("unresolved draft at seal")
    if event["reason"] == "teacher_prefix":
        for q, r in zip(event["selected"], event["responses"], strict=True):
            rows.append(dict(q, token=r[0]))
    return rows, credits


class Forks:
    def __init__(self, a, idx, tmp, sha):
        self.binary = a.runtime_binary
        self.program = a.previous / "programs" / f"{idx:04d}" / "program.json"
        if hashlib.sha256(self.program.read_bytes()).hexdigest() != sha:
            raise ValueError("Recipe identity mismatch")
        self.tape = tmp / "fork.json"
        self.export = tmp / "graph.json"
        self.sha = sha
        self.cache = {}
        self.calls = 0
        self.seconds = 0.0
        subprocess.run(
            [
                self.binary,
                "reference",
                self.program,
                "-",
                "audit",
                "--export",
                self.export,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        self.target = Target(read(self.program), read(self.export))

    def call(self, rows, stop=None, exact=False):
        self.tape.write_text(
            json.dumps(
                {
                    "schema": "cell-token-replay/v2",
                    "program_sha256": self.sha,
                    "requests": rows,
                    "repair_events": [],
                }
            )
        )
        args = [self.binary, "replay", self.program, self.tape, "audit"]
        if stop is not None:
            args.append(str(stop))
        args += (
            ["--audit-next-proofs"]
            if exact
            else ["--export", self.export, "--ept-origins"]
        )
        tick = perf_counter()
        rep = json.loads(subprocess.check_output(args))
        elapsed = perf_counter() - tick
        self.calls += 1
        self.seconds += elapsed
        if exact:
            return rep
        counts = rep["counts"]
        delivered = (
            counts["accepted"] + counts["duplicates"] + sum(counts["rejected"].values())
        )
        if delivered != len(rows):
            raise ValueError(
                f"fork accounted {delivered}/{len(rows)} supplied requests"
            )
        sha = rep["state_sha"]
        if sha not in self.cache:
            self.cache[sha] = self.target.match(read(self.export))
        return {
            "sha": sha,
            "ops": effects(rep),
            "facts": self.cache[sha],
            "origins": dict(rep["ept"]["origins"]),
            "counts": rep["counts"],
            "seconds": rep["seconds"],
            "process_seconds": elapsed,
            "schedule": [v[:3] for v in rep["schedule"]],
        }


def difference(left, right):
    """Signed, paired continuation minus Seal. Sets are reference fact identities."""
    return {
        "gained": sorted(right["facts"] - left["facts"]),
        "lost": sorted(left["facts"] - right["facts"]),
        "ops": right["ops"] - left["ops"],
        "seal_hash": left["sha"],
        "continue_hash": right["sha"],
        "seal_covered": len(left["facts"]),
        "continue_covered": len(right["facts"]),
        "seal_native_seconds": left["seconds"],
        "continue_native_seconds": right["seconds"],
        "seal_process_seconds": left["process_seconds"],
        "continue_process_seconds": right["process_seconds"],
        "same_schedule": left["schedule"] == right["schedule"],
    }


def preference(direct, terminal, proven_noop, origin_stable):
    if (
        not origin_stable
        or not direct["same_schedule"]
        or not terminal["same_schedule"]
    ):
        return None
    if direct["ops"] > 0 and terminal["gained"] and not terminal["lost"]:
        return CONTINUE
    if (
        proven_noop
        and direct["seal_hash"] == direct["continue_hash"]
        and terminal["seal_hash"] == terminal["continue_hash"]
        and not direct["ops"]
    ):
        return SEAL
    return None


def checkpoint_candidates(event):
    # A depleted generation allowance cannot be turned into an early-exit training label.
    return [
        (i, a)
        for i, a in enumerate(event["actions"])
        if not a["draft"] and a["mask"][CONTINUE] and a["mask"][SEAL]
    ]


def audit_shard(a, cohort, idx):
    source = (
        a.out
        / ("shuffle" if cohort == "shuffle" else "")
        / "experience"
        / f"{idx}.json"
    )
    dest = a.out / "pairs" / f"{cohort}-{idx:04d}.json.gz"
    if dest.exists():
        return
    sh = read(source)
    events = sh["history"]
    accepted = {q["token"]: q for q in sh["tape"]["requests"]}
    data = [event_requests(e, accepted) for e in events]
    allq = [q for qs, _ in data for q in qs]
    if len({q["token"] for q in allq}) != len(allq):
        raise ValueError("duplicate paid ID")
    records = []
    actions = []
    with TemporaryDirectory() as temp:
        f = Forks(a, idx, Path(temp), sh["tape"]["program_sha256"])
        original = f.call(allq)
        if original["sha"] != events[-1]["exit"]["base_hash"] or original["counts"][
            "accepted"
        ] != len(accepted):
            raise ValueError("raw signed tape fails to reproduce native endpoint")
        for e, (qs, cell_rows) in zip(events, data, strict=True):
            run = e["run"]
            prior = [q for q in allq if q["run"] < run]
            suffix = [q for q in allq if q["run"] > run]
            for c in cell_rows:
                q = c["request"]
                c["credit"] = labels(
                    c["reply"],
                    c["dirty"],
                    c["dirty"],
                    original["origins"].get(q["token"], 0),
                    False,
                )
            entry = {
                "run": run,
                "stage": e["stage"],
                "epoch": e["epoch"],
                "rules": e["rules"],
                "policy": sh["behavior"],
                "reason": e["reason"],
                "cell_credit": cell_rows,
                "control_events": e["actions"],
                "exit_audit": e["exit"],
            }
            actions.append(entry)
            if not checkpoint_candidates(e):
                continue
            # Static published snapshot is identical across nonempty Submits; admission
            # history is restored separately at each checkpoint.
            exact = f.call(prior, run - 1, True)
            for i, act in checkpoint_candidates(e):
                issued = act["sent"]
                base = prior + qs[:issued]
                current = f.call(base, run)
                end = f.call(base + suffix)
                checkpoint = {
                    "run": run,
                    "action_index": i,
                    "paid_prefix": issued,
                    "state": digest(
                        [
                            sh["tape"]["program_sha256"],
                            e["stage"],
                            e["epoch"],
                            prior,
                            qs[:issued],
                            e["actions"][:i]
                            and [
                                (v["action"], v.get("tokens", []))
                                for v in e["actions"][:i]
                            ],
                        ]
                    ),
                    "observed": act["action"],
                }
                trials = []
                # A complete observed batch may span multiple pages.
                next_submit = next(
                    (
                        j
                        for j in range(i, len(e["actions"]))
                        if e["actions"][j]["action"] == SUBMIT
                    ),
                    None,
                )
                if next_submit is not None:
                    s = e["actions"][next_submit]
                    batch = qs[issued : issued + len(s["ids"])]
                    trials.append(
                        (
                            "frozen_neural",
                            batch,
                            all(v in (1, 2) for v in s["status"]),
                            sum(
                                row.get("generation_seconds", 0)
                                for row in e["actions"][i:next_submit]
                            ),
                            s["submit_seconds"],
                            sum(
                                row["action"] == CONTINUE
                                for row in e["actions"][i:next_submit]
                            ),
                        )
                    )
                # Training-only concrete alternative. Subsample deterministically, and
                # retain a separate provenance so effect witnesses are not called discoveries.
                seen = {
                    (q["rule"], json.dumps(q["parents"], sort_keys=True))
                    for q in qs[:issued]
                }
                opts = [
                    q
                    for q in exact
                    if (q["rule"], json.dumps(q["parents"], sort_keys=True)) not in seen
                ]
                if opts:
                    start = (idx + run + i) % len(opts)
                    opts = (opts[start:] + opts[:start])[: a.cap]
                    fresh = max((q["token"] for q in allq), default=0) + 1
                    trials.append(
                        (
                            "offline_teacher",
                            [dict(q, token=fresh + k) for k, q in enumerate(opts)],
                            False,
                            None,
                            None,
                            1,
                        )
                    )
                for origin, batch, noop, gensec, subsec, pages in trials:
                    now = f.call(base + batch, run)
                    then = f.call(base + batch + suffix)
                    direct, terminal = difference(current, now), difference(end, then)
                    stable = (
                        all(
                            current["origins"].get(q["token"], 0)
                            == now["origins"].get(q["token"], 0)
                            for q in base
                        )
                        and sum(now["origins"].get(q["token"], 0) for q in batch)
                        == direct["ops"]
                    )
                    pref = preference(direct, terminal, noop, stable)
                    rec = dict(
                        **checkpoint,
                        origin=origin,
                        batch=batch,
                        pages=pages,
                        paid=len(batch),
                        held_suffix_paid=len(suffix),
                        direct=direct,
                        terminal=terminal,
                        stable=stable,
                        target=pref,
                        gen_seconds=gensec,
                        submit_seconds=subsec,
                    )
                    # Equal-spend test: move precisely the same named requests to the
                    # next source occurrence scheduling all their opcodes. Identical
                    # later tape, including requests that may now fail verification.
                    if pref == CONTINUE:
                        rules = {q["rule"] for q in batch}
                        next_run = next(
                            (
                                v["run"]
                                for v in events
                                if v["run"] > run
                                and rules.issubset({r for r, _, _ in v["rules"]})
                            ),
                            None,
                        )
                        if next_run:
                            delayed = (
                                [q for q in suffix if q["run"] < next_run]
                                + [dict(q, run=next_run) for q in batch]
                                + [q for q in suffix if q["run"] >= next_run]
                            )
                            later = f.call(base + delayed)
                            rec["delay"] = {
                                "run": next_run,
                                "delta": difference(later, then),
                                "credited_ops": sum(
                                    later["origins"].get(q["token"], 0) for q in batch
                                ),
                            }
                    records.append(rec)
        obj = {
            "program": sh["tape"]["program_sha256"],
            "idx": idx,
            "signature": sh["signature"],
            "cohort": cohort,
            "reference_facts": len(f.target.gold),
            "windows": actions,
            "pairs": records,
            "audit_calls": f.calls,
            "audit_wall": f.seconds,
        }
    tmp = dest.with_suffix(".tmp")
    with gzip.open(tmp, "wt", compresslevel=1) as out:
        json.dump(obj, out, separators=(",", ":"))
    tmp.replace(dest)


if __name__ == "__main__":
    p = arguments()
    p.add_argument("--cohort", choices=["neural", "shuffle"], required=True)
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    (a.out / "pairs").mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        for i, _ in enumerate(
            pool.map(lambda idx: audit_shard(a, a.cohort, idx), range(a.programs))
        ):
            if i % 10 == 0:
                print(a.cohort, i, flush=True)
