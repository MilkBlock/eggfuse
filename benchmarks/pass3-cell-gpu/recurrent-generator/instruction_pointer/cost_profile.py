"""Offline instrumentation of the frozen B's actual batched parent searches."""

import json
import shutil
import subprocess
from time import perf_counter

import numpy as np

from cell_transaction import STATUS
from recursive_train import binary, folder, read
from structure_runtime import StructureEntries

FIELDS = ("prefixes", "scores", "old_certificate", "negative", "score_ns")
META = ("run", "rule", "entry_role", "token", "op", "version", "wake", "batch")


class CostProfile:
    def __init__(self):
        self.blocks = []
        self.depths = []
        self.verdicts = []
        self.batch = []
        self.winners = {}
        self.probes = {}
        self.duplicate_refs = {}
        self.base = 0

    def start(self, mem, run, r, j, ix, woke, stats):
        self.t0 = perf_counter()
        self.n = len(ix)
        self.order = mem.order(r, j)
        self.mem = mem
        self.rule = r
        self.run = run
        roots = mem.bank(mem.roles[r][j]).rows[ix] if j >= 0 else np.zeros((len(ix), 3), np.int64)
        meta = np.empty((len(ix), len(META)), np.int64)
        meta[:, :3] = run, r, j
        meta[:, 3:6] = roots
        meta[:, 6:] = int(woke), len(self.batch)
        self.blocks.append(meta)
        self.lookup = np.zeros(int(ix.max()) + 1, np.int64)
        self.lookup[ix] = np.arange(len(ix))
        self.depth = np.zeros((len(ix), len(self.order) + 1, len(FIELDS)), np.int64)
        self.verdict = np.zeros((len(ix), len(STATUS) + 2), np.int64)
        self.before = (stats["visits"], stats["parent_candidate_scores"])

    def add(self, arr, ids):
        if len(ids):
            arr += np.bincount(ids, minlength=self.n)

    def prefix(self, paths, d):
        roots = self.lookup[paths[:, 0]] if d else np.zeros(len(paths), np.int64)
        self.add(self.depth[:, d, 0], roots)

    def formed(self, paths, roots):
        if len(self.order):
            self.add(self.verdict[:, -2], self.lookup[paths[:, 0]])
        else:
            self.verdict[0, -2] += len(paths)
        self.add(self.verdict[:, -1], self.lookup[roots])

    def scored(self, mem, r, order, d, child, keep, wm, seconds):
        ix = self.lookup[child[:, 0]]
        n = np.bincount(ix, minlength=self.n)
        self.depth[:, d, 1] += n
        self.depth[:, d, 4] += np.rint(n * (seconds * 1e9 / len(ix))).astype(np.int64)
        self.add(self.depth[:, d, 3], ix[~keep])
        if mem.rd.iface.rules[r]["metadata"]["seminaive"] and not any(
            len(b.versions) and b.versions[-1] >= wm
            for j in order[d + 1 :]
            for b in [mem.bank(mem.roles[r][j])]
        ):
            old = np.ones(len(ix), bool)
            for k, j in enumerate(order[: d + 1]):
                old &= mem.bank(mem.roles[r][j]).rows[child[:, k], 2] < wm
            self.add(self.depth[:, d, 2], ix[old])
        # Deterministic witness of a rejected complete pointer path. This never
        # changes the requests sent by B. Unprobed paths remain unknown.
        if d == len(order) - 1 and not keep.all():
            for k in np.flatnonzero(~keep)[np.unique(ix[~keep], return_index=True)[1]]:
                eid = self.base + int(ix[k])
                if eid not in self.probes:
                    refs = [None] * len(order)
                    for a, j in enumerate(order):
                        t, p, v = map(int, mem.bank(mem.roles[r][j]).rows[child[k, a]])
                        refs[j] = {"address": {"token": t, "op": p}, "version": v}
                    self.probes[eid] = {"token": eid + 1, "run": self.run, "rule": r, "parents": refs}

    def replies(self, roots, responses, batch):
        ix = self.lookup[roots]
        code = responses[:, 1]
        self.verdict[:, : len(STATUS)] += np.bincount(
            ix * len(STATUS) + code, minlength=self.n * len(STATUS)
        ).reshape(self.n, -1)
        dup = np.flatnonzero(code == 1)
        if len(dup):
            for k in dup[np.unique(ix[dup], return_index=True)[1]]:
                eid = self.base + int(ix[k])
                if eid not in self.duplicate_refs:
                    self.duplicate_refs[eid] = batch[k].copy()
        for k in np.flatnonzero(code == 0):
            self.winners[int(responses[k, 0])] = self.base + int(ix[k])

    def end(self, stats):
        self.batch.append(
            [
                perf_counter() - self.t0,
                stats["visits"] - self.before[0],
                stats["parent_candidate_scores"] - self.before[1],
            ]
        )
        self.depths.append(self.depth)
        self.verdicts.append(self.verdict)
        self.base += self.n

    def save(self, data, store, case, work, result, suffix=""):
        import gzip

        native = binary(data)
        program = folder(data, case) / "program.json"
        tape = work / "issued.json"
        shutil.copyfile(tape, store / f"{case}{suffix}-issued.json")
        report = json.loads(
            subprocess.check_output([native, "replay", program, tape, "audit", "--ept-origins"])
        )
        if report["state_sha"] != result["state_sha"]:
            raise ValueError("baseline replay diverged")
        ops = np.zeros(self.base, np.int64)
        for t, n in report["ept"]["origins"]:
            if t in self.winners:
                ops[self.winners[t]] += n
        prune = np.full(self.base, -1, np.int8)
        if self.probes:
            q = read(tape)
            q["requests"] = list(self.probes.values())
            probes = work / "prune.json"
            probes.write_text(json.dumps(q))
            rep = json.loads(
                subprocess.check_output([native, "replay", program, tape, "audit", "--recall", probes])
            )
            if rep["state_sha"] != result["state_sha"] or rep["unused_recall"]:
                raise ValueError("bad probe replay")
            for _, t, owner, why in rep["recall_verdicts"]:
                prune[t - 1] = int(owner is not None or why == "off_reference")
        width = max(x.shape[1] for x in self.depths)
        depths = np.concatenate([np.pad(x, ((0, 0), (0, width - x.shape[1]), (0, 0))) for x in self.depths])
        meta = np.concatenate(self.blocks)
        np.savez_compressed(
            store / f"{case}{suffix}-ledger.npz",
            meta=meta,
            depth=depths,
            verdict=np.concatenate(self.verdicts),
            batch=np.asarray(self.batch),
            ops=ops,
            prune=prune,
            winners=np.array(list(self.winners.items())),
        )
        with gzip.open(store / f"{case}{suffix}-duplicate-witnesses.jsonl.gz", "wt") as out:
            for eid, refs in self.duplicate_refs.items():
                out.write(json.dumps([eid, refs.tolist()]) + "\n")
        return {
            "events": len(meta),
            "scores": int(depths[:, :, 1].sum()),
            "native_prune_probes": len(self.probes),
        }


class ProfileEntries(StructureEntries):
    def __init__(self, program, store, *args):
        super().__init__(program, store, *args)
        self.store = store
        self.cost_profile = CostProfile()

    def audit_partners(self, data, case, work, result):
        return self.cost_profile.save(data, self.store, case, work, result)
