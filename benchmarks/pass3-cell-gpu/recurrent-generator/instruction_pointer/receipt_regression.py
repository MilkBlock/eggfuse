"""Named native replay controls and legal publication boundaries for the 4790 regression."""

from collections import Counter, defaultdict
from pathlib import Path
import argparse
import json
import subprocess
import tempfile

from receipt_bake import (
    Snapshot,
    address,
    check,
    link_layouts,
    prove,
    read,
    save,
    specialize,
)
from ripsat_layout import capture


def segment(unit, tokens, start, end, requests):
    slots = {}
    steps = []
    for i in range(start, end):
        r, g, w = unit[i]
        wires = []
        for (src, pc), arg in zip(w, requests[tokens[i]]["parents"], strict=True):
            if src >= start:
                wires.append((src - start, pc))
            else:
                ref = (*address(arg), arg["version"])
                wires.append((-1, slots.setdefault(ref, len(slots))))
        steps.append((r, g - unit[start][1], tuple(wires)))
    return tuple(steps), tuple(slots)


def regression(root, old, new, binary, out):
    name = "loopfact"
    folder = root / name
    p = read(folder / "program.json")
    u = tuple(dict(link_layouts(p, read(old)))[4790])
    replacement = tuple(dict(link_layouts(p, read(new)))[4790])
    refs, _, roots, _ = capture(folder, p, 10, grow_consumers=True)
    requests = {q["token"]: q for q in refs}
    contract = json.loads(
        subprocess.check_output([binary, "receipt-contract", folder / "program.json"])
    )
    memory = Snapshot(folder)
    schedule = defaultdict(list)
    for line in (folder / "memory.jsonl").open():
        frame = json.loads(line)
        for rid, _ in frame["rules"]:
            schedule[rid].append(frame["run"])
    probes = []
    expected = []

    def probe(step, label, target):
        probes.append(dict(step, token=len(probes) + 1))
        expected.append((label, target))

    examples = []
    for j, opts in roots.items():
        for b, _, scheduled, tokens in opts.get(u, ()):
            start = refs[j]["run"]
            entry = []
            for slot, (tok, pc, v) in enumerate(b):
                times = memory.timeline[tok, pc]
                first = next(t for t, ver in times if ver == v)
                uses = [
                    requests[t]["run"]
                    for t, (_, _, w) in zip(tokens, u)
                    if (-1, slot) in w
                ]
                entry.append(
                    dict(
                        slot=slot,
                        token=tok,
                        op=pc,
                        version=v,
                        first_visible_version=first,
                        first_used=min(uses),
                    )
                )
            parts = []
            for begin, end in ((0, len(u) - 1), (len(u) - 1, len(u))):
                part, bb = segment(u, tokens, begin, end, requests)
                steps = prove(part, bb, tokens[begin:end], requests, memory)
                parts.append(dict(slots=len(bb), ready=bool(steps)))
                if steps:
                    for s, t in zip(steps, tokens[begin:end], strict=True):
                        probe(s, "split", t)
            target, new_boundary = specialize(u, b, tokens, contract["rules"])
            if target != replacement:
                raise ValueError(
                    "frozen replacement differs from native returned-port contract"
                )
            steps = prove(replacement, new_boundary, tokens, requests, memory)
            if not scheduled or not steps:
                raise ValueError("specialized regression is not ready")
            for s, t in zip(steps, tokens, strict=True):
                probe(s, "internal", t)
            final = steps[-1]
            # Move just the final check earlier, without changing the source schedule.
            prior_run = max(
                r for r in schedule[final["rule"]] if r <= requests[tokens[-2]]["run"]
            )
            probe(dict(final, run=prior_run), "early", None)
            bad = [dict(x) for x in final["parents"]]
            bad[0] = dict(bad[0], version=bad[0]["version"] + 1)
            probe(dict(final, parents=bad), "stale", None)
            future = next(
                (
                    q
                    for q in refs
                    if q["rule"] == requests[tokens[-2]]["rule"]
                    and q["run"] >= final["run"]
                ),
                None,
            )
            if future:
                later = list(final["parents"])
                later[0] = dict(
                    address=dict(token=future["token"], op=later[0]["address"]["op"]),
                    version=future["run"],
                )
                probe(dict(final, parents=later), "future_receipt", None)
            missing = next(
                (
                    q
                    for q in refs
                    if q["rule"] == requests[tokens[-2]]["rule"]
                    and q["run"] < final["run"]
                    and (q["token"], bad[0]["address"]["op"]) not in memory.timeline
                ),
                None,
            )
            if missing:
                bad = list(final["parents"])
                bad[0] = dict(
                    address=dict(token=missing["token"], op=bad[0]["address"]["op"]),
                    version=missing["run"],
                )
                probe(dict(final, parents=bad), "unpublished_address", None)
            examples.append(
                dict(
                    root=tokens[0],
                    root_run=start,
                    inputs=entry,
                    split=parts,
                    earliest_all_versions=max(
                        a["first_visible_version"] for a in entry
                    ),
                    internal_tokens=tokens,
                )
            )
    if not examples:
        raise ValueError("no regression instances")
    answer = check(folder, binary, read(folder / "tape.json"), probes)
    stats = defaultdict(Counter)
    for _, idx, actual, reason in answer["recall_verdicts"]:
        label, target = expected[idx - 1]
        if actual != target:
            raise ValueError((label, target, actual, reason))
        stats[label][reason] += 1

    # Exercise the production graph-certificate compiler on conditional op PCs,
    # even if the frozen router selects none of these layouts independently.
    def compile_layout(unit, positive):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "layout.json"
            save(path, [unit])
            cmd = [
                binary,
                "online",
                folder / "program.json",
                "-",
                "time",
                "0",
                "--layouts",
                path,
            ]
            p = subprocess.run(cmd, input=b"", capture_output=True)
            if positive and p.returncode != 0:
                raise ValueError(p.stderr)
            if not positive and (
                p.returncode == 0 or b"invalid layout return type" not in p.stderr
            ):
                raise ValueError(p.stderr)
            return p.returncode, p.stderr.decode()[:300]

    # Only structural validation is credited here. No graph is issued on stdin.
    malformed = list(replacement)
    r, g, w = malformed[-1]
    malformed[-1] = (r, g, ((w[0][0], 999999), *w[1:]))
    valid = compile_layout(replacement, True)
    invalid = compile_layout(malformed, False)
    owner, pc = replacement[-1][2][0]
    ret = contract["rules"][replacement[owner][0]]["outputs"][str(pc)]
    save(
        out,
        dict(
            checked=stats,
            instances=examples,
            graph_receiver=[valid, invalid],
            conditional_output=dict(
                step=owner + 1,
                pc=pc,
                table_name=p["recipe"]["tables"][ret["table"]]["name"],
                **ret,
            ),
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("root", "old", "new", "binary", "output"):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    regression(a.root, a.old, a.new, a.binary, a.output)
