"""Force one preselected graph certificate in an otherwise named teacher replay.
Only the returned feedback translates IDs. No alternative proofs are searched.
"""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from receipt_bake import link_layouts, read, save


def replay_many(folder, binary, layout_file, cases, tape, reference):
    packets = defaultdict(list)
    by_token = {}
    for q in tape:
        packets[q["run"]].append(q)
        by_token[q["token"]] = q
    units = read(layout_file)
    covered = set()
    children = {}
    certificates = {}
    sizes = Counter()
    for uid, steps in cases:
        if covered.intersection(steps):
            raise ValueError("overlapping graph instances")
        covered.update(steps)
        root = steps[0]
        unit = units[uid]
        boundary = {}
        for t, (_, _, wires) in zip(steps, unit, strict=True):
            for (src, pc), arg in zip(wires, by_token[t]["parents"], strict=True):
                if src < 0 and boundary.setdefault(pc, arg) != arg:
                    raise ValueError("inconsistent boundary version")
        certificates[root] = (uid, [boundary[i] for i in range(len(boundary))])
        children.update((t, root) for t in steps[1:])
        sizes[str(uid)] += 1
    ids = {}

    def parent(p):
        a = p["address"]
        return dict(p, address=dict(a, token=ids.get(a["token"], a["token"])))

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
                # First-group siblings are emitted while the root batch is being
                # received. Their native IDs are first observable at publication.
                for accepted in frame["accepted"]:
                    actual = accepted["token"]
                    if actual in by_token or actual in ids.values():
                        continue
                    expected = [
                        q
                        for q in packets[accepted["run"]]
                        if q["token"] in children
                        and q["rule"] == accepted["rule"]
                        and list(map(parent, q["parents"])) == accepted["parents"]
                    ]
                    if len(expected) != 1:
                        raise ValueError("unknown native sibling at publication")
                    ids[expected[0]["token"]] = actual
                claims = frame["layout_feedback"]["claims"]
                for owner, actual, rule, parents in claims:
                    expected = [
                        q
                        for q in packets[run]
                        if children.get(q["token"]) == owner
                        and q["rule"] == rule
                        and list(map(parent, q["parents"])) == parents
                    ]
                    if len(expected) != 1:
                        raise ValueError(
                            ("unexpected graph dispatch", run, owner, rule, parents)
                        )
                    ids[expected[0]["token"]] = actual
                batch = []
                for q in packets[run]:
                    if q["token"] in children:
                        continue
                    issued = dict(q, parents=list(map(parent, q["parents"])))
                    if q["token"] in certificates:
                        uid, boundary = certificates[q["token"]]
                        issued["graph"] = dict(
                            layout=uid, boundary=list(map(parent, boundary))
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
    if costs["completed_layouts"] != sizes or set(ids) != set(children):
        raise ValueError(("instance did not complete", costs))
    same = {
        k: report[k] == reference[k]
        for k in ("state_sha", "schedule", "writes", "rhs", "resumes", "events")
    }
    if not all(same.values()) or report["counts"]["accepted"] != len(tape):
        raise ValueError(("replay diverged", same, report["counts"]))
    return dict(
        checks=same,
        accepted=report["counts"]["accepted"],
        graph=costs,
        external_requests=len(tape) - len(children),
        native_batches=report["runs"],
    )


def replay(folder, binary, layout_file, case, tape, reference):
    steps = case["internal_tokens"]
    result = replay_many(folder, binary, layout_file, [(0, steps)], tape, reference)
    return dict(
        root=steps[0],
        checks=result["checks"],
        accepted=result["accepted"],
        graph=result["graph"],
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
