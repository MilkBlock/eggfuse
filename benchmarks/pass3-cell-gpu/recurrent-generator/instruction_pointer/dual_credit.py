"""Offline, same-window teacher witnesses and measured neural realization at a drained exit."""

import gzip
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

from control_credit_pairs import Forks, digest, event_requests
from discovery_score import packet, token
from discovery_states import read
from discrete_cells import from_q
from execution_control import SEAL
from execution_control_data import arguments


def marginal(base, trial, prefix, additions):
    """Credit signed origins only if old credit survives and all new credit reconciles."""
    if any(
        base["origins"].get(q["token"], 0) != trial["origins"].get(q["token"], 0)
        for q in prefix
    ):
        return None
    gains = [trial["origins"].get(q["token"], 0) for q in additions]
    if min(gains, default=0) < 0 or sum(gains) != trial["ops"] - base["ops"]:
        return None
    return gains


def compare(twin):
    left, right = twin["continue"], twin["seal"]
    if left["prefix"] != right["prefix"]:
        raise ValueError("live branches did not start at the same state")
    if len(left["pages"]) != len(right["pages"]):
        raise ValueError("unequal page budget")
    a, b = set(left["facts"]), set(right["facts"])
    return dict(
        source="live_policy_paired_terminal",
        gained=sorted(a - b),
        lost=sorted(b - a),
        continue_minus_seal_ops=left["ops"] - right["ops"],
        continue_minus_seal_seconds=left["wall"] - right["wall"],
        pages_each=len(left["pages"]),
    )


def arm_result(f, prefix, branch, run):
    page = branch["pages"][0]
    rows = [
        packet(token(t), page["run"], receipt[0])
        for t, receipt in zip(page["tokens"], page["response"], strict=True)
    ]
    base = f.call(prefix, page["run"])
    trial = f.call(prefix + rows, page["run"]) if rows else base
    gains = marginal(base, trial, prefix, rows)
    return dict(
        source="live_policy_ccp_and_signed_origin_replay",
        first_run=page["run"],
        current_window=page["run"] == run,
        requests=rows,
        response=page["response"],
        first_page_device=page["device"],
        first_page_gains=gains,
        first_page_ops=sum(gains) if gains is not None else None,
        first_page_seconds=page["gen_seconds"] + page["submit_seconds"],
        paid=sum(len(p["response"]) for p in branch["pages"]),
        generation_seconds=sum(p["gen_seconds"] for p in branch["pages"]),
        submit_seconds=sum(p["submit_seconds"] for p in branch["pages"]),
        wall=branch["wall"],
        terminal_ops=branch["ops"],
        terminal_sha=branch["sha"],
        terminal_facts=branch["facts"],
    )


def audit(a, idx):
    twins = [] if a.live_only else read(a.paired / "live" / f"{idx}.json")
    if a.additional_live:
        twins += read(a.additional_live / "live" / f"{idx}.json")
    if len({(t["cohort"], t["run"]) for t in twins}) != len(twins):
        raise ValueError("repeated live decision state")
    dest = a.out / "dual" / f"{idx:04}.json.gz"
    results = []
    if twins:
        cohort = twins[0]["cohort"]
        root = a.paired / ("shuffle" if cohort == "shuffle" else "")
        sh = read(root / "experience" / f"{idx}.json")
        accepted = {q["token"]: q for q in sh["tape"]["requests"]}
        paid = [q for w in sh["history"] for q in event_requests(w, accepted)[0]]
        windows = {w["run"]: w for w in sh["history"]}
        with TemporaryDirectory() as tmp:
            f = Forks(a, idx, Path(tmp), sh["tape"]["program_sha256"])
            for t in twins:
                r = t["run"]
                w = windows[r]
                act = w["actions"][-1]
                prior = [q for q in paid if q["run"] < r]
                current = [q for q in paid if q["run"] == r]
                prefix = prior + current
                checkpoint = t.get("checkpoint", sh["checkpoint_sha256"])
                if checkpoint != a.policy_sha:
                    raise ValueError(
                        "measured policy differs from requested checkpoint"
                    )
                if (
                    t["continue"]["pages"][0]["run"] != r
                    or t["seal"]["pages"][0]["run"] <= r
                ):
                    raise ValueError("neural page is on the wrong side of publication")
                if (
                    t["signature"] != sh["signature"]
                    or t["stage"] != w["stage"]
                    or act["action"] != SEAL
                    or act["draft"]
                    or t["paid_prefix"] != len(current)
                ):
                    raise ValueError("wrong publication or signed prefix")
                base = f.call(prefix, r)
                if base["sha"] != w["exit"]["base_hash"]:
                    raise ValueError("prefix does not reproduce archived window")
                exact = f.call(prior, r - 1, True)
                used = {from_q(q) for q in current}
                start = max((q["token"] for q in prefix), default=0) + 1
                extra = [
                    dict(q, token=start + i)
                    for i, q in enumerate(exact)
                    if from_q(q) not in used
                ]
                trial = f.call(prefix + extra, r) if extra else base
                gains = marginal(base, trial, prefix, extra)
                witnesses = (
                    None
                    if gains is None
                    else [[q, g] for q, g in zip(extra, gains, strict=True) if g]
                )
                potential = dict(
                    source="offline_native_exact_named_fork",
                    exhaustive_saturation=False,
                    audited_options=len(exact),
                    witnesses=witnesses,
                    witnessed_ops=None if gains is None else sum(gains),
                )
                delta = compare(t)
                state = digest(
                    [f.sha, w["stage"], w["epoch"], prefix, act["x"], act["mask"]]
                )
                results.append(
                    dict(
                        state=state,
                        program=f.sha,
                        signature=sh["signature"],
                        checkpoint=t.get("checkpoint", sh["checkpoint_sha256"]),
                        slots_per_page=t.get("slots_per_page", a.cap),
                        cohort=cohort,
                        run=r,
                        epoch=w["epoch"],
                        stage=w["stage"],
                        prefix=t["continue"]["prefix"],
                        teacher_potential=potential,
                        control_effect=delta,
                        policy_realization={
                            k: arm_result(f, prefix, t[k], r)
                            for k in ("continue", "seal")
                        },
                    )
                )
    tmp = dest.with_suffix(".tmp")
    with gzip.open(tmp, "wt") as fp:
        json.dump(results, fp, separators=(",", ":"))
    tmp.replace(dest)


if __name__ == "__main__":
    p = arguments()
    p.add_argument("--paired", type=Path, required=True)
    p.add_argument("--first", type=int, default=0)
    p.add_argument("--live-only", action="store_true")
    p.add_argument("--additional-live", type=Path)
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    a.policy_sha = hashlib.sha256(a.checkpoint.read_bytes()).hexdigest()
    (a.out / "dual").mkdir(exist_ok=True, parents=True)
    with ThreadPoolExecutor(a.workers) as pool:
        list(pool.map(lambda i: audit(a, i), range(a.first, a.programs)))
