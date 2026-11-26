"""Attach choice-local credit and test publication and window loss with native forks."""

import gzip
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

from control_credit_pairs import Forks, digest, event_requests
from discovery_states import read
from execution_control import CONTINUE, SEAL, SUBMIT
from execution_control_data import arguments


def target(pairs):
    # Evidence against a specific wasteful continuation may coexist with a
    # productive alternative. Do not teach Seal in that situation.
    if any(p["target"] == CONTINUE for p in pairs):
        return CONTINUE
    if any(p["target"] == SEAL for p in pairs) and all(
        p["target"] == SEAL for p in pairs
    ):
        return SEAL
    return None


def publication_probe(f, rows, events, accepted, origins):
    """Verify the exact named consumer with and without its particular producer."""
    found = []
    for w in events:
        r = w["run"]
        for consumer in rows:
            if consumer["run"] != r + 1 or not origins.get(consumer["token"], 0):
                continue
            owners = {p["address"]["token"] for p in consumer["parents"]}
            parent = next(
                (
                    q
                    for q in rows
                    if q["run"] == r and q["token"] in owners and q["token"] in accepted
                ),
                None,
            )
            if parent is None:
                continue
            base = [q for q in rows if q["run"] <= r]
            after = f.call(base + [consumer], r + 1)
            without = f.call([q for q in base if q != parent] + [consumer], r + 1)
            uid = consumer["token"]
            if not after["origins"].get(uid, 0) or without["origins"].get(uid, 0):
                continue
            early = None
            if consumer["rule"] in {rid for rid, _, _ in w["rules"]}:
                rep = f.call(base + [dict(consumer, run=r)], r)
                early = rep["origins"].get(uid, 0)
                if early:
                    continue
            found.append(
                {
                    "run": r,
                    "parent": parent,
                    "consumer": consumer,
                    "early_ops": early,
                    "prepublication": "requires_next_ruleset"
                    if early is None
                    else "no_effect_before_publication",
                    "after_ops": after["origins"][uid],
                    "without_producer_ops": 0,
                }
            )
            break
    return found


def attach(a, cohort, idx):
    name = f"{cohort}-{idx:04d}.json.gz"
    dest = a.out / "ledger" / name
    if dest.exists():
        return
    with gzip.open(a.out / "pairs" / name) as inp:
        sh = json.load(inp)
    raw = read(
        a.out
        / ("shuffle" if cohort == "shuffle" else "")
        / "experience"
        / f"{idx}.json"
    )
    accepted = {q["token"]: q for q in raw["tape"]["requests"]}
    rows = [q for e in raw["history"] for q in event_requests(e, accepted)[0]]
    with TemporaryDirectory() as tmp:
        f = Forks(a, idx, Path(tmp), sh["program"])
        live = f.call(rows)
        sh["publication_probes"] = publication_probe(
            f, rows, sh["windows"], accepted, live["origins"]
        )
        for w in sh["windows"]:
            r = w["run"]
            for i, act in enumerate(w["control_events"]):
                peers = [
                    p for p in sh["pairs"] if p["run"] == r and p["action_index"] == i
                ]
                credit = {}
                state = digest(
                    [
                        sh["program"],
                        w["stage"],
                        w["epoch"],
                        rows_before(rows, r, act["sent"]),
                        act["x"],
                        act["mask"],
                    ]
                )
                for p in peers:
                    p["state"] = state
                pref = target(peers)
                if pref == SEAL and w["exit_audit"]["credited"]:
                    # Even the later drained exit had a witnessed omission.
                    pref = None
                if pref is not None:
                    credit["timing"] = [
                        "control_at_snapshot",
                        pref,
                        "native_paired_terminal",
                    ]
                if act["action"] == SUBMIT and (act["ops"] or act["later_used"]):
                    credit["contribution"] = [
                        "submitted_batch",
                        act["ops"],
                        "signed_origins",
                    ]
                    if act["later_used"]:
                        credit["dependency"] = [
                            "issued_batch_named_uses",
                            act["later_used"],
                            "later_effective_consumer",
                        ]
                if act["action"] == SEAL and w["exit_audit"]["credited"]:
                    credit["omission"] = [
                        "exit_decision",
                        sum(g for _, g in w["exit_audit"]["credited"]),
                        "native_exit_fork",
                    ]
                cost = {
                    k: act[k]
                    for k in ("generated", "generation_seconds", "submit_seconds")
                    if k in act
                }
                credit["cost"] = ["control_action", cost, "observed_cost"]
                act.update(state=state, credit=credit)
            w["publication_probe_ids"] = [
                i for i, p in enumerate(sh["publication_probes"]) if p["run"] == r
            ]
        sh["audit_calls"] += f.calls
        sh["audit_wall"] += f.seconds
    tmp = dest.with_suffix(".tmp")
    with gzip.open(tmp, "wt", compresslevel=1) as out:
        json.dump(sh, out, separators=(",", ":"))
    tmp.replace(dest)


def rows_before(rows, r, n):
    return [q for q in rows if q["run"] < r] + [q for q in rows if q["run"] == r][:n]


if __name__ == "__main__":
    p = arguments()
    p.add_argument("--cohort", choices=["shuffle", "neural"], required=True)
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    (a.out / "ledger").mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        for i, _ in enumerate(
            pool.map(lambda idx: attach(a, a.cohort, idx), range(a.programs))
        ):
            if i % 20 == 0:
                print("ledger", a.cohort, i, flush=True)
