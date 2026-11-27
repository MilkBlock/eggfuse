"""Post-hoc counterfactual Higher choice under the rule state, receipts and published interface."""

import json
import pickle

import torch

from cell_kv_runtime import native
from feedback_stall import folder
from int_parameters import digest
from partner_index_worlds import args
from scaling_archive import directory
from scaling_campaign import REPORT
from scaling_eval import frozen
from scaling_fit import atomic
from scaling_transitions import Replay
from state_transition_corpus import world


def recover(a, actor):
    rows = []
    for i in range(6):
        w = world(a, actor, i, False)
        pair = pickle.loads((folder(a) / f"test-{i}.pkl").read_bytes())["siblings"]
        targets = []
        for prior, verified in pair:
            [receipt] = prior["request_receipts"]
            prelude = (receipt[2], receipt[3])
            log = []
            native(
                a,
                w,
                policy=Replay([[prelude]]),
                seed=9541 + i,
                slots=6,
                receipt_log=log,
                rule_state=True,
                receipt_memory=True,
            )
            state = log[1][0]
            if (
                any(state[k] != v for k, v in prior.items())
                or tuple(log[0][2][0]) != receipt[4]
            ):
                raise ValueError("native counterfactual frame or receipt differs")
            [good] = [t for t in verified if t[0] >= w.primitives]
            targets.append((state, good))
        if targets[0][1][0] == targets[1][1][0]:
            raise ValueError("expected opposite Higher choices")
        rows.append((i, w, targets))
    return rows


def run(a):
    d = directory(a)
    out = d / "higher-counterfactual.json"
    scores = json.loads(out.read_text()) if out.exists() else {}
    n = frozen(a, "initial")[0]
    pairs = recover(a, n.actor)
    state = json.loads((d / "campaign.json").read_text())
    models = ["initial", "sweep", *state["groups"]]
    models.extend(
        sorted(p.stem for p in (REPORT / "size-controls").glob("*.json") if p.stem not in models)
    )
    for name in models:
        if name in scores:
            continue
        n = frozen(a, name)[0]
        vals = []
        for i, w, pair in pairs:
            n.prepare(w)
            for s, (tid, refs) in pair:
                m = n.state(w, s)
                ps = {
                    t: float((-n.token_loss(w, m, (t, refs))).exp())
                    for t in range(w.primitives, len(w.layouts))
                }
                others = [p for t, p in ps.items() if t != tid]
                vals.append(
                    {
                        "program": i,
                        "state": digest(s),
                        "correct_higher": tid,
                        "named_inputs": refs,
                        "full": ps[tid],
                        "family": sum(ps.values()),
                        "wins": ps[tid] > max(others),
                        "sibling_probabilities": ps,
                    }
                )
        scores[name] = vals
        atomic(out, scores)
    return scores


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        run(args())
