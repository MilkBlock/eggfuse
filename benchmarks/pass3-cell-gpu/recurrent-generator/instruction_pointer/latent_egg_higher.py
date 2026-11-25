"""Independent held-program, post-freeze Higher activation through CCP v0.1."""

import argparse
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
import torch

from entry_closure import Rules
from higher_replacement import send
from latent_cell_flow import WIDTH, ZERO, Flow, Frozen
from latent_composition import predict
from latent_live import Live
from recursive_coverage import Target, snapshot
from recursive_train import binary, folder, read
from ripsat_policy import CellScorer, GraphBank
from rule_read import load_actor
from transaction_native import execute


def bake(contract, enc, excluded):
    rules = Rules(contract)
    out = {}
    for r, roles in enumerate(rules.inputs):
        if len(roles) != 1:
            continue
        unit = rules.root(r)
        for depth in range(2):
            used = {s[0] for s in unit}
            suffix = next((s for s in rules.extensions(unit, Counter()) if s[0] not in used), None)
            if suffix is None:
                break
            unit += (suffix,)
        if len(unit) > 1 and enc.cat.int_bake.key(unit) not in excluded:
            out[r] = unit
    return out


class EggHigher(Live):
    def __init__(self, enc, net, arm, menu, codes):
        super().__init__(enc, net, "Cdecode" if arm in ("stackD", "stackE") else "A", 0.0)
        self.pick = arm
        self.menu = menu
        self.codes = codes
        self.waiting = []

    def resume_programs(self, frame, pub, txn, stats):
        scheduled = dict(frame["rules"])
        remaining = []
        for unit, ext, owners, versions in self.waiting:
            rid, _, wires = unit[len(owners)]
            # Pin every already-materialized internal output at its first publication.
            # An owner and op can never be resolved to an unrelated matching row.
            for _, _, inputs in unit[len(owners) :]:
                for s, p in inputs:
                    if 0 <= s < len(owners):
                        key = owners[s], p
                        if key in self.confirmed.live:
                            versions.setdefault(key, self.confirmed.live[key][0]["version"])
            if rid in scheduled:
                refs = []
                for s, p in wires:
                    a = (owners[s], p) if s >= 0 else ext[p][:2]
                    v = versions.get(a) if s >= 0 else ext[p][2]
                    stats["named_receipt_reads"] += 1
                    if a not in self.confirmed.live or v != self.confirmed.live[a][0]["version"]:
                        break
                    refs.append((*a, v))
                if len(refs) == len(wires):
                    receipt = send(txn, rid, np.asarray([refs], np.int64).reshape(1, len(refs), 3))[0]
                    stats["lowered_suffix"] += 1
                    if receipt[1] != 0:
                        stats["suffix_rejected"] += 1
                        continue
                    owners.append(int(receipt[0]))
                    if len(owners) == len(unit):
                        stats["higher_completed"] += 1
                        continue
            remaining.append((unit, ext, owners, versions))
        self.waiting = remaining
        stats["open_instances"] = len(remaining)

    def flush(self, batch, txn, stats, run):
        if not batch:
            return
        refs = []
        ops = []
        choices = []
        simulated = self.confirmed.total.float()
        for rid, parents, _ in batch:
            take = False
            if rid in self.menu and self.pick != "baseline":
                tick = perf_counter()
                q = dict(
                    rule=rid, parents=[dict(address=dict(token=t, op=o), version=v) for t, o, v in parents]
                )
                p = self.enc.token(q, self.confirmed.live)
                h = torch.cat((self.codes[rid], p[WIDTH:]))
                z = simulated if self.pick in ("stackD", "stackE") else self.confirmed.total.float()
                hp, pp = (predict(self.flow, z, t) for t in (h, p))
                if self.pick in ("desired", "stackE"):
                    desired = predict(self.flow, z, ZERO.repeat(2), len(self.menu[rid]), True)
                    take = bool((hp - desired).norm() < (pp - desired).norm())
                else:
                    take = bool(hp.norm() > pp.norm())
                if self.pick in ("stackD", "stackE"):
                    simulated = simulated + (hp if take else pp)
                stats["choice_seconds"] += perf_counter() - tick
                stats["menus"] += 1
                stats["high_choices"] += int(take)
            if rid not in self.menu and self.pick in ("stackD", "stackE"):
                q = dict(
                    rule=rid, parents=[dict(address=dict(token=t, op=o), version=v) for t, o, v in parents]
                )
                simulated = simulated + predict(self.flow, simulated, self.enc.token(q, self.confirmed.live))
            choices.append(take)
            refs.extend([(*x, -1) for x in parents])
            ops.append((0, 0, rid, -1, len(refs)))
        response = txn.collect(
            txn.enqueue(np.asarray(ops, np.int64), np.asarray(refs, np.int64).reshape(-1, 4), 0)
        )
        for (rid, parents, _), take, receipt in zip(batch, choices, response.rows.numpy(), strict=True):
            if take and receipt[1] == 0:
                stats["instantiated"] += 1
                self.waiting.append((self.menu[rid], parents, [int(receipt[0])], {}))
        stats["open_instances"] = len(self.waiting)


@torch.no_grad()
def main():
    p = argparse.ArgumentParser()
    for arg in ("root", "store", "actor"):
        p.add_argument(arg, type=Path)
    args = p.parse_args()
    torch.set_num_threads(1)
    excluded = set(read(Path("run-recall/parameterized-deep-ripsat/catalog.json"))["structural_keys"])
    higher = read(args.store / "higher.json")
    excluded.update(higher["donor_signatures"])
    outputs = {}
    for case in ("fact", "loopfact", "sum-divisors", "grammar-benefit-left-17119"):
        d = folder(args.root, case)
        contract = json.loads(
            subprocess.check_output([binary(args.root), "receipt-contract", d / "program.json"])
        )
        tick = perf_counter()
        program = read(d / "program.json")
        actor = load_actor(args.actor, True)
        scorer = CellScorer(WIDTH).eval()
        scorer.load_state_dict(
            torch.load("run-recall/parameterized-deep-ripsat/event-gnn.pt", weights_only=True)["model"]
        )
        enc = Frozen(program, actor, scorer)
        encoder_setup = perf_counter() - tick
        tick = perf_counter()
        menu = bake(contract, enc, excluded)
        codes = (
            dict(zip(menu, GraphBank(list(menu.values()), enc.cat, enc.nodes).encode(scorer))) if menu else {}
        )
        bake_setup = perf_counter() - tick
        runs = []
        with TemporaryDirectory(dir=args.store) as tmp:
            path = Path(tmp) / "ref.json"
            target = Target(program, snapshot(args.root, d, "reference", "-", None, path)[0])
            init = target.match(snapshot(args.root, d, "reference", "-", 0, path)[0])
            for block in range(4):
                arms = ["baseline", "primitive_fit", "composed", "desired", "stackD", "stackE"]
                for arm in arms if block % 2 == 0 else reversed(arms):
                    tick = perf_counter()
                    net = Flow().eval()
                    net.load_state_dict(
                        torch.load(
                            args.store
                            / ("state137.pt" if arm in ("baseline", "primitive_fit") else "higher-flow.pt"),
                            weights_only=True,
                        )
                    )
                    policy = EggHigher(enc, net, arm, menu, codes)
                    setup = perf_counter() - tick + encoder_setup + (bake_setup if arm != "baseline" else 0)
                    row = execute(args.root, case, study=policy, seconds=180, series=tmp)
                    covered = target.match(read(Path(tmp) / (case + "-stream-multi") / "state.json")) - init
                    runs.append(
                        dict(
                            arm=arm,
                            block=block,
                            covered=len(covered),
                            reference=len(target.gold) - len(init),
                            covered_sha=hashlib.sha256(json.dumps(sorted(covered)).encode()).hexdigest(),
                            state_sha=row["state_sha"],
                            paid=row["paid"],
                            ept=row["ept"],
                            effective=row["signed_ops"],
                            work=row["work"],
                            verdicts=row["verdicts"],
                            wall=row["wall"] + row["runtime_setup_seconds"],
                            cold_wall=row["wall"] + row["runtime_setup_seconds"] + setup,
                            termination=row["termination"],
                        )
                    )
        outputs[case] = dict(
            menu_size=len(menu),
            encoder_setup=encoder_setup,
            bake_code_setup=bake_setup,
            signatures=[enc.cat.int_bake.key(u) for u in menu.values()],
            runs=runs,
        )
        (args.store / "egg-higher.json").write_text(json.dumps(outputs, indent=2) + "\n")
        print(case, len(menu), flush=True)


if __name__ == "__main__":
    main()
