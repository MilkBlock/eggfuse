"""Post-edit native causal checks. Teacher suffix is held fixed; no labels feed back into sampling."""

import hashlib
import json
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np
import torch

from discrete_draft import plan
from discrete_editor import sampler
from discrete_study import arguments, dataset, load, save
from latent_cell_flow import TEST
from recursive_train import binary, folder, read


def outcome(exe, program, tape, qs, tmp):
    trial = tmp / "trial.json"
    mem = tmp / "memory.jsonl"
    trial.write_text(json.dumps({**tape, "requests": qs}))
    proc = subprocess.run(
        [exe, "replay", program, trial, "audit", "--memory", mem, "--ept"], capture_output=True
    )
    if proc.returncode:
        return None
    report = json.loads(proc.stdout)
    # Accepted IDs and semantic effects are intentionally distinct; compare subsequent
    # visible receipts, versions, retirements, epochs and repair events, ignoring verifier lists.
    h = hashlib.sha256()
    with mem.open() as f:
        for line in f:
            frame = json.loads(line)
            frame.pop("accepted", None)
            h.update(json.dumps(frame, sort_keys=True, separators=(",", ":")).encode())
    report["pub_sha"] = h.hexdigest()
    return report


@torch.no_grad()
def main(a):
    marks, nets = load(a)
    summary = {}
    for case in TEST:
        d = folder(a.root, case)
        tape = read(d / "tape.json")
        qs = tape["requests"]
        rows = {q["run"]: q for q in map(json.loads, (a.forks / (case + ".jsonl")).read_text().splitlines())}
        chosen = set(sorted(rows)[:3])
        observations = []
        with tempfile.TemporaryDirectory(dir=a.out) as scratch:
            tmp = Path(scratch)
            ref = outcome(binary(a.root), d / "program.json", tape, qs, tmp)

            def visit(m, pairs, run):
                if run not in chosen:
                    return
                q = rows[run]["a"]
                first = next(i for i, v in enumerate(qs) if v["token"] == q["token"])
                high = max(v["token"] for v in qs) + 1
                cache = {}
                for ix, (task, src, dst) in enumerate(pairs):
                    if task not in ("duplicate", "empty"):
                        continue
                    for method, steps in [("source", 0), ("editor", 1), ("mask", 4), ("flow", 4)]:
                        rng = np.random.default_rng(12345 + run * 17 + ix)
                        output = (
                            tuple(src)
                            if method == "source"
                            else tuple(
                                it.cell
                                for it in sampler(
                                    nets[method], marks, m, plan(src), method, steps, rng, Counter()
                                )
                            )
                        )
                        result = cache.get(output)
                        if result is None:
                            if any(c.higher or any(not isinstance(p, tuple) for p in c.refs) for c in output):
                                observations.append(dict(run=run, task=task, method=method, unknown=True))
                                continue
                            inserted = []
                            survives = False
                            for i, c in enumerate(output):
                                saved = not survives and c == dst[0]
                                inserted.append(
                                    dict(
                                        token=q["token"] if saved else high + i,
                                        run=run,
                                        rule=c.rule,
                                        parents=[
                                            dict(address=dict(token=t, op=o), version=v) for t, o, v in c.refs
                                        ],
                                    )
                                )
                                survives |= saved
                            report = outcome(
                                binary(a.root),
                                d / "program.json",
                                tape,
                                qs[:first] + inserted + qs[first + 1 :],
                                tmp,
                            )
                            result = dict(unknown=report is None)
                            if report:
                                keys = (
                                    "pub_sha",
                                    "schedule",
                                    "state_sha",
                                    "writes",
                                    "rhs",
                                    "resumes",
                                    "events",
                                    "ept",
                                )
                                result.update(
                                    equal={k: ref[k] == report[k] for k in keys},
                                    same_effect=all(ref[k] == report[k] for k in keys),
                                    accepted=report["counts"]["accepted"] - ref["counts"]["accepted"],
                                    duplicate_delta=report["counts"]["duplicates"]
                                    - ref["counts"]["duplicates"],
                                )
                            cache[output] = result
                        observations.append(
                            dict(
                                run=run,
                                task=task,
                                method=method,
                                requests=len(output),
                                exact=list(output) == dst,
                                **result,
                            )
                        )

            dataset(a, case, visit)
        summary[case] = observations
        save(a.out / "native-evaluation.json", summary)
        print(case, len(observations), flush=True)


if __name__ == "__main__":
    a = arguments()
    torch.set_num_threads(1)
    main(a)
