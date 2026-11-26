"""Construct page targets from real Run suffixes after verified, executed prefixes."""

import json
import subprocess
from collections import Counter, defaultdict

import numpy as np
import torch

from continuation_audit import arguments
from discrete_cells import Marks, from_q
from discrete_draft import Cell
from discrete_editor import features, supervised
from discrete_study import record
from recursive_train import binary, folder, read
from response_study import memory


def sources(a):
    high = a.out / "reference-stream"
    for case, source in (
        ("sum", "teacher"),
        ("dot", "teacher"),
        ("grammar-benefit-fork-17118", "teacher"),
        ("grammar-benefit-fork-17118", "stream"),
        ("sum", "stream"),
    ):
        d = folder(a.data, case)
        yield (
            case,
            source,
            d,
            (
                d / "tape.json"
                if source == "teacher"
                else high / f"{case}-stream-multi/issued.json"
            ),
        )


def boundary(at, total, teacher):
    if at < total:
        return "page_budget"
    return "teacher_run_exhausted" if teacher else "stream_evidence_exhausted"


def examples(m, source, target, end, rng, rec=None, sampled=False):
    z, e, src, dst, vec, bridge = rec if rec is not None else record(m, source, target)
    sup = supervised(src, dst)
    yield (
        "editor",
        features(z, e, [vec[v.cell] for v in src], 0),
        sup,
        torch.ones_like(sup),
    )
    # A legal local bridge ends once this page has been emitted. Right censor its
    # insertion exposure at the tail if we have no evidence for stopping this Run.
    times = range(len(bridge) + 1)
    if sampled and len(bridge) > 4:
        times = sorted(
            {
                0,
                len(bridge),
                *rng.choice(np.arange(1, len(bridge)), 3, replace=False).tolist(),
            }
        )
    for k in times:
        x = bridge[k][0] if k < len(bridge) else dst
        t = float(rng.beta(k + 1, len(bridge) - k + 1))
        X = features(z, e, [vec[v.cell] for v in x], t)
        y = torch.zeros((len(x) + 1, 3))
        mask = torch.ones_like(y)
        if k < len(bridge):
            _, i, op, _ = bridge[k]
            y[i, op] = len(bridge) - k
        elif end != "teacher_run_exhausted":
            mask[-1, 0] = 0
        yield "flow", X, y, mask


@torch.no_grad()
def build(a, case, source, d, tape):
    prefix = "full" if a.full else "corpus"
    output = a.out / f"{prefix}-{case}-{source}.pt"
    if output.exists():
        return
    m = memory(a, d)
    name = output.stem
    mem = a.out / (name + ".jsonl")
    replay = json.loads(
        subprocess.check_output(
            [
                binary(a.data),
                "replay",
                d / "program.json",
                tape,
                "time",
                "--memory",
                mem,
                "--ept-origins",
            ]
        )
    )
    requests = read(tape)["requests"]
    assert replay["counts"]["accepted"] == len(requests)
    ref = (
        read(d / "capture.json")
        if source == "teacher"
        else read(a.out / "reference-stream" / f"{case}.json")
    )
    assert replay["state_sha"] == ref["state_sha"]
    qs = defaultdict(list)
    for q in requests:
        qs[q["run"]].append(q)
    frames = list(map(json.loads, mem.open()))
    gains = dict(replay["ept"]["origins"])
    rng = np.random.default_rng(621)
    marks = Marks()
    counts = Counter()
    rows = defaultdict(list)
    rejects = defaultdict(list)
    if source == "rejected":
        for run, prefix, code, v in read(
            a.out / "reference-stream" / (case + "-negative.json")
        ):
            assert v["response"][1] == code and code
            rejects[run].append(
                (prefix, Cell(v["rule"], tuple(map(tuple, v["refs"]))), code)
            )
    prior = None
    for frame in frames:
        m.update(frame)
        group = qs[frame["run"]]
        n = len(group)
        counts["runs"] += 1
        counts["repair_events"] += len(frame["repair_events"])
        counts["retired"] += len(frame["retired"])
        counts["versioned_updates"] += sum(
            row["version"] > 0 for _, row in frame["updates"]
        )
        if not m.ids:
            continue
        starts = sorted(
            {0, n, min(1, n), *rng.integers(0, n + 1, size=min(12, n)).tolist()}
        )
        # The given tape was accepted in order by this exact native receiver.
        # ResponseMemory's immediate policy input is the last accepted named Cell.
        # No future publication or producer is installed at this prefix.
        contexts = [(j, None, 0) for j in starts]
        if source == "rejected":
            contexts = [r for r in rejects[frame["run"]] if r[0] < n]
            if len(contexts) > 32:
                contexts = [
                    contexts[i]
                    for i in sorted(rng.choice(len(contexts), 32, replace=False))
                ]
        for j, negative, code in contexts:
            if j:
                last = from_q(group[j - 1])
                m.reply([(last, True)])
            if negative is not None:
                m.reply([(negative, False)])
                counts[f"actual_rejection/{code}"] += 1
            end = n if a.full else min(j + 2, n)
            label = boundary(end, n, source == "teacher")
            target = [from_q(q) for q in group[j:end]]
            if j == n and source != "teacher":
                counts["unknown_stream_tail"] += 1
                continue
            counts["max_target_length"] = max(counts["max_target_length"], len(target))
            seed_cells = []
            if negative is not None:
                seed_cells.append([negative])
            elif j:
                seed_cells.append([last])
            elif prior is not None and (prior.rule, False) not in m.ids_index:
                seed_cells.append([prior])
            for src in [[], *seed_cells]:
                # A carried identical head can be another scheduled binding only
                # if it is actually present in the remaining witnessed suffix.
                rec = record(m, src, target)
                if not rec[-1] and label != "teacher_run_exhausted":
                    continue
                counts[label] += 1
                for mode, x, y, mask in examples(
                    m, src, target, label, rng, rec, a.full
                ):
                    if (
                        mode == "editor"
                        and not target
                        and label != "teacher_run_exhausted"
                    ):
                        continue
                    rows[mode].append((x, y, mask))
                jumps = rec[-1]
                if a.full and len(jumps) > 2:
                    jumps = [jumps[0], jumps[int(rng.integers(1, len(jumps)))]]
                for draft, i, op, cell in jumps:
                    if cell is None:
                        continue
                    bits = []
                    got = marks.draw(
                        m,
                        rng,
                        Counter(),
                        hint=draft[i].cell if op == 2 else None,
                        target=cell,
                        records=bits,
                        prefix=draft[:i],
                    )
                    if got != cell:
                        counts["unrepresentable_mark"] += 1
                        continue
                    if bits:
                        rows["marks"].append(
                            (
                                torch.stack([v[0] for v in bits]),
                                torch.tensor([v[1] for v in bits]).float(),
                            )
                        )
                counts["examples"] += 1
                counts["prefix_nonempty"] += j > 0
        if group:
            prior = from_q(group[-1])
    packed = {
        key: tuple(torch.cat(column) for column in zip(*parts, strict=True))
        for key, parts in rows.items()
    }
    torch.save(packed, output)
    meta = {
        "case": case,
        "source": source,
        "requests": len(requests),
        "credited": sum(v > 0 for v in gains.values()),
        "state_sha": replay["state_sha"],
        "counts": counts,
        "rows": {k: len(v[0]) for k, v in packed.items()},
    }
    (a.out / (name + ".json")).write_text(json.dumps(meta) + "\n")
    print(meta, flush=True)


if __name__ == "__main__":
    p = arguments()
    p.add_argument(
        "--source", choices=["teacher", "stream", "rejected", "all"], default="all"
    )
    p.add_argument("--full", action="store_true")
    a = p.parse_args()
    torch.set_num_threads(1)
    for case, source, d, tape in sources(a):
        if a.source in (source, "all"):
            build(a, case, source, d, tape)
        if source == "stream" and case == "sum" and a.source in ("rejected", "all"):
            build(a, case, "rejected", d, tape)
