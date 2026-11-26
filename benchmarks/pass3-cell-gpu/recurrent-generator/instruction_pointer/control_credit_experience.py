"""Joint offline replay interface. Features for inference never include the evidence field."""

import gzip
import json
from collections import defaultdict

from execution_control import CONTINUE, SEAL, SUBMIT


def records(shard, allocation, live=(), *, dual=(), historical=False):
    """Privileged evidence stays out of x. Only a live policy twin can label a preference."""
    paired = {t["state"]: t for t in dual}
    if len(paired) != len(dual):
        raise ValueError("reused decision identity")
    exits = {
        p["run"]: p
        for p in live
        if p["cohort"] == shard["cohort"] and p["signature"] == shard["signature"]
    }
    by_state = defaultdict(list)
    for trial in allocation["records"]:
        by_state[trial["state"]].append(trial)
    pairs = defaultdict(list)
    for trial in shard["pairs"]:
        pairs[trial["state"]].append(trial)
    for w in shard["windows"]:
        meta = {
            "program": shard["program"],
            "run": w["run"],
            "stage": w["stage"],
            "epoch": w["epoch"],
        }
        cells = iter(w["cell_credit"])
        draft = []
        for action in w["control_events"]:
            state = action["state"]
            kind = action["action"]
            credit = dict(action["credit"])
            credit["cost"] = [
                "control_action",
                dict(action["credit"]["cost"][1], logical_control_tokens=1),
                "observed_cost",
            ]
            matches = by_state[state]
            if matches:
                prefs = {r["target"] for r in matches if r["target"] is not None}
                if len(prefs) == 1:
                    credit["allocation"] = [
                        "one_page_before_or_after_publication",
                        prefs.pop(),
                        "equal_paid_terminal_fact_sets",
                    ]
            if kind == SEAL and w["publication_probe_ids"]:
                credit["dependency"] = [
                    "published_named_producer",
                    w["publication_probe_ids"],
                    "native_delayed_consumer_and_producer_removal",
                ]
            twin = exits.get(w["run"]) if kind == SEAL else None
            if twin and bool(twin["gained"]) != bool(twin["lost"]):
                credit["live_allocation"] = [
                    "same_snapshot_three_page_budget",
                    CONTINUE if twin["gained"] else SEAL,
                    "live_ccp_terminal_fact_sets",
                ]
            fields = {}
            if not historical:
                for key in ("timing", "allocation", "omission", "live_allocation"):
                    credit.pop(key, None)
                t = paired.get(state)
                if t and (t["program"], t["run"], t["epoch"], t["stage"]) != (
                    shard["program"],
                    w["run"],
                    w["epoch"],
                    w["stage"],
                ):
                    raise ValueError("paired evidence belongs to another window")
                teacher = [p for p in pairs[state] if p["origin"] == "offline_teacher"]
                policy = [p for p in pairs[state] if p["origin"] == "frozen_neural"]
                fields = dict(
                    teacher_potential=t["teacher_potential"] if t else None,
                    policy_realization=t["policy_realization"] if t else None,
                    realization_checkpoint=t["checkpoint"] if t else None,
                    slots_per_page=t["slots_per_page"] if t else None,
                    sampled_teacher_trials=teacher,
                    observed_policy_trials=policy,
                    control_effect=t["control_effect"] if t else None,
                )
                if t and bool(t["control_effect"]["gained"]) != bool(
                    t["control_effect"]["lost"]
                ):
                    credit["realized_allocation"] = [
                        "policy_and_page_budget_only",
                        CONTINUE if t["control_effect"]["gained"] else SEAL,
                        "paired_live_terminal_fact_dominance",
                    ]
                fields["masks"] = {
                    "teacher_witness": bool(t and t["teacher_potential"]["witnesses"]),
                    "realized_continue": bool(
                        t
                        and t["policy_realization"]["continue"]["first_page_ops"]
                        is not None
                    ),
                    "realized_seal": bool(
                        t
                        and t["policy_realization"]["seal"]["first_page_ops"]
                        is not None
                    ),
                    "realized_allocation": "realized_allocation" in credit,
                }
            yield dict(
                **fields,
                **meta,
                state=state,
                kind="control",
                action=kind,
                mask=action["mask"],
                x=action["x"],
                credit=credit,
                evidence={"pairs": pairs[state], "allocation": matches, "live": twin},
            )
            if kind == CONTINUE:
                draft.extend((state, t) for t in action["tokens"])
            if kind == SUBMIT:
                for (generated, cell), uid in zip(draft, action["ids"], strict=True):
                    c = next(cells)
                    if c["request"]["token"] != uid:
                        raise ValueError("request identity differs from response")
                    yield dict(
                        **meta,
                        state=generated,
                        submitted_state=state,
                        kind="cell",
                        token=cell,
                        request=c["request"],
                        reply=c["reply"],
                        credit=c["credit"],
                    )
                draft = []
        if draft or next(cells, None) is not None:
            raise ValueError("draft and receipts do not reconcile")


def load(root, category, name):
    with gzip.open(root / category / name) as f:
        return json.load(f)
