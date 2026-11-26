"""Joint offline replay interface. Features for inference never include the evidence field."""

import gzip
import json
from collections import defaultdict

from execution_control import CONTINUE, SEAL, SUBMIT


def records(shard, allocation, live=()):
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
            yield dict(
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
