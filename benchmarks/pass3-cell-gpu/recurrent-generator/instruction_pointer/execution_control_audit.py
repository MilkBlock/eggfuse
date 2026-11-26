"""Post-run diagnostics. Never imported by the independent rollout."""

import json
import subprocess
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from discovery_score import packet, token, write_csv
from discovery_states import read, save
from discrete_cells import from_q
from execution_control_data import arguments, effects, exit_audit
from recursive_train import folder


def compare(binary, program, tape, rows, run, additional):
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "fork.json"

        def fork(q):
            save(
                path,
                dict(
                    tape,
                    requests=q,
                    repair_events=[e for e in tape["repair_events"] if e["run"] <= run],
                ),
            )
            rep = json.loads(
                subprocess.check_output(
                    [
                        binary,
                        "replay",
                        program,
                        path,
                        "audit",
                        str(run),
                        "--ept-origins",
                    ]
                )
            )
            return rep

        early, late = fork(rows), fork(rows + additional)
        b, a = (dict(x["ept"]["origins"]) for x in (early, late))
        return {
            "delta": effects(late) - effects(early),
            "accepted": late["counts"]["accepted"] - early["counts"]["accepted"],
            "rejection": dict(
                Counter(late["counts"]["rejected"])
                - Counter(early["counts"]["rejected"])
            ),
            "stable": all(b.get(q["token"], 0) == a.get(q["token"], 0) for q in rows),
            "base": early["state_sha"],
            "after": late["state_sha"],
        }


def live_boundary(a, program, tape, wrong, right):
    """Offline diagnostic; only this controlled probe receives the named oracle replacement."""
    from ccp_v01 import Client, read_repairs
    from cell_transaction import STATUS, memory_frame
    from credit_scale_buffer import submit
    from discrete_draft import Cell

    proc = subprocess.Popen(
        [a.runtime_binary, "online-ccp-v0.1", program, "-", "audit", "--ept"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    client = Client(proc, 256, tape["program_sha256"])
    ids = {}
    log = []
    try:
        for expected in range(1, 5):
            header = json.loads(proc.stdout.readline())
            pub = memory_frame(proc.stdout, header)
            read_repairs(proc.stdout, header)
            assert (
                header["run"] == expected
                and header["committed_through_run"] == expected - 1
            )
            client.run, client.epoch = expected, header["epoch"]
            entry = {
                "run": expected,
                "epoch": client.epoch,
                "committed": expected - 1,
                "published": len(pub[0]),
                "submits": [],
            }
            log.append(entry)
            if expected == 4:
                break
            proposals = (
                [q for q in tape["requests"] if q["run"] == expected]
                if expected < 3
                else [wrong, right]
            )
            for q in proposals:
                c = from_q(q)
                named = Cell(c.rule, tuple((ids.get(t, t), o, v) for t, o, v in c.refs))
                response = submit(client, [named], 256)[0]
                if response[1] == 0:
                    ids[q["token"]] = response[0]
                entry["submits"].append(
                    [c.rule, response[0], STATUS[response[1]], client.epoch]
                )
            client.seal()
        assert [v[2] for v in log[2]["submits"]] == ["binding", "accepted"]
        assert log[1]["submits"][0][0:3:2] == [574, "accepted"]
        return log
    finally:
        proc.kill()
        proc.wait()
        client.close()
        proc.stdin.close()
        proc.stdout.close()


def pinned_terminal(a):
    """Measure the terminal consequence with an identical remaining request tape."""
    from recursive_coverage import Target, snapshot

    case = "sum-divisors"
    d = folder(a.data, case)
    dest = a.out / "independent" / case / "C-536-0"
    tape = read(dest / (case + "-stream-multi") / "issued.json")
    if any(q["run"] >= 2 for q in tape["requests"]):
        raise ValueError(
            "this archived no-later-requests diagnostic requires a new fork design"
        )
    q = {
        "run": 2,
        "rule": 574,
        "parents": [],
        "token": max(x["token"] for x in tape["requests"]) + 1,
    }
    with TemporaryDirectory() as tmp:
        p = Path(tmp) / "tape.json"
        f = Path(tmp) / "state.json"
        target = Target(
            read(d / "program.json"), snapshot(a.data, d, "reference", "-", None, f)[0]
        )
        base = target.match(read(dest / (case + "-stream-multi") / "state.json"))
        save(p, dict(tape, requests=tape["requests"] + [q]))
        rep = json.loads(
            subprocess.check_output(
                [
                    a.runtime_binary,
                    "replay",
                    d / "program.json",
                    p,
                    "audit",
                    "--export",
                    f,
                    "--ept",
                ]
            )
        )
        after = target.match(read(f))
        return {
            "rule": 574,
            "base_hash": read(dest / "result.json")["sha"],
            "fork_hash": rep["state_sha"],
            "runs": rep["runs"],
            "paid_increment": 1,
            "gained": sorted(after - base),
            "lost": sorted(base - after),
        }


def regression(a):
    case = "sum-divisors"
    program = folder(a.data, case) / "program.json"
    tape = read(
        a.out
        / "independent"
        / case
        / "A-536-0"
        / (case + "-stream-multi")
        / "issued.json"
    )
    # Pinned autonomous prefix. Change just the request under study.
    rows = tape["requests"]
    zero = next(q for q in rows if q["rule"] == 574 and q["run"] == 2)
    prefix = [q for q in rows if q["run"] < 2]
    r = {
        "574_open": compare(a.runtime_binary, program, tape, prefix, 2, [zero]),
        "574_late": compare(
            a.runtime_binary, program, tape, prefix, 5, [dict(zero, run=5)]
        ),
    }
    sample = next(
        s
        for s in read(Path(__file__).parent / "run-recall/fine-credit/egg-audit.json")[
            "samples"
        ]
        if s["rule"] == 575 and s["run"] == 3
    )
    pair = sample["verified"][0]
    prefix = [q for q in rows if q["run"] < 3]
    uid = max(q["token"] for q in prefix) + 1
    bad = packet(token(pair["wrong"]), 3, uid)
    good = packet(token(pair["replacement"]), 3, uid + 1)
    r["575_wrong"] = compare(a.runtime_binary, program, tape, prefix, 3, [bad])
    r["575_continue"] = compare(
        a.runtime_binary, program, tape, prefix + [bad], 3, [good]
    )
    r["575_early_seal"] = compare(a.runtime_binary, program, tape, prefix, 3, [])
    assert (
        r["574_open"]["delta"] > 0
        and r["574_late"]["rejection"].get("untriggered_rule") == 1
    )
    assert (
        r["575_wrong"]["rejection"].get("binding") == 1
        and r["575_continue"]["delta"] > 0
    )
    r["575_live"] = live_boundary(a, program, tape, bad, good)
    r["574_terminal"] = pinned_terminal(a)
    return r


def report(a):
    out = a.out / "report"
    out.mkdir(exist_ok=True)
    save(out / "regressions.json", regression(a))
    summaries = []
    audits = []
    continued = []
    factsets = []
    publication = []
    for file in sorted((a.out / "independent").glob("*/*/result.json")):
        v = read(file)
        case = v["case"]
        history = read(file.parent / "history.json")
        tape = read(file.parent / (case + "-stream-multi") / "issued.json")
        # A later actual accepted consumer quoted an output owned by that request.
        # This is observed use, not a proof of unique counterfactual unlocking.
        born = {q["token"]: q["run"] for q in tape["requests"]}
        consumers = Counter()
        for q in tape["requests"]:
            owner_runs = {
                born[p["address"]["token"]]
                for p in q["parents"]
                if p["address"]["token"] in born
                and born[p["address"]["token"]] < q["run"]
            }
            consumers.update(owner_runs)
        summaries.append(
            {k: val for k, val in v.items() if k not in ("facts", "exits", "device")}
            | v["exits"]
            | {"accepted": len(tape["requests"])}
        )
        factsets.append(
            {k: v[k] for k in ("case", "arm", "seed", "block", "facts", "sha")}
        )
        if v["block"] or v["seed"] != 536:
            continue
        for p in history["publications"][1:]:
            publication.append(
                dict(
                    case=case,
                    arm=v["arm"],
                    **p,
                    observed_later_consumers=consumers[p["run"]],
                )
            )
        if v["arm"] not in ("A", "B", "C", "C-shuffle"):
            continue
        windows = history["windows"]
        n = len(windows)
        program = folder(a.data, case) / "program.json"
        for r in sorted({i for i in (2, 3, n // 2, n) if 0 < i <= n}):
            e = exit_audit(a.runtime_binary, program, tape, r)
            audits.append(
                dict(case=case, arm=v["arm"], reason=windows[r - 1]["reason"], **e)
            )
        # Choose by presence of two actual submits, before examining effect/origin labels.
        for w in (x for x in windows if x["submits"] >= 2 and x["actions"]):
            r = w["run"]
            cut = next(act["ids"][-1] for act in w["actions"] if act["action"] == 1)
            issued = [q for q in tape["requests"] if q["run"] <= r]
            deferred = [q for q in issued if q["run"] == r and q["token"] > cut]
            if not deferred:
                continue
            base = [q for q in issued if q["token"] <= cut]
            continued.append(
                dict(
                    case=case,
                    arm=v["arm"],
                    run=r,
                    **compare(a.runtime_binary, program, tape, base, r, deferred),
                )
            )
            break
    schedules = {}
    for case in a.cases:
        tree = read(folder(a.data, case) / "program.json")["recipe"]["control"]
        kinds = Counter()

        def walk(node, kinds=kinds):
            if isinstance(node, list):
                for child in node:
                    walk(child)
            else:
                for op in ("sequence", "repeat", "saturate", "run"):
                    if op in node:
                        kinds[op] += 1
                        if op == "repeat":
                            walk(node["body"])
                        elif op in ("sequence", "saturate"):
                            walk(node[op])
                        break
                else:
                    raise ValueError(f"unrecognized Recipe control {node}")

        walk(tree)
        schedules[case] = kinds
    save(out / "schedules.json", schedules)
    from statistics import median

    aggregated = []
    for case, arm in sorted({(v["case"], v["arm"]) for v in summaries}):
        runs = [v for v in summaries if (v["case"], v["arm"]) == (case, arm)]
        distinct = [v for v in runs if not v["block"]]
        for v in runs:
            orig = next(i for i in distinct if i["seed"] == v["seed"])
            assert (v["sha"], v["paid"], v["ops"]) == (
                orig["sha"],
                orig["paid"],
                orig["ops"],
            )
        aggregated.append(
            {
                "case": case,
                "arm": arm,
                "runs": len(runs),
                "coverage": sum(v["coverage"] for v in distinct) / len(distinct),
                "ept": sum(v["ops"] for v in distinct)
                / sum(v["paid"] for v in distinct),
                "eps_median": median(v["eps"] for v in runs),
                "cold_seconds_min": min(v["seconds"] for v in runs),
                "cold_seconds_max": max(v["seconds"] for v in runs),
            }
        )
    write_csv(out / "summary.csv", aggregated)
    write_csv(out / "runs.csv", summaries)
    write_csv(out / "publication.csv", publication)
    save(out / "exit-forks.json", audits)
    save(out / "continuations.json", continued)
    save(out / "facts.json", factsets)


if __name__ == "__main__":
    report(arguments().parse_args())
