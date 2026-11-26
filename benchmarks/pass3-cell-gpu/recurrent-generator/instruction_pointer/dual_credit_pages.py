"""Attach pre-page teacher and policy marginals to fixed-exit rollout shards, offline."""

import gzip
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from itertools import groupby
from pathlib import Path
from tempfile import TemporaryDirectory

from control_credit_pairs import Forks, digest
from credit_scale_fit import load_shard
from discovery_score import packet, token
from discovery_states import cli
from dual_credit import marginal
from execution_control import CONTINUE, SEAL, SUBMIT
from fine_credit import experiences


def audit_page_shard(a, source):
    sh = load_shard(source)
    rows = []
    events = []
    with TemporaryDirectory() as tmp:
        f = Forks(a, sh["idx"], Path(tmp), sh["program"])
        for event in sh["events"]:
            frame = event["frame"]
            run = frame["run"]
            before = f.call(rows, run - 1)
            if before["sha"] != event["semantic_state"]:
                raise ValueError(
                    "offline prefix does not reproduce the published state"
                )
            base = f.call(rows, run)
            exact = f.call(rows, run - 1, exact=True)
            first = max((q["token"] for q in rows), default=0) + 1
            teacher = [dict(q, token=first + i) for i, q in enumerate(exact)]
            trial = f.call(rows + teacher, run) if teacher else base
            gains = marginal(base, trial, rows, teacher)
            paid = [
                packet(token(c), run, reply[0])
                for c, reply in zip(event["generated"], event["response"], strict=True)
            ]
            actual = f.call(rows + paid, run) if paid else base
            received = marginal(base, actual, rows, paid)
            if received is not None and received != event["signed_gain"]:
                raise ValueError("observed and forked native origins differ")
            state = digest(
                [
                    sh["program"],
                    run,
                    frame["epoch"],
                    event["semantic_state"],
                    digest(rows),
                    event["context"],
                ]
            )
            events.append(
                dict(
                    state=state,
                    run=run,
                    epoch=frame["epoch"],
                    teacher_witnesses=None
                    if gains is None
                    else [[q, g] for q, g in zip(teacher, gains, strict=True) if g],
                    teacher_ops=None if gains is None else sum(gains),
                    realized_ops=None if received is None else sum(received),
                    paid=len(paid),
                    submit_seconds=event["issue_seconds"],
                    residual_omission_ops=sum(g for _, g in event["omitted"])
                    if event["stable"]
                    else None,
                )
            )
            rows.extend(paid)
            rows.extend(
                packet(token(c), run, r[0])
                for c, r in zip(
                    event["assisted"], event["assisted_response"], strict=True
                )
            )
    result = dict(
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        policy=sh["checkpoint"],
        signature=sh["signature"],
        events=events,
        teacher_source="isolated_exact_named_requests_from_pre_page_prefix",
        realized_source="observed_policy_receipts_and_reconciled_native_origins",
        exit_policy="fixed",
        control_preference=None,
    )
    dest = a.out / "page-dual" / source.name
    tmp = dest.with_suffix(".tmp")
    with gzip.open(tmp, "wt", compresslevel=1) as fp:
        json.dump(result, fp, separators=(",", ":"))
    tmp.replace(dest)


def records(source, credit_path, dual_path):
    """Stream actual actions and fine-grained Cell rows. All witness fields are offline."""
    sh = load_shard(source)
    audit = load_shard(dual_path)
    if hashlib.sha256(source.read_bytes()).hexdigest() != audit["source_sha256"]:
        raise ValueError("teacher and policy sidecar belongs to another rollout")
    groups = iter(groupby(experiences(source, credit_path), key=lambda r: r["run"]))
    current = next(groups, None)
    for event, evidence in zip(sh["events"], audit["events"], strict=True):
        run = event["frame"]["run"]
        if run != evidence["run"] or event["frame"]["epoch"] != evidence["epoch"]:
            raise ValueError("different decision window")
        state = evidence["state"]
        common = dict(
            run=run,
            page_state=state,
            policy=sh["checkpoint"],
            policy_branch=sh["branch"],
            control_preference=None,
        )
        yield dict(
            **common,
            kind="control",
            action=CONTINUE,
            state=state,
            teacher_witnesses=evidence["teacher_witnesses"],
            teacher_source=audit["teacher_source"],
            realized_ops=evidence["realized_ops"],
            realized_source=audit["realized_source"],
            realized_scope="page_generated_then_submitted_in_same_window",
            budget=sh["slot_budget"],
            paid=evidence["paid"],
            masks={
                "positive_potential": bool(evidence["teacher_witnesses"]),
                "realization": evidence["realized_ops"] is not None,
                "control_preference": False,
            },
        )
        # Physical CCP submissions are chunks of 128 in the frozen Lane.
        for start in range(0, len(event["response"]), 128):
            replies = event["response"][start : start + 128]
            draft = event["generated"][start:]
            yield dict(
                **common,
                kind="control",
                action=SUBMIT,
                state=digest([state, "submit", event["response"][:start], draft]),
                responses=replies,
                native_gains=event["signed_gain"][start : start + 128],
                paid=len(replies),
                source="observed_submit_signed_origins",
            )
        if current is not None and current[0] == run:
            for c in current[1]:
                yield dict(
                    c,
                    kind="cell" if c["request"] is not None else "omission",
                    page_state=state,
                )
            current = next(groups, None)
        yield dict(
            **common,
            kind="control",
            action=SEAL,
            state=digest(
                [state, "seal", event["response"], event["assisted_response"]]
            ),
            source="observed_fixed_exit",
            teacher_assisted=len(event["assisted_response"]),
            masks={"control_preference": False},
        )
    if current is not None:
        raise ValueError("unmatched cell credit at end of rollout")


if __name__ == "__main__":
    p = cli()
    p.add_argument("--jobs", type=int, default=4)
    a = p.parse_args()
    (a.out / "page-dual").mkdir(parents=True, exist_ok=True)
    files = sorted((a.out / "buffer").glob("*.gz"))
    with ThreadPoolExecutor(a.jobs) as pool:
        list(pool.map(lambda path: audit_page_shard(a, path), files))
