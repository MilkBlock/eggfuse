"""Compare two statically legal same-type named wires with identical rule nodes and different native outcomes."""

import argparse
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import torch
from torch.nn import functional as F

from discrete_cells import Memory, load_enc
from discrete_draft import Cell, plan
from discrete_rollout import Policy
from discrete_study import load
from recursive_train import binary, folder, read
from scaling_bake import graph_program, save
from scaling_native import execute


@torch.no_grad()
def probe(a, n):
    d = folder(a.root, f"wiring-scale-{n}")
    d.mkdir(exist_ok=True)
    source, expected = graph_program("line", n, 1, 17)
    # Both named outputs are legal. One dependency carries a finish time 37 units later.
    base = "(Finish0 (+ x0 4))"
    if source.count(base) != 1:
        raise ValueError("unexpected first-rule computation")
    src = d.with_suffix(".egg")
    src.write_text(source.replace(base, base + " (Finish0 (+ x0 41))"))
    with TemporaryDirectory(dir=a.out) as tmp:
        compiled = Path(tmp) / "native"
        subprocess.run(
            [a.compiler, "compile", "--source", src, "--output", compiled],
            stdout=subprocess.DEVNULL,
            check=True,
        )
        (d / "program.json").write_bytes((compiled / "program.json").read_bytes())
    p = d / "program.json"
    exe = binary(a.root)
    cap = subprocess.check_output(
        [exe, "capture", p, d / "tape.json", "audit", "--memory", d / "memory.jsonl", "--ept"]
    )
    (d / "capture.json").write_bytes(cap)
    import json

    c = json.loads(subprocess.check_output([exe, "receipt-contract", p]))
    program = read(p)
    names = [t["name"] for t in program["recipe"]["tables"]]
    producers = {}
    for rid, r in enumerate(c["rules"]):
        for pc, site in r["outputs"].items():
            producers.setdefault(names[site["table"]], []).append((rid, int(pc)))
    first = sorted(producers["Finish0"])
    if len(first) != 2 or first[0][0] != first[1][0]:
        raise ValueError("expected two named root receipts")
    enc, scorer = load_enc(program, a.actor)
    marks, nets = load(type("Weights", (), {"out": a.weights}))
    codes = []
    records = []
    with (d / "memory.jsonl").open() as fs:
        frame = json.loads(next(fs))
    q = read(d / "tape.json")["requests"][0]
    external = tuple((v["address"]["token"], v["address"]["op"], v["version"]) for v in q["parents"])
    for root, pc in first:
        body = [(root, 0, [(-1, 0)])]
        for j in range(1, n):
            rid = producers[f"Finish{j}"][0][0]
            body.append((rid, j, [(j - 1, pc if j == 1 else producers[f"Finish{j - 1}"][0][1])]))
        menu = {root: body}
        m = Memory(enc, c, menu, scorer)
        m.update(frame)
        code = m.codes[root]
        codes.append(code)
        prob = marks.choice(marks.branch(m.context(), enc.graphs[root], code, 0)).sigmoid().item()

        class Forced(Policy):
            started = False

            def run_snapshot(self, frame, pub, rd, model, txn, stats, deadline):
                super().run_snapshot(frame, pub, rd, model, txn, stats, deadline)
                if not self.started and root in dict(frame["rules"]):
                    self.send(plan([Cell(root, external, True)]), txn, stats)
                    self.started = True

        # Fresh memory for native execution. The initial named request is an offline intervention.
        m = Memory(enc, c, menu, scorer)
        pol = Forced(m, marks, nets, "noop", 1, 0, 1)
        with TemporaryDirectory(dir=a.out) as tmp:
            r = execute(a.root, d.name, study=pol, series=tmp, seconds=300)
            state = read(Path(tmp) / (d.name + "-stream-multi") / "state.json")
        vals = [v["values"][0]["value"] for v in state["rows"] if v["table"] == f"Finish{n - 1}"]
        if len(vals) != 1 or r["paid"] != n or r["work"].get("higher_completed") != 1:
            raise ValueError((vals, r["work"]))
        records.append(
            dict(pc=pc, leaf_value=vals[0], paid=r["paid"], select_probability=prob, terminal=r["state_sha"])
        )
    if {v["leaf_value"] for v in records} != {
        expected[f"Finish{n - 1}", 0],
        expected[f"Finish{n - 1}", 0] + 37,
    }:
        raise ValueError("wiring semantic mismatch")
    return dict(
        size=n,
        wires=records,
        cosine=F.cosine_similarity(*codes, dim=0).item(),
        relative_distance=((codes[0] - codes[1]).norm() / codes[0].norm()).item(),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for k in ("root", "compiler", "out", "actor", "weights"):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    rows = []
    for n in (6, 16, 32, 64, 128, 256, 512):
        rows.append(probe(a, n))
        save(a.out / "wiring.json", rows)
