"""Reduce native rollouts and export stable event ranks; never used by the policy."""

import argparse
import csv
import gzip
import hashlib
import json
import subprocess
from pathlib import Path
from statistics import median

import numpy as np

from cell_transaction import STATUS
from cost_profile import META
from recursive_train import folder, read

CASES = ("fact", "loopfact", "sum-divisors")
ARMS = ("base", "frozen", "rl", "oracle")
DIAGNOSTICS = ("single", "receipt-single", "receipt", "combined", "receipt-with-b", "wide")


def write(path, obj):
    path.write_text(json.dumps(obj, indent=2, allow_nan=False) + "\n")


def distribution(values):
    mid = median(values)
    return {
        "samples": values,
        "median": mid,
        "mad": median(abs(x - mid) for x in values),
        "minimum": min(values),
        "maximum": max(values),
    }


def checksum(path):
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def frozen_search(store, output, case):
    z = np.load(store / f"{case}-ledger.npz")
    meta, depth, verdict, ops, probe, batch = (
        z[k] for k in ("meta", "depth", "verdict", "ops", "prune", "batch")
    )
    scores = depth[:, :, 1].sum(axis=1)
    score_ns = depth[:, :, 4].sum(axis=1)
    order = np.argsort(-scores, kind="stable")
    accumulated = scores[order].cumsum()
    total = int(scores.sum())
    counts = {str(p): int(np.searchsorted(accumulated, total * p / 100) + 1) for p in (50, 80, 95)}
    # Native sampled alternatives can coexist with a successful request on this event.
    exact = read(store / f"{case}-exact-audit.json")
    loss = {}
    for eid, why, owner, stage, _ in exact["witnesses"]:
        if why in ("match", "off_reference") and stage:
            loss.setdefault(eid, set()).add((stage, why))
    fork_errors = {r: f["error"] for r, f in exact["runs"].items() if "error" in f}
    hits, duplicates = verdict[:, 0] > 0, verdict[:, 1] > 0

    def evidence(ix):
        classes = {
            "accepted": hits,
            "duplicate_only": ~hits & duplicates,
            "no_accepted_or_duplicate": ~hits & ~duplicates,
            "sampled_legal_rejected_terminal": probe == 1,
        }
        return {
            k: {"events": int(mask[ix].sum()), "parent_scores": int(scores[ix][mask[ix]].sum())}
            for k, mask in classes.items()
        }

    tiers = {}
    for p, n in counts.items():
        ix = order[:n]
        tiers[p] = {
            "events": n,
            "cutoff": int(scores[ix[-1]]),
            "cost": int(scores[ix].sum()),
            "classes": evidence(ix),
        }
    # Stable row id indexes the full depth/verdict ledger. The first n rows of
    # this human-readable export are exactly the corresponding concentration set.
    ranked = output / f"{case}-top95.csv.gz"
    with gzip.open(ranked, "wt", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            (
                "event",
                *META,
                "scores",
                "prefixes",
                "old_scores",
                "accepted",
                "duplicates",
                "native_requests",
                "effective_ops",
                "valid_pruned_terminal",
            )
        )
        for i in order[: counts["95"]]:
            w.writerow(
                (
                    i,
                    *meta[i],
                    scores[i],
                    depth[i, :, 0].sum() - verdict[i, -2],
                    depth[i, :, 2].sum(),
                    *verdict[i, :2],
                    verdict[i, : len(STATUS)].sum(),
                    ops[i],
                    probe[i],
                )
            )
    base = read(store / f"{case}-profile-0.json")
    if total != base["work"]["parent_candidate_scores"] or total != int(batch[:, 2].sum()):
        raise ValueError(f"ordinary search totals disagree for {case}")

    # Prefix counts in the ledger include complete paths. Remove them using the
    # actual emit-boundary population, including fully old paths.
    def stats(ix):
        s = depth[ix].sum(axis=0)
        return {
            "events": len(ix),
            "scores": int(s[:, 1].sum()),
            "prefixes": int(s[:, 0].sum() - verdict[ix, -2].sum()),
            "score_depth": s[:, 1].tolist(),
            "expanded_by_depth": s[:, 0].tolist(),
            "verified_old_score_depth": s[:, 2].tolist(),
            "threshold_failures": s[:, 3].tolist(),
            "score_seconds_apportioned": (s[:, 4] / 1e9).tolist(),
            "formed": int(verdict[ix, -2].sum()),
            "watermark_legal": int(verdict[ix, -1].sum()),
            "native_verdicts": dict(zip(STATUS, verdict[ix, : len(STATUS)].sum(axis=0).tolist())),
            "effective_operations": int(ops[ix].sum()),
        }

    groups = {}
    for i, (r, j) in enumerate(meta[:, 1:3]):
        groups.setdefault((int(r), int(j)), []).append(i)
    rows = [dict(rule=r, entry_role=j, **stats(ix)) for (r, j), ix in groups.items()]
    rows.sort(key=lambda x: -x["scores"])
    with (output / f"{case}-roles.jsonl").open("w") as stream:
        for row in rows:
            stream.write(json.dumps(row, separators=(",", ":")) + "\n")
    local = np.load(store / f"{case}-single-ledger.npz")
    if not np.array_equal(local["meta"], meta) or not np.array_equal(
        local["verdict"][:, : len(STATUS)], verdict[:, : len(STATUS)]
    ):
        raise ValueError("local intervention changed an issued verdict")
    other = local["depth"]
    delta = scores - other[:, :, 1].sum(axis=1)
    singles = [
        {
            "event": int(i),
            "key": meta[i, :6].tolist(),
            "before": int(scores[i]),
            "after": int(scores[i] - delta[i]),
            "before_prefixes": int(depth[i, :, 0].sum() - verdict[i, -2]),
            "after_prefixes": int(other[i, :, 0].sum() - local_formed),
        }
        for i, local_formed in zip(np.flatnonzero(delta), local["verdict"][delta != 0, -2])
    ]
    loss_stats = {}
    for stage in ("bucket", "prefix", "terminal"):
        for why in ("match", "off_reference"):
            ids = [e for e, ls in loss.items() if (stage, why) in ls]
            loss_stats[f"{stage}_{why}"] = {"events": len(ids), "parent_scores": int(scores[ids].sum())}
    dep = read(store / f"{case}-dependencies.json")
    examples = {row[0]: row[1] for row in dep.pop("examples")}
    by_time = {}
    for event in order[: counts["95"]]:
        if event in examples:
            n = examples[event]
            group = "named_wiring" if not n else "one_external" if n == 1 else "multiple_external"
        elif probe[event] == 1:
            group = "valid_pruned_witness"
        else:
            fork = exact["runs"][str(meta[event, 0])]
            group = (
                "fork_failed"
                if "error" in fork
                else "exact_fork_emitted_no_rule_binding"
                if not fork["rules"].get(str(meta[event, 1]), 0)
                else "unresolved_no_named_witness"
            )
        by_time[group] = by_time.get(group, 0.0) + score_ns[event] / 1e9

    def time_tiers(metric):
        rank = np.argsort(-metric, kind="stable")
        return {
            str(p): int(np.searchsorted(metric[rank].cumsum(), metric.sum() * p / 100) + 1)
            for p in (50, 80, 95)
        }

    dep["apportioned_pointer_seconds_high95_by_witness"] = by_time
    return {
        "total": stats(np.arange(len(meta))),
        "classes": evidence(np.arange(len(meta))),
        "all_visits": base["work"]["visits"],
        "aux_visits": base["work"]["visits"] - total,
        "batches": len(batch),
        "batch_seconds": float(sum(batch[:, 0])),
        "tiers": tiers,
        "apportioned_pointer_time_event_counts": time_tiers(score_ns),
        "exact_dispatch_wall_batch_counts": time_tiers(batch[:, 0]),
        "threshold_probed": int((probe >= 0).sum()),
        "native_fork_runs": len(exact["runs"]),
        "fork_errors": fork_errors,
        "ledger_sha256": checksum(store / f"{case}-ledger.npz"),
        "witnessed_path_losses": loss_stats,
        "dependency_audit": dep,
        "single_regions": singles,
    }


def compact(row, arm):
    w = row["work"]
    oracle = arm in ("oracle", "wide", "single", "combined", "receipt", "receipt-single")
    actions = row["open_actions"]
    oracular = sum(
        n
        for k, n in actions.items()
        if (oracle and k.startswith(("Cost", "Evidence")))
        or (arm == "receipt-with-b" and k.startswith("Evidence"))
    )
    proofs = w["generated_proofs"]
    neural_controls = (
        row["terminal_decisions"] + sum(actions.values()) - oracular + w.get("open_contract_choices", 0)
    )
    keys = (
        "visits",
        "parent_candidate_scores",
        "complete_candidate_scores",
        "expanded_prefixes",
        "formed_paths",
        "root_state_updates",
        "template_branch_scores",
        "generated_templates",
        "woken_templates",
        "generated_proofs",
        "lowered_steps",
        "replaced_requests",
        "index_writes",
        "index_removes",
        "index_port_reads",
        "source_port_reads",
        "named_parent_reads",
        "interface_reads",
        "query_field_reads",
        "posting_index_reads",
        "receipt_position_probes",
        "open_partner_scores",
        "open_operand_reads",
        "boundary_scores",
        "open_independent_bindings",
        "open_new_bindings",
    )
    counters = {k: w[k] for k in keys if k in w}
    counters.update(
        {k: v for k, v in w.items() if k.startswith(("cost_", "oracle_", "evidence_", "structure_"))}
    )
    return {
        "runs": row["runs"],
        "facts": row["facts"],
        "reference": row["reference"],
        "state_sha": row["state_sha"],
        "reference_endpoint": row["exact_endpoint"],
        "effective_ops": row["signed_ops"],
        "committed_primitive_applications": row["committed_tokens"],
        "neural_template_tokens": w["generated_templates"],
        "neural_ordinary_proposals": proofs,
        "neural_control_tokens": neural_controls,
        "neural_emissions": proofs + w["generated_templates"] + neural_controls,
        "oracle_controls": oracular,
        "neural_dynamic_partner_selections": w.get("open_operand_reads", 0),
        "ccp_requests": row["paid"],
        "ccprows_plus_controls": row["charged_with_decisions"],
        "synchronizations": row["synchronizations"],
        "ept": row["ept"],
        "eps": row["eps"],
        "wall": row["wall"],
        "setup": row["setup_seconds"],
        "cold_online": (row["wall"] + row["setup_seconds"] + row["runtime_setup_seconds"])
        if "runtime_setup_seconds" in row
        else None,
        "controls": actions,
        "verdicts": row["verdicts"],
        "additional_suffix_ops": row.get("new_suffix_operations", {}),
        "counters": counters,
        "cost_seconds": {k: v for k, v in w.items() if k.endswith("_seconds")},
        "boundaries": row.get("boundary_hashes"),
        "region_receipts": [x for x in row.get("structures", []) if x.get("mode") == "Evidence"],
    }


def rollouts(store, cases):
    out = {}
    for case in cases:
        groups = {}
        for arm in ARMS + DIAGNOSTICS:
            paths = sorted(store.glob(f"{case}-{arm}-[0-9].json"))
            if not paths:
                continue
            rows = [compact(read(p), arm) for p in paths]
            if (
                len({(r["facts"], r["state_sha"], r["ccp_requests"], r["counters"]["visits"]) for r in rows})
                != 1
            ):
                raise ValueError(f"nondeterministic work in {case}/{arm}")
            groups[arm] = {
                "rows": rows,
                "seconds": distribution([r["wall"] for r in rows]),
                "eps": distribution([r["eps"] for r in rows]),
            }
            if arm != "base" and "base" in groups:
                base = groups["base"]["rows"]
                if arm in ARMS:
                    groups[arm]["paired_online_seconds_saved"] = distribution(
                        [b["wall"] - r["wall"] for b, r in zip(base, rows)]
                    )
                reference = next((b["boundaries"] for b in base if b["boundaries"]), None)
                checks = [(reference, r["boundaries"]) for r in rows if reference and r["boundaries"]]
                groups[arm]["per_run_compared"] = [{k: a[k] == b[k] for k in a} for a, b in checks]
        out[case] = groups
    return out


def native_work(data, store, executable):
    result = {}
    for case in CASES:
        episodes = {}
        for arm, suffix in (("base", ""), ("aux", "-aux"), ("receipt-with-b", "-receipt-with-b")):
            tape = store / f"{case}{suffix}-issued.json"
            if not tape.is_file():
                continue
            measured = read(store / f"{case}-{arm}-0.json")
            report = json.loads(
                subprocess.check_output(
                    [
                        executable,
                        "replay",
                        folder(data, case) / "program.json",
                        tape,
                        "audit",
                        "--ept-origins",
                    ]
                )
            )
            work = report["primitive_work"]
            if (
                report["state_sha"] != measured["state_sha"]
                or work["committed_rhs"] != measured["committed_tokens"]
            ):
                raise ValueError(f"Native operation audit diverged on {case}/{arm}")
            ept = report["ept"]
            effective = sum(ept["signed_external"]) + sum(ept["signed_internal"])
            if effective != measured["signed_ops"]:
                raise ValueError(f"Native effective ledger diverged on {case}/{arm}")
            episodes[arm] = {
                "work": work,
                "ept_ledger": ept["ledger_sha256"],
                "effective_ops": effective,
                "state_sha": report["state_sha"],
                "signed_by_kind": dict(zip(ept["kinds"], ept["signed_external"])),
                "uncredited_by_kind": dict(zip(ept["kinds"], ept["uncredited"])),
            }
        result[case] = episodes
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("store", type=Path)
    p.add_argument("dest", type=Path)
    p.add_argument("task", choices=["profile", "rollouts", "primitive"])
    p.add_argument("--data", type=Path)
    p.add_argument("--replay", type=Path)
    a = p.parse_args()
    a.dest.mkdir(parents=True, exist_ok=True)
    if a.task == "profile":
        write(a.dest / "search-audit.json", {c: frozen_search(a.store, a.dest, c) for c in CASES})
    elif a.task == "primitive":
        if a.data is None or a.replay is None:
            p.error("primitive requires --data and --replay")
        write(a.dest / "primitive-work.json", native_work(a.data, a.store, a.replay))
    else:
        write(a.dest / "native-rollouts.json", rollouts(a.store, CASES))
