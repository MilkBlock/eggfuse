"""Force one preselected graph certificate in an otherwise named teacher replay.
Only the returned feedback translates IDs. No alternative proofs are searched.
"""

import argparse
from collections import defaultdict
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from receipt_bake import link_layouts, read, save


def replay(folder, binary, layout_file, case, tape, reference):
    packets = defaultdict(list)
    for q in tape:
        packets[q["run"]].append(q)
    steps = case["internal_tokens"]
    root = steps[0]
    children = set(steps[1:])
    ids = {}

    def parent(p):
        a = p["address"]
        return dict(p, address=dict(a, token=ids.get(a["token"], a["token"])))

    # Resolve the compact boundary at its first external read in Recipe order.
    unit = read(layout_file)[0]
    by_token = {q["token"]: q for q in tape}
    boundary = {}
    for t, (_, _, wires) in zip(steps, unit, strict=True):
        for (src, pc), arg in zip(wires, by_token[t]["parents"], strict=True):
            if src < 0:
                boundary[pc] = arg
    cmd = [
        binary,
        "online",
        folder / "program.json",
        "-",
        "audit",
        "--layout-feedback",
        layout_file,
    ]
    with subprocess.Popen(
        cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    ) as proc:
        try:
            for line in proc.stdout:
                frame = json.loads(line)
                if "layout_feedback" not in frame:
                    report = frame
                    break
                run = frame["run"]
                claims = frame["layout_feedback"]["claims"]
                for owner, actual, rule, parents in claims:
                    expected = [
                        q
                        for q in packets[run]
                        if q["token"] in children
                        and q["rule"] == rule
                        and list(map(parent, q["parents"])) == parents
                    ]
                    if owner != root or len(expected) != 1:
                        raise ValueError("unexpected graph dispatch")
                    ids[expected[0]["token"]] = actual
                batch = []
                for q in packets[run]:
                    if q["token"] in children:
                        continue
                    issued = dict(q, parents=list(map(parent, q["parents"])))
                    if q["token"] == root:
                        issued["graph"] = dict(
                            layout=0,
                            boundary=[boundary[i] for i in range(len(boundary))],
                        )
                    batch.append(issued)
                proc.stdin.write(json.dumps(batch) + "\n")
                proc.stdin.flush()
            else:
                raise ValueError("missing native execution report")
        finally:
            proc.stdin.close()
        if proc.wait():
            raise ValueError("native replay failed")
    costs = report["layouts"]["counts"]
    if costs["completed_layouts"] != {"0": 1} or set(ids) != children:
        raise ValueError(("instance did not complete", costs))
    same = {
        k: report[k] == reference[k]
        for k in ("state_sha", "schedule", "writes", "rhs", "resumes", "events")
    }
    if not all(same.values()) or report["counts"]["accepted"] != len(tape):
        raise ValueError(("replay diverged", same, report["counts"]))
    return dict(
        root=root, checks=same, accepted=report["counts"]["accepted"], graph=costs
    )


def run(folder, binary, catalog, cases, output):
    unit = dict(link_layouts(read(folder / "program.json"), read(catalog)))[4790]
    tape = read(folder / "tape.json")["requests"]
    reference = read(folder / "capture.json")
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "layout.json"
        save(path, [unit])
        rows = [replay(folder, binary, path, c, tape, reference) for c in cases]
    save(output, rows)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("folder", "binary", "catalog", "regression", "output"):
        p.add_argument(k, type=Path)
    args = p.parse_args()
    run(
        args.folder,
        args.binary,
        args.catalog,
        read(args.regression)["instances"],
        args.output,
    )
