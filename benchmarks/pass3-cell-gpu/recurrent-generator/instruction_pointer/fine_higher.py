"""Native paired control for a two-step Higher with an unchanged Recipe and entry."""

import argparse
import json
import subprocess
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

import torch

from ccp_v01 import Client
from cell_transaction import STATUS
from discrete_cells import Memory, load_enc
from discrete_draft import Cell, Item
from fine_credit import labels
from recursive_train import folder
from region_owner import Ownership
from transaction_native import execute

SOURCE = """
(relation Seed (i64))
(relation L (i64))
(relation R (i64))
(ruleset beforeL) (ruleset beforeR) (ruleset root) (ruleset next)
(rule ((Seed x)) ((L x)) :ruleset beforeL)
(rule ((Seed x)) ((R x)) :ruleset beforeR)
(rule ((Seed x)) ((L x)) :ruleset root)
(rule ((L x)) ((R x)) :ruleset next)
(Seed 7)
(run-schedule (run beforeL) (run beforeR) (run root) (run next) (run next))
"""


@torch.no_grad()
def run(a):
    case = "fine-higher-credit"
    d = folder(a.data, case)
    d.mkdir(parents=True, exist_ok=True)
    source = a.out / "higher-control.egg"
    source.write_text(SOURCE)
    with TemporaryDirectory() as temp:
        build = Path(temp) / "program"
        subprocess.run(
            [a.compiler, "compile", "--source", source, "--output", build],
            stdout=subprocess.DEVNULL,
            check=True,
        )
        copyfile(build / "program.json", d / "program.json")
    prog = d / "program.json"
    prefix = [a.runtime, "capture", prog, d / "tape.json", "audit", "--ept"]
    (d / "capture.json").write_bytes(subprocess.check_output(prefix))
    recipe = json.loads(prog.read_bytes())
    contract = json.loads(
        subprocess.check_output([a.runtime, "receipt-contract", prog])
    )
    rules = {s["name"]: s["rule_ids"][0] for s in recipe["multi_stage"]["rule_sets"]}
    root = rules["root"]
    tail = rules["next"]
    (pc,) = contract["rules"][root]["outputs"]
    menu = {root: [(root, 0, [(-1, 0)]), (tail, 1, [(0, int(pc))])]}
    records = []
    for mode, fill in (
        ("empty", ()),
        ("partial", ("beforeR",)),
        ("present", ("beforeL", "beforeR")),
    ):
        receipts = []

        class LogClient(Client):
            def collect(self, ticket, receipts=receipts):
                response = super().collect(ticket)
                receipts.extend(
                    (self.run, int(uid), STATUS[code])
                    for uid, code, *_ in response.rows.tolist()
                )
                return response

        class Diagnostic(Ownership):
            client_type = LogClient

            def resume_programs(self, frame, pub, txn, stats, fill=fill):
                super().resume_programs(frame, pub, txn, stats)
                if frame["run"] == 1:
                    addr, row = next(iter(self.confirmed.live.items()))
                    self.seed = (*addr, row[0]["version"])
                for name in (*fill, "root"):
                    if rules[name] in dict(frame["rules"]):
                        self.send(
                            [Item(0, Cell(rules[name], (self.seed,), name == "root"))],
                            txn,
                            stats,
                        )

        enc, scorer = load_enc(recipe, a.actor)
        actor = Diagnostic(
            Memory(enc, contract, menu, scorer), None, None, "noop", 1, 1, 1
        )
        series = a.out / ("higher-" + mode)
        r = execute(
            a.data, case, study=actor, series=str(series), runtime_binary=a.runtime
        )
        issued = series / (case + "-stream-multi") / "issued.json"
        replay = json.loads(
            subprocess.check_output(
                [a.runtime, "replay", prog, issued, "audit", "--ept-origins"]
            )
        )
        if replay["state_sha"] != r["state_sha"]:
            raise ValueError("replay mismatch")
        origins = dict(replay["ept"]["origins"])
        rows = [
            {
                "run": run,
                "request": uid,
                "status": status,
                "credit": labels(status, None, None, origins.get(uid, 0), False),
            }
            for run, uid, status in receipts
            if run >= 3
        ]
        records.append(
            {
                "mode": mode,
                "template": menu[root],
                "entry": actor.seed,
                "steps": rows,
                "gain": sum(
                    origins.get(uid, 0) for run, uid, _ in receipts if run >= 3
                ),
                "completed": r["work"].get("higher_completed", 0),
                "pending": r["work"].get("open_instances", 0),
                "reference": r["exact_endpoint"],
                "graph": r["state_sha"],
            }
        )
    if len({tuple(r["entry"]) for r in records}) != 1:
        raise ValueError("entry changed")
    (a.out / "higher-control.json").write_text(json.dumps(records, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for key in ("data", "compiler", "runtime", "out", "actor"):
        parser.add_argument("--" + key, required=True, type=Path)
    torch.set_num_threads(1)
    run(parser.parse_args())
