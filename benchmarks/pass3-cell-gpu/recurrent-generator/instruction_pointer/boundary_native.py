"""Independent offline intervention: replay only the signed prefix, issue one graph, drain native schedule."""

import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory, TemporaryFile

from scaling_bake import save

PROBE = 1 << 50


def run_graph(exe, d, out, tape, run, unit, external):
    packets = defaultdict(list)
    for q in tape:
        if q["run"] < run:
            packets[q["run"]].append(q)
    premise = lambda ref: dict(address=dict(token=ref[0], op=ref[1]), version=ref[2])
    boundary = list(map(premise, external))
    root = dict(
        token=PROBE,
        run=run,
        rule=unit[0][0],
        parents=[boundary[p] for s, p in unit[0][2]],
        graph=dict(layout=0, boundary=boundary),
    )
    outcomes = Counter()
    failure = []
    dispatch_run = {}
    with TemporaryDirectory(dir=out) as tmp, TemporaryFile() as err:
        path = Path(tmp) / "layout.json"
        save(path, [unit])
        proc = subprocess.Popen(
            [exe, "online", d / "program.json", "-", "audit", "--layout-feedback", path, "--ept-origins"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=err,
            text=True,
        )
        try:
            report = None
            for line in proc.stdout:
                f = json.loads(line)
                if "layout_feedback" not in f:
                    report = f
                    break
                feedback = f["layout_feedback"]
                for _, token, _, _ in feedback["claims"]:
                    dispatch_run[token] = f["run"]
                for _, token, verdict in feedback["outcomes"]:
                    outcomes[verdict] += 1
                    if verdict not in ("accepted", "external_alternative"):
                        step = 1 + token - (1 << 61)
                        failure.append(
                            dict(
                                step=step,
                                rule=unit[step][0],
                                issued_run=dispatch_run.get(token, run),
                                verdict=verdict,
                            )
                        )
                batch = packets[f["run"]] if f["run"] < run else [root] if f["run"] == run else []
                proc.stdin.write(json.dumps(batch) + "\n")
                proc.stdin.flush()
            proc.stdin.close()
            code = proc.wait()
            if code or report is None:
                err.seek(0)
                raise ValueError(err.read().decode()[-500:] or "native replay missing result")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    counts = report["layouts"]["counts"]
    credit = report["ept"]
    root_values = [v for k, v in credit["origins"] if k == PROBE]
    observed = {k for k, v in credit["origins"] if k is not None}
    expected = {q["token"] for batch in packets.values() for q in batch}
    if not expected <= observed:
        raise ValueError("prefix was not reproducible")
    siblings = sum(g == 0 for _, g, _ in unit) - 1
    entry = (
        bool(root_values)
        and counts["issued_layouts"].get("0", 0) == 1
        and all((1 << 61) + j in observed for j in range(siblings))
    )
    admitted = counts["issued_layouts"].get("0", 0) == 1
    return dict(
        entry=entry,
        complete=counts["completed_layouts"].get("0", 0) == 1,
        root_effective=sum(root_values),
        effective=(sum(root_values) if admitted else 0) + sum(credit["signed_internal"]),
        ordinary_fallback_effective=0 if admitted else sum(root_values),
        accepted_internal=counts["accepted_steps"],
        counts=counts,
        outcomes=outcomes,
        failure=failure,
        state_sha=report["state_sha"],
    )
