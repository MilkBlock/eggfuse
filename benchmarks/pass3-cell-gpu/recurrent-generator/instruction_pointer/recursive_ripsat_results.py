"""Derive coverage-matched comparisons from completed independent rollouts."""
import argparse
from collections import Counter
from hashlib import sha256
from pathlib import Path
from receipt_bake import read
from protocol_experiment import dump


def summarize(store):
    output = {}
    for case in ("dot", "fact", "loopfact", "sum-divisors"):
        groups = {}
        files = sorted(store.glob(f"{case}-original-*.json"))
        if not files:
            raise ValueError(f"missing baseline for {case}")
        for origin in files:
            rep = origin.stem.rsplit("-", 1)[1]
            baseline = read(origin)
            for arm in ("original", "open", "rl"):
                x = read(store / f"{case}-{arm}-{rep}.json")
                if x["termination"] != "schedule_end" or x["runs"] != baseline["runs"]:
                    raise ValueError(f"incomplete execution for {case}/{arm}")
                w = x["work"]
                # Count each category in its own units; pointer scores are visits,
                # automatic wakes/CCP lowering are not learned action emissions.
                metrics = dict(runs=x["runs"], facts=x["facts"], reference=x["reference"],
                    coverage=x["facts"]/x["reference"], same_graph=x["state_sha"]==baseline["state_sha"],
                    signed_ops=x["signed_ops"], ept=x["ept"], paid=x["paid"], visits=w["visits"],
                    template_emissions=w["generated_templates"], terminal_choices=x["terminal_decisions"],
                    open_choices=sum(x["open_actions"].values()), contract_choices=w.get("open_contract_choices",0),
                    operand_reads=w.get("open_operand_reads",0), boundary_scores=w.get("boundary_scores",0),
                    complete_candidate_scores=w.get("complete_candidate_scores",0),
                    charged_with_decisions=x["charged_with_decisions"],
                    depth=w.get("max_abstraction_depth", int(bool(w.get("completed_deep")))),
                    direct_suffix_ops=x.get("new_suffix_operations",{}),
                    skipped_leaf_positions=w.get("open_terminal_candidates_skipped",0),
                    skipped_unary_events=w.get("open_unary_events_skipped",0),
                    open_actions=x["open_actions"],
                    open_issued={k.removeprefix("open_issued_"):v for k,v in w.items() if k.startswith("open_issued_")},
                    open_accepted={k.removeprefix("open_accepted_"):v for k,v in w.items() if k.startswith("open_accepted_")},
                    named_operands_issued=w.get("open_independent_bindings",0))
                if "open_new_bindings" in w:
                    metrics["extra_bindings_at_issue"] = w["open_new_bindings"]
                elif not w.get("open_issued_Activate", 0):
                    metrics["extra_bindings_at_issue"] = metrics["named_operands_issued"] - sum(metrics["open_issued"].values())
                else:
                    raise ValueError("cannot infer independently bound operands for projected Activate")
                group = groups.setdefault(arm, dict(metrics=metrics, wall=[], eps=[]))
                if group["metrics"] != metrics:
                    raise ValueError(f"nonreproducible work: {case}/{arm}")
                group["wall"].append(x["wall"])
                group["eps"].append(x["eps"])
        output[case] = groups
    train = [read(p) for p in store.glob("sum-train-*-*.json")]
    decisions = sum((Counter(x["open_actions"]) for x in train), Counter())
    return dict(cases=output, training_decisions=decisions, reward_fit=read(store / "training.json"),
                checkpoints={k:sha256((store/k).read_bytes()).hexdigest()
                             for k in ("wired.pt","graph.pt","recursive-rl.pt","entry-contracts.json","catalog.json")})


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("store",type=Path)
    p.add_argument("out",type=Path)
    a=p.parse_args()
    dump(a.out,summarize(a.store))
