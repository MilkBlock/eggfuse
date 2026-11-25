"""Different named proofs of a common result. Compare native end states before labeling overlap."""

import argparse
import hashlib
import itertools
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import torch

from latent_cell_flow import WIDTH, Flow, Frozen, Published
from recursive_train import read
from ripsat_policy import CellScorer
from rule_read import load_actor


@torch.no_grad()
def main():
    p = argparse.ArgumentParser()
    for k in ("compiler", "runtime", "actor", "store"):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    with TemporaryDirectory(dir=a.store) as scratch:
        w = Path(scratch)
        d = w / "compiled"
        src = w / "pair.egg"
        src.write_text("""
(relation Evidence (i64))
(relation Additional (i64))
(relation Outcome (i64))
(ruleset actions)
(rule ((Evidence x)) ((Outcome x)) :ruleset actions)
(rule ((Evidence x) (Additional x)) ((Outcome x)) :ruleset actions)
(Evidence 42)
(Additional 42)
(run-schedule (run actions) (run actions))
""")
        subprocess.run(
            [a.compiler, "compile", "--source", src, "--output", d], stdout=subprocess.DEVNULL, check=True
        )
        prog = d / "program.json"
        tape = w / "tape.json"
        mem = w / "first.jsonl"
        subprocess.run(
            [a.runtime, "capture", prog, tape, "audit", "--memory", mem],
            stdout=subprocess.DEVNULL,
            check=True,
        )
        raw = read(tape)
        rs = raw["requests"]
        if len(rs) != 2 or rs[0]["rule"] == rs[1]["rule"]:
            raise ValueError("need two distinct named proofs")
        scorer = CellScorer(WIDTH).eval()
        scorer.load_state_dict(
            torch.load("run-recall/parameterized-deep-ripsat/event-gnn.pt", weights_only=True)["model"]
        )
        enc = Frozen(read(prog), load_actor(a.actor, True), scorer)
        state = Published(enc)
        state.change(json.loads(mem.read_text().splitlines()[0]), True)
        net = Flow().eval()
        net.load_state_dict(torch.load(a.store / "state137.pt", weights_only=True))
        actions = [enc.token(q, state.live) for q in rs]
        results = {}
        for n in (0, 1, 2):
            for order in itertools.permutations(range(2), n):
                trial = w / "trial.json"
                trial.write_text(json.dumps({**raw, "requests": [rs[i] for i in order]}))
                report = json.loads(
                    subprocess.check_output(
                        [
                            a.runtime,
                            "replay",
                            prog,
                            trial,
                            "audit",
                            "2",
                            "--export",
                            w / "state.json",
                            "--ept",
                        ]
                    )
                )
                norm = None
                if order:
                    last = actions[order[-1]]
                    pending = actions[order[0]] if n == 2 else torch.zeros_like(last)
                    norm = float(
                        net(
                            state.total.float()[None],
                            pending[None],
                            last[None],
                            torch.ones(1, 1),
                            torch.zeros(1, 2),
                        ).norm()
                    )
                results["".join(map(str, order)) or "empty"] = dict(
                    outcome=[
                        r["values"][0]
                        for r in read(w / "state.json")["rows"]
                        if not r["subsumed"] and r["table"] == "Outcome"
                    ],
                    state_sha=report["state_sha"],
                    visible_sha=hashlib.sha256(
                        json.dumps(
                            sorted(
                                (r["table"], json.dumps(r["values"], sort_keys=True))
                                for r in read(w / "state.json")["rows"]
                                if not r["subsumed"]
                            )
                        ).encode()
                    ).hexdigest(),
                    counts=report["counts"],
                    signed=report["ept"]["signed_external"],
                    predicted_norm=norm,
                )
        if (
            not results["0"]["outcome"]
            or results["empty"]["outcome"]
            or any(results[x]["outcome"] != results["0"]["outcome"] for x in ("1", "01", "10"))
            or results["0"]["visible_sha"] != results["01"]["visible_sha"]
        ):
            raise ValueError("native semantic equivalence failed")
        (a.store / "overlap.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
