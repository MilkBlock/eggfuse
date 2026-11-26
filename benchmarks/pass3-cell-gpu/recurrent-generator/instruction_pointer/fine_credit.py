"""Offline, receipt-scoped CCP proof credit. Online generation never imports this module."""

import argparse
import gzip
import hashlib
import json
import subprocess
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from cell_transaction import STATUS
from credit_scale_fit import load_shard
from discovery_sampling import encode
from discovery_score import packet, token
from transition_credit import decode, schema

AXES = (
    "structure",
    "timing",
    "binding",
    "condition",
    "novelty",
    "contribution",
    "dependency",
    "omission",
    "cost",
)


def labels(status, generate_dirty, issue_dirty, gain, present):
    """Each entry is (target, value, evidence). Missing entries are Unknown, mask zero.

    structure=+1 only certifies suitability of this instantiation at admission.
    Cost is paid proof count. Wall time is recorded at its observed batch scope.
    """
    v = {"cost": ("signed_request", 1, "paid_ccp")}
    if status == "untriggered_rule":
        if issue_dirty is True:
            raise ValueError("untriggered proof observed dirty at issue")
        if generate_dirty is False:
            v["timing"] = ("template_at_generation", -1, "scheduler_and_receipt")
        elif generate_dirty is True and issue_dirty is False:
            v["timing"] = ("submit_after_window", -1, "two_observers")
        else:
            v["timing"] = ("issue_trigger_only", -1, "receipt")
    elif status == "pending_port":
        v["timing"] = ("pending_reference_at_issue", -1, "receipt")
    elif status in {
        "arity",
        "binding",
        "unknown_output",
        "hidden",
        "version",
        "retired",
        "type",
    }:
        v["binding"] = ("named_tuple_at_issue", -1, "receipt")
    elif status in {
        "watermark",
        "guard",
        "unbound_primitive",
        "unbound_input",
        "accepted",
        "duplicate",
    }:
        v["binding"] = ("table_atom_tuple", 1, "check_passed_all_named_atoms")
        if status == "watermark":
            v["timing"] = ("tuple_at_watermark", -1, "receipt")
        elif status == "guard":
            v["condition"] = ("guard_conjunction", -1, "receipt")
        elif status in {"accepted", "duplicate"}:
            v["condition"] = ("required_query_checks", 1, "check_returned_instance")
            v["structure"] = ("this_instantiation", 1, "check_returned_instance")
            v["timing"] = ("this_admission", 1, "receipt")
            v["contribution"] = (
                "immediate_signed_ops",
                gain,
                "replay_origin" if status == "accepted" else "no_second_admission",
            )
            if status == "duplicate":
                v["novelty"] = (
                    "native_signing_key",
                    -1,
                    "same_rule_and_bound_input_values",
                )
            elif gain:
                v["novelty"] = ("some_new_operation", 1, "replay_origin")
            elif present:
                v["novelty"] = (
                    "published_single_effect",
                    -1,
                    "recipe_projection_and_replay",
                )
    if gain and status != "accepted":
        raise ValueError("unsigned effective operation")
    return v


def one_edit(failed, valid):
    by_context = defaultdict(list)
    for c in valid:
        for j in range(len(c.refs)):
            by_context[
                c.rule, c.higher, c.observe, j, c.refs[:j], c.refs[j + 1 :]
            ].append(c)
    for c in failed:
        for j in range(len(c.refs)):
            for other in by_context.get(
                (c.rule, c.higher, c.observe, j, c.refs[:j], c.refs[j + 1 :]), ()
            ):
                if other.refs[j] != c.refs[j]:
                    yield c, other, j


def tape(shard):
    rows = []
    for event in shard["events"]:
        for cells, replies in (
            ("generated", "response"),
            ("assisted", "assisted_response"),
        ):
            for c, r in zip(event[cells], event[replies], strict=True):
                if STATUS[r[1]] == "accepted":
                    rows.append(packet(token(c), event["frame"]["run"], r[0]))
    return rows


def evidence(sh, program, runtime, decoded, limit):
    """Single-request substitutions and pinned-suffix parent ablation on isolated forks."""
    signed = tape(sh)
    parents = {r["token"]: r for r in signed}
    result = {"edits": [], "edges": [], "counts": Counter()}
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "tape.json"

        def replay(rows, run):
            path.write_text(
                json.dumps(
                    {
                        "schema": "cell-token-replay/v2",
                        "program_sha256": sh["program"],
                        "repair_events": [
                            q for q in sh["repair_events"] if q["run"] <= run
                        ],
                        "requests": rows,
                    }
                )
            )
            p = subprocess.run(
                [runtime, "replay", program, path, "audit", str(run), "--ept-origins"],
                capture_output=True,
                check=False,
            )
            if p.returncode:
                result["counts"]["unreplayable_forks"] += 1
                return None
            return json.loads(p.stdout)

        proposed = []
        dependencies = []
        for event, (items, omitted) in zip(sh["events"], decoded, strict=True):
            run = event["frame"]["run"]
            bad = sorted(
                {c for c, s, *_ in items if s == "binding"},
                key=lambda c: (c.rule, c.refs),
            )
            good = {c for c, s, g, *_ in items if s == "accepted" and g} | {
                c for c, g, _ in omitted if g
            }
            for c, d, j in one_edit(bad, sorted(good, key=lambda c: (c.rule, c.refs))):
                proposed.append((run, c, d, j))
            for (c, _, gain, *_), receipt in zip(items, event["response"], strict=True):
                if gain:
                    for owner in sorted({t for t, op, v in c.refs if t in parents}):
                        dependencies.append((run, owner, receipt[0]))
        # Deterministic subsampling independent of the model scores. Favour distributed runs.
        import random

        rng = random.Random(
            sh.get("rollout_seed", 42761 + sh["idx"] * 11 + sh["branch"])
        )
        rng.shuffle(proposed)
        rng.shuffle(dependencies)
        checked_starts = set()
        expected_origins = dict(sh["origins"])
        for run, bad, good, slot in proposed[:limit]:
            prefix = [r for r in signed if r["run"] < run]
            if run not in checked_starts:
                start_state = replay(prefix, run - 1)
                event = next(e for e in sh["events"] if e["frame"]["run"] == run)
                if (
                    not start_state
                    or start_state["state_sha"] != event["semantic_state"]
                ):
                    raise ValueError("substitution fork does not reproduce start state")
                checked_starts.add(run)
            uid = max(parents, default=0) + 1
            wrong = replay([*prefix, packet(bad, run, uid)], run)
            right = replay([*prefix, packet(good, run, uid)], run)
            base = replay(prefix, run)
            result["counts"]["edit_attempts"] += 1
            if not all((base, wrong, right)):
                continue

            def failed(rep):
                return rep["counts"]["rejected"].get("binding", 0)

            g = dict(right["ept"]["origins"]).get(uid, 0)
            if (
                failed(wrong) == failed(base) + 1
                and right["counts"]["accepted"] == base["counts"]["accepted"] + 1
                and g > 0
            ):
                result["edits"].append([run, encode(bad), encode(good), slot, g])
        used = set()
        for run, parent, child in dependencies:
            if len(used) >= limit:
                break
            if child in used:
                continue
            used.add(child)
            original = [r for r in signed if r["run"] <= run]
            before = replay(original, run)
            after = replay([r for r in original if r["token"] != parent], run)
            result["counts"]["edge_attempts"] += 1
            if not before or not after:
                continue
            g = dict(before["ept"]["origins"]).get(child, 0)
            if g != expected_origins.get(child, 0):
                result["counts"]["changed_origin_at_horizon"] += 1
                continue
            if g and not dict(after["ept"]["origins"]).get(child, 0):
                result["edges"].append([parents[parent]["run"], parent, run, child, g])
    return result


def produce(source, bank, dest, runtime, limit):
    sh = load_shard(source)
    program = bank / "programs" / f"{sh['idx']:04}" / "program.json"
    if hashlib.sha256(program.read_bytes()).hexdigest() != sh["program"]:
        raise ValueError("wrong recipe")
    ir = json.loads(program.read_bytes())
    stages = {
        r: k["name"] for k in ir["multi_stage"]["rule_sets"] for r in k["rule_ids"]
    }
    decoded = list(decode(sh, schema(ir)))
    forks = evidence(sh, program, runtime, decoded, limit)
    windows = {s[0]: s for s in sh["scheduler"] if not s[3]}
    admissions = {
        uid: (r, rid, epoch, check, bool(dirty))
        for r, uid, rid, epoch, check, dirty in sh.get("admissions", [])
    }
    counts = Counter()
    witnessed_parents = {row[1] for row in forks["edges"]}
    events = []
    for i, (event, (items, omits)) in enumerate(
        zip(sh["events"], decoded, strict=True)
    ):
        f = event["frame"]
        run = f["run"]
        _, epoch, enabled, _, rules = windows[run]
        if epoch != f["epoch"] or f["rules"] != [v[:2] for v in rules]:
            raise ValueError("state mismatch")
        dirty = {rid: bool(d) for rid, _, d in rules}
        states = []
        seen = set()
        for (c, status, g, _, done), r in zip(items, event["response"], strict=True):
            a = admissions.get(r[0])
            if a is not None and a[:4] != (run, c.rule, epoch, enabled):
                raise ValueError("issue snapshot mismatch")
            d = a[-1] if a is not None else None
            if a is None and "admissions" in sh and status != "pending_port":
                raise ValueError("missing issue observer")
            # CCP pins the publication across these synchronous batches. A missing
            # independent admission observation stays null in the archive.
            v = labels(status, dirty[c.rule], d, g, done)
            if r[0] in witnessed_parents:
                v["dependency"] = (
                    "named_producer_on_fixed_suffix",
                    1,
                    "native_parent_removal",
                )
            counts["complete_tokens"] += 1
            counts["physical_repeats"] += c in seen
            seen.add(c)
            for axis in AXES:
                counts[axis + ("_known" if axis in v else "_unknown")] += 1
            counts["response_" + status] += 1
            states.append([r[0], r[1], g, done, d])
        events.append(
            {
                "run": run,
                "epoch": epoch,
                "stage": sorted({stages[r] for r in dirty}),
                "source_event": i,
                "generation_and_issue_publication": f["epoch"],
                "rules": rules,
                "semantic_state": event["semantic_state"],
                "previous_response_event": i - 1 if i else None,
                "rows": states,
            }
        )
        counts["direct_omissions"] += len(omits)
    result = dict(
        schema="receipt-credit/v1",
        source=source.name,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        program=sh["program"],
        events=events,
        **forks,
    )
    counts.update(forks["counts"])
    counts.update(
        verified_edits=len(forks["edits"]),
        verified_edges=len(forks["edges"]),
        states=len(events),
    )
    final_path = dest / source.name
    with TemporaryDirectory(dir=dest) as tmp:
        part = Path(tmp) / source.name
        with gzip.open(part, "wt", compresslevel=1) as f:
            json.dump(result, f, separators=(",", ":"))
        part.replace(final_path)
    return counts


def experiences(source, sidecar):
    """Resolve one normalized archive into self-describing rows for offline consumers.

    Physical port visibility/version comes from the shared publication delta stream.
    Positions in the generation page and synchronous batch identify the observed
    draft, outstanding requests, and previous response without copying Memory.
    """
    sh = load_shard(source)
    index = load_shard(sidecar)
    if hashlib.sha256(source.read_bytes()).hexdigest() != index["source_sha256"]:
        raise ValueError("credit refers to another rollout")
    edges = defaultdict(list)
    for pr, parent, cr, child, gain in index["edges"]:
        edges[parent].append({"consumer": child, "run": cr, "consumer_gain": gain})

    def describe(values):
        return {
            axis: {
                "scope": obj,
                "value": value,
                "source": source,
                "direct_native": source
                in {
                    "receipt",
                    "paid_ccp",
                    "replay_origin",
                    "no_second_admission",
                    "same_rule_and_bound_input_values",
                    "check_returned_instance",
                    "check_passed_all_named_atoms",
                    "native_parent_removal",
                    "native_fork_marginal",
                },
            }
            for axis, (obj, value, source) in values.items()
        }

    live = {}
    previous_response = None
    for i, (event, window) in enumerate(
        zip(sh["events"], index["events"], strict=True)
    ):
        seen = set()
        for key in event["frame"]["retired"]:
            live.pop((key["token"], key["op"]), None)
        for key, row in event["frame"]["updates"]:
            live[key["token"], key["op"]] = row
        dirty = {r: bool(d) for r, w, d in window["rules"]}
        for pos, (raw, row) in enumerate(
            zip(event["generated"], window["rows"], strict=True)
        ):
            uid, code, gain, present, issue_dirty = row
            values = labels(STATUS[code], dirty[raw[0]], issue_dirty, gain, present)
            if uid in edges:
                values["dependency"] = (
                    "named_producer_on_fixed_suffix",
                    edges[uid],
                    "native_parent_removal",
                )
            c = token(raw)
            repeated = c in seen
            seen.add(c)
            if pos and pos % 128 == 0:
                previous_response = event["response"][pos - 1][0]
            yield {
                "state": (
                    sh["program"],
                    window["semantic_state"],
                    sh["checkpoint"],
                    sh.get("rollout_seed", 42761 + sh["idx"] * 11 + sh["branch"]),
                    i,
                ),
                "run": window["run"],
                "epoch": window["epoch"],
                "stage": window["stage"],
                "rules": window["rules"],
                "frame_index": i,
                "draft_index": pos,
                "submitted_batch": (pos // 128),
                "inflight_before_enqueue": 0,
                "preceding_issue_response_id": previous_response,
                "generation_response_event": window["previous_response_event"],
                "generated_page_size": len(event["generated"]),
                "physical_duplicate_in_page": repeated,
                "generation_refs": [
                    {"requested": [t, op, v], "published": live.get((t, op))}
                    for t, op, v in c.refs
                ],
                "token": raw,
                "request": uid,
                "issue_dirty": issue_dirty,
                "receipt": STATUS[code],
                "credit": describe(values),
                "masks": {axis: axis in values for axis in AXES},
                # Issue timing and memory costs retain their actual measurement scope.
                "issue_page_seconds": event["issue_seconds"],
            }
        for response in (event["response"], event["assisted_response"]):
            if response:
                previous_response = response[-1][0]
        for raw, gain in event["omitted"]:
            yield {
                "state": (
                    sh["program"],
                    window["semantic_state"],
                    sh["checkpoint"],
                    sh.get("rollout_seed", 42761 + sh["idx"] * 11 + sh["branch"]),
                    i,
                ),
                "run": window["run"],
                "token": raw,
                "request": None,
                "credit": describe(
                    {
                        "omission": (
                            "feasible_unissued_token",
                            gain,
                            "native_fork_marginal",
                        )
                    }
                ),
                "masks": {axis: axis == "omission" for axis in AXES},
            }


def main():
    parser = argparse.ArgumentParser()
    for name in ("root", "bank", "runtime"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--jobs", type=int, default=6)
    a = parser.parse_args()
    dest = a.root / "credit"
    dest.mkdir(exist_ok=True)
    start = perf_counter()
    paths = sorted((a.root / "buffer").glob("*.gz"))
    if not paths:
        raise ValueError("empty experience archive")
    totals = Counter()
    with ThreadPoolExecutor(a.jobs) as pool:
        for counts in pool.map(
            lambda p: produce(p, a.bank, dest, a.runtime, a.limit), paths
        ):
            totals.update(counts)
    totals["worker_wall_seconds"] = perf_counter() - start
    (a.root / "quality.json").write_text(json.dumps(totals, indent=2) + "\n")


if __name__ == "__main__":
    main()
