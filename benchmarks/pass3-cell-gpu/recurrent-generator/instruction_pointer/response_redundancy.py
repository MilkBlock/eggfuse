"""Offline ablation of distinct committed requests with no credited effective operation."""

from collections import Counter

from boundary_inputs import native
from recursive_train import binary, read
from scaling_bake import save


def audit(data, work, program, online):
    tape = read(work / "issued.json")
    requests = tape["requests"]
    base = native(
        binary(data), "replay", program, work / "issued.json", "audit", "--ept-origins"
    )
    assert base["state_sha"] == online["state_sha"]
    credit = dict(base["ept"]["origins"])
    zero = [q for q in requests if credit.get(q["token"]) == 0]
    refs = Counter(p["address"]["token"] for q in requests for p in q["parents"])
    tests = []
    for q in zero[:4]:
        tid = q["token"]
        if refs[tid]:
            tests.append(dict(token=tid, kind="observed_consumer", tested=False))
            continue
        smaller = dict(tape, requests=[x for x in requests if x["token"] != tid])
        path = work / "leave-one-out.json"
        save(path, smaller)
        check = native(binary(data), "replay", program, path, "audit", "--ept-origins")
        comparisons = {
            k: check.get(k) == base.get(k)
            for k in ("state_sha", "schedule", "runtime_events", "runs")
        }
        comparisons["remaining_requests"] = check["counts"]["accepted"] == len(
            smaller["requests"]
        )
        comparisons["remaining_credit"] = dict(check["ept"]["origins"]) == {
            k: v for k, v in credit.items() if k != tid
        }
        tests.append(
            dict(
                token=tid,
                kind="same_final_effect" if all(comparisons.values()) else "different",
                tested=True,
                checks=comparisons,
            )
        )
    return dict(accepted=len(requests), zero_credit=len(zero), tests=tests)
