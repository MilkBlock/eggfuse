"""Offline trace audit of the frozen deep Cell catalog and its event recognizer."""
import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import torch

from deep_ripsat import depth
from event_addresses import Directory
from int_parameters import link_layouts
from recursive_agent import Reader
from ripsat_layout import capture, queries
from ripsat_policy import CellScorer
from ripsat_replay import unpack
from side_boundary import address


def read(path):
    return json.loads(path.read_bytes())


def projections(layout):
    rules = tuple(r for r, _, _ in layout)
    owners = tuple(tuple(p for p, _ in wires) for _, _, wires in layout)
    ports = tuple(tuple(pc if p >= 0 else None for p, pc in wires) for _, _, wires in layout)
    epochs = tuple(g for _, g, _ in layout)
    return (tuple(sorted(rules)), rules, (rules, owners), (rules, owners, ports),
            (rules, owners, ports, epochs), layout)


STAGES = ("rule_multiset", "rule_order", "owner_wiring", "producer_pc", "run_groups", "boundary_sharing")


def readiness_failures(boundary, tokens, unit, requests, timeline):
    def version(key, run):
        events = timeline[key]
        i = bisect_right(events, run, key=lambda row: row[0]) - 1
        return events[i][1] if i >= 0 else None

    faults = set()
    root_run = requests[tokens[0]]["run"]
    for tok, pc, expected in boundary:
        observed = version((tok, pc), root_run)
        if observed is None:
            faults.add("external_absent_at_entry")
        elif expected != observed:
            faults.add("external_version_at_entry")
    for token, (_, _, wires) in zip(tokens, unit, strict=True):
        for (owner, pc), ref in zip(wires, requests[token]["parents"], strict=True):
            if owner >= 0:
                producer = requests[tokens[owner]]
                if version(address(ref), producer["run"] + 1) != ref["version"]:
                    faults.add("internal_receipt_version")
    return faults


@torch.no_grad()
def event_quality(folder, target, frames, refs, menus, ready, checkpoint):
    rd = Reader(target, folder.parent, rename_seed=179)
    mem = Directory(rd, Counter())
    codes = checkpoint["codes"]
    model = CellScorer(codes.shape[1]).eval()
    model.load_state_dict(checkpoint["model"])
    encoder = torch.nn.Linear(16, codes.shape[1])
    encoder.load_state_dict(checkpoint["encoder"])
    runs = defaultdict(list)
    for j,q in enumerate(refs):
        runs[q["run"]].append((j,q))
    labels = defaultdict(Counter)
    decisions = {}
    result = Counter()
    covered, potential = set(), set()
    selected_uids = set()
    for frame in frames:
        rd.advance(frame)
        wm = dict(frame["rules"])
        for j, q in runs[frame["run"]]:
            rid = q["rule"]
            if rid not in menus:
                continue
            menu = menus[rid]
            events = []
            for p in q["parents"]:
                tok, pc = address(p)
                a = rd.store.alias(tok), pc
                row = rd.store.visible[a]
                if row["version"] >= wm[rid]:
                    bank = mem.bank(row["table"])
                    events.append(bank.vec[bank.positions[a]])
            if not q["parents"]:
                events.append(np.zeros(16, np.float32))
            gold = ready.get(j, {})
            for vec in events:
                key = rid, vec.tobytes()
                if key not in decisions:
                    scores = model(encoder(torch.from_numpy(vec)).expand(len(menu), -1), codes[menu])[:,1]
                    best = int(scores.argmax())
                    decisions[key] = menu[best] if scores[best] > 0 else None
                picked = decisions[key]
                result["event_root_pairs"] += 1
                if picked is not None:
                    selected_uids.add(picked)
                    result["issued_pairs"] += 1
                if gold:
                    result["ready_pairs"] += 1
                    labels[key].update(gold.keys())
                    for tokens in gold.values():
                        potential.update(tokens)
                    if picked is None:
                        result["ready_abstained"] += 1
                    elif picked in gold:
                        result["ready_correct"] += 1
                        covered.update(gold[picked])
                    else:
                        result["ready_wrong_choice"] += 1
    result.update(distinct_event_vectors_per_rule=len(decisions),
                  positive_event_vector_classes=len(labels),
                  optimistic_top1_correct=sum(max(v.values()) for v in labels.values()),
                  selected_templates=len(selected_uids), selected_distinct_steps=len(covered),
                  selectable_distinct_steps=len(potential))
    return dict(result)


def analyze(root, name, catalog, checkpoint, per_layout):
    folder = root / name
    target = read(folder / "program.json")
    # Mine in the target namespace. The old exact donor mapping drops producers
    # which structural linking can now bind, changing the observed layouts.
    refs, remap, roots, _ = capture(folder, target, 10, grow_consumers=True)
    if list(remap) != list(range(len(remap))):
        raise ValueError("target contains duplicate exact rule IDs")
    requests = {q["token"]:q for q in refs}
    frames = [json.loads(s) for s in (folder / "memory.jsonl").read_bytes().splitlines()]
    timeline = defaultdict(list)
    for f in frames:
        for a in f["retired"]:
            timeline[a["token"],a["op"]].append((f["run"], None))
        for a,row in f["updates"]:
            timeline[a["token"],a["op"]].append((f["run"], row["version"]))
    linked = {i: tuple(unit) for i,unit in link_layouts(target,catalog)}
    ids = defaultdict(list)
    menus = defaultdict(list)
    for i,l in linked.items():
        ids[l].append(i)
        menus[l[0][0]].append(i)
    fired = {q["rule"] for q in refs}
    seen = [set() for _ in STAGES]
    prefix = set()
    by_root = defaultdict(dict)
    faults = Counter()
    witnesses = {}
    ever_boundary_ready, ever_schedule_ready = set(), set()
    for root_index,options in roots.items():
        for unit,occurrences in options.items():
            for level,key in zip(seen,projections(unit)):
                level.add(key)
            prefix.update(unit[:i] for i in range(1,len(unit)+1))
            for uid in ids.get(unit, ()):
                stats = per_layout[uid]
                stats[name+"_roots"] += 1
                good = set()
                for boundary, ready, scheduled, tokens in occurrences:
                    if ready:
                        ever_boundary_ready.add(uid)
                    if scheduled:
                        ever_schedule_ready.add(uid)
                    if ready and scheduled:
                        good.update(tokens)
                    else:
                        reasons = readiness_failures(boundary, tokens, unit, requests, timeline)
                        if ready != (not reasons):
                            raise ValueError("readiness and reconstructed evidence disagree")
                        if "external_absent_at_entry" in reasons and uid not in witnesses:
                            start = refs[root_index]["run"]
                            for j, (r,group,wires) in enumerate(unit):
                                for role, (owner,slot) in enumerate(wires):
                                    if owner != -1:
                                        continue
                                    tok, pc, version = boundary[slot]
                                    produced = requests.get(tok)
                                    if produced is None or produced["run"] < start:
                                        continue
                                    rule = target["recipe"]["rules"][r]
                                    witnesses[uid] = dict(template=uid, root_run=start,
                                        root_token=tokens[0], root_rule=unit[0][0],
                                        external_producer_run=produced["run"], external_token=tok,
                                        external_pc=pc, external_version=version,
                                        consumer_run=requests[tokens[j]]["run"], consumer_rule=r,
                                        consumer_atom=role, table=queries(rule)[role]["call"]["table"],
                                        size=len(unit), groups=[g for _,g,_ in unit])
                                    break
                                if uid in witnesses:
                                    break
                        if not scheduled:
                            reasons.add("missed_first_schedule")
                        faults["+".join(sorted(reasons))] += 1
                if good:
                    stats[name+"_ready_roots"] += 1
                    by_root[root_index][uid] = good
    funnel = Counter(linked=len(linked))
    for uid,unit in linked.items():
        if unit[0][0] in fired:
            funnel["root_fired"] += 1
        if all(r in fired for r,_,_ in unit):
            funnel["every_rule_fired"] += 1
        for stage, key, level in zip(STAGES,projections(unit),seen):
            if key in level:
                funnel[stage] += 1
        if unit[:-1] in prefix:
            funnel["all_but_last_as_prefix"] += 1
    example_ids = [i for i in witnesses if not per_layout[i][name+"_ready_roots"]]
    examples = [dict(witnesses[i], observed_roots=per_layout[i][name+"_roots"])
                for i in sorted(example_ids, key=lambda i: (-per_layout[i][name+"_roots"],i))[:3]]
    # Sensitivity to mining order. Same tape and eligibility; try every direct
    # parent first, preserving the original grow-consumers pass.
    extra = {}
    if name not in ("sum","dot"):
        _, _, alternatives, _ = capture(folder, target, 10, grow_consumers=True, each_parent_first=True)
        observed_ids, ready_ids = set(), set()
        for choices in alternatives.values():
            for layout, occurrences in choices.items():
                members = ids.get(layout, ())
                observed_ids.update(members)
                if members and any(ok and first for _,ok,first,_ in occurrences):
                    ready_ids.update(members)
        extra = dict(observed=len(observed_ids), ready=len(ready_ids))
        for i in ready_ids:
            per_layout[i][name+"_alternative_ready"] = 1
    subsets = {}
    for minimum in (0,1,2,5):
        eligible = {r["uid"] for r in per_layout if
                    r["sum_fit_ready_roots"] + r["dot_fit_ready_roots"] >= minimum}
        active, tokens = set(), set()
        for root_index, options in by_root.items():
            for uid, proof in options.items():
                if uid in eligible:
                    active.add(root_index)
                    tokens.update(proof)
        subsets[minimum] = dict(catalog_size=len(eligible), ready_roots=len(active),
                                distinct_teacher_steps=len(tokens))
    restricted = {}
    if extra:
        eligible = {r["uid"] for r in per_layout if r["sum_fit_ready_roots"] or r["dot_fit_ready_roots"]}
        subset_menus = {r: [i for i in menu if i in eligible] for r,menu in menus.items()}
        subset_ready = {j: {i:v for i,v in options.items() if i in eligible} for j,options in by_root.items()}
        restricted = event_quality(folder,target,frames,refs,
                                   {r:m for r,m in subset_menus.items() if m},subset_ready,checkpoint)
    return dict(commits=len(refs), late_examples=examples, train_ready_only_recognition=restricted, train_support_subsets=subsets, alternative_parent_order=extra, funnel=dict(funnel),
                boundary_ready_templates=len(ever_boundary_ready), scheduled_templates=len(ever_schedule_ready),
                ready_templates=sum(bool(s[name+"_ready_roots"]) for s in per_layout),
                ready_roots=len(by_root), sampled_failed_occurrences=faults,
                recognition=event_quality(folder,target,frames,refs,menus,by_root,checkpoint))


def main(root, source, out):
    catalog = read(source/"catalog.json")
    checkpoint = torch.load(source/"event-gnn.pt", weights_only=True)
    rows = []
    for uid, unit in enumerate(unpack(catalog["layouts"])):
        external = {pc for _,_,wires in unit for p,pc in wires if p < 0}
        root_slots = {pc for p,pc in unit[0][2]}
        rows.append(Counter(uid=uid, root=unit[0][0], depth=depth(unit), steps=len(unit),
                            external=len(external), extra_entry_slots=len(external-root_slots)))
    results = {}
    train = ("sum","dot")
    evaluation = ("fact","loopfact","sum-divisors")
    # Reproduce the concrete donor namespace and root sets actually used by
    # deep_ripsat training. Re-mining dot in its own namespace can change cuts.
    donor = read(root/"sum/program.json")
    original = {unit:i for i,unit in enumerate(unpack(catalog["layouts"]))}
    for name in train:
        _,_,roots,_ = capture(root/name, donor, 10, grow_consumers=True)
        for choices in roots.values():
            for unit, occurrences in choices.items():
                if unit in original and any(ok and first for _,ok,first,_ in occurrences):
                    rows[original[unit]][name+"_fit_ready_roots"] += 1
    for name in train+evaluation:
        results[name] = analyze(root,name,catalog,checkpoint,rows)
        print(name, results[name]["funnel"], results[name]["ready_templates"], flush=True)
    for row in rows:
        for label,cases in (("train",train),("evaluation",evaluation)):
            suffix = "_fit_ready_roots" if label == "train" else "_ready_roots"
            counts = [row[n+suffix] for n in cases]
            row[label+"_ready_roots"] = sum(counts)
            row[label+"_ready_programs"] = sum(bool(n) for n in counts)
    by_support = defaultdict(Counter)
    by_external = defaultdict(Counter)
    by_depth = defaultdict(Counter)
    for row in rows:
        count = row["train_ready_roots"]
        support = "0" if not count else "1" if count==1 else "2-4" if count<5 else "5+"
        extra = row["extra_entry_slots"]
        for group in (by_support[support], by_external[min(extra,5)], by_depth[row["depth"]]):
            group["templates"] += 1
            group["train_ready"] += bool(count)
            group["evaluation_ready"] += bool(row["evaluation_ready_roots"])
            group["alternative_evaluation_ready"] += any(row[n+"_alternative_ready"] for n in evaluation)
    out.mkdir(parents=True, exist_ok=True)
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with (out/"templates.csv").open("w",newline="") as f:
        w = csv.writer(f,lineterminator="\n")
        w.writerow(keys)
        w.writerows([r[k] for k in keys] for r in rows)
    result = dict(catalog_sha256=hashlib.sha256((source/"catalog.json").read_bytes()).hexdigest(),
                  weights_sha256=hashlib.sha256((source/"event-gnn.pt").read_bytes()).hexdigest(),
                  programs=results, by_train_ready_roots=by_support, by_extra_entry_slots=by_external,
                  by_depth=by_depth)
    (out/"audit.json").write_text(json.dumps(result,indent=2)+"\n")


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    for name in ("root","catalog","out"):
        parser.add_argument(name,type=Path)
    args=parser.parse_args()
    torch.set_num_threads(1)
    main(args.root,args.catalog,args.out)
