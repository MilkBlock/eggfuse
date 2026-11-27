"""Coalesce requests from independently advancing native sessions. No speculative prefixes."""

import copy
import json
import math
import os
import queue
import threading
from collections import Counter, defaultdict
from concurrent.futures import Future, ThreadPoolExecutor
from time import perf_counter

import torch
from torch.nn.utils.rnn import pad_sequence

from continuous_trials import setup
from incremental_fit import output
from incremental_native import run_one
from operand_read_model import words
from partner_index_worlds import args
from prefix_attention import static_wires


class Batch:
    def __init__(self, n, device, capacity):
        self.device = device
        self.actor = copy.deepcopy(n.actor).to(device).eval()
        self.capacity = capacity
        self.timed_kernels = device == "mps" and os.getenv("IK_TIMED_KERNELS") == "1"
        self.queue = queue.Queue()
        self.metrics = Counter()
        self.times = Counter()
        self.thread = threading.Thread(target=self.serve)
        self.thread.start()

    def call(self, kind, data):
        f = Future()
        self.queue.put((kind, data, f))
        return f.result()

    def install(self, n):
        if n.mode != "direct" or n.arm != "C" or n.variant == "A":
            raise ValueError(
                "batch path is validated for the direct, rich Cell KV decoder"
            )

        def read(ctx, values, codes):
            return self.call("template", (ctx, values, codes))

        def address(w, m, tid, prefix):
            if not m["refs"]:
                return None
            rid = w.layouts[tid][0][0]
            nodes, codes, _ = n.cache
            key = (tid, tuple(prefix))
            hs = m.setdefault("prefix_hidden", {})
            if key not in hs:
                h = (m["ctx"] + codes[tid]).tanh()
                for j, ix in enumerate(prefix):
                    k = (tid, tuple(prefix[: j + 1]))
                    if k not in hs:
                        hs[k] = n.actor.next_read(m["ext"][ix], h)
                    h = hs[k]
                hs[key] = h
            q = n.actor.query(
                hs[key] + nodes[w.cat.inputs["generated", rid][len(prefix)]]
            )
            if "batch_bank" not in m:
                m["batch_bank"] = {
                    "flat": m["keys"][m["group"]] + m["ek"],
                    "bias": torch.bincount(m["group"]).float().log()[m["group"]],
                    "tables": m["tables"],
                }
            if not hasattr(w, "prefix_wires"):
                w.prefix_wires = {}
            role = rid, len(prefix)
            if role not in w.prefix_wires:
                w.prefix_wires[role] = tuple(static_wires(w, *role)) if prefix else ()
            wires = w.prefix_wires[role]
            bank = m["batch_bank"]
            if wires and "fields" not in bank:
                bank["fields"] = words([p[4] for p in m["ports"]])[0].reshape(
                    len(m["refs"]), -1, 2, 32
                )
            return self.call(
                "parent", (bank, q, w.roles[rid][len(prefix)], wires, prefix, nodes)
            )

        if os.getenv("IK_BATCH_KV") == "1":
            n.context_read = lambda q, k, v: self.call("context", (q, k, v))
            n.owner_read = lambda lp, v: self.call("owner", (lp, v))
        n.template_readout = read
        n.address = address

    def put(self, x):
        if self.device != "cpu":
            self.metrics["upload_bytes"] += x.nbytes
        return x.to(self.device)

    def run_group(self, kind, items):
        tic = perf_counter()
        sizes = []
        if kind == "context":
            qs, ks, vs = zip(*items, strict=True)
            sizes = [len(k) for k in ks]
            q = self.put(torch.stack(qs))
            k = self.put(pad_sequence(ks, batch_first=True))
            vals = self.put(pad_sequence(vs, batch_first=True))
            mask = self.put(
                torch.arange(k.size(1))[None, :] >= torch.tensor(sizes)[:, None]
            )
        elif kind == "owner":
            # Merge the template rows from multiple native states without mixing their candidate domains.
            lp, vs = zip(*items, strict=True)
            sizes = [len(x) for x in lp]
            width = max(x.size(1) for x in lp)
            logits = self.put(
                torch.cat(
                    [
                        torch.nn.functional.pad(
                            x, (0, width - x.size(1)), value=-torch.inf
                        )
                        for x in lp
                    ]
                )
            )
            vals = self.put(
                torch.cat(
                    [
                        torch.nn.functional.pad(x, (0, 0, 0, width - x.size(1)))
                        for x in vs
                    ]
                )
            )
        elif kind == "template":
            ctx, v, codes = zip(*items, strict=True)
            sizes = [len(x) for x in v]
            context = self.put(
                torch.cat([x.expand_as(y) for x, y in zip(ctx, v, strict=True)])
            )
            values = self.put(torch.cat(v))
            templates = self.put(torch.cat(codes))
        else:
            keys = []
            biases = []
            masks = []
            relation = []
            queries = []
            for bank, q, table, wires, prefix, nodes in items:
                if "resident" not in bank:
                    bank["resident"] = {
                        k: self.put(bank[k]) for k in ("flat", "bias", "tables")
                    }
                dev = bank["resident"]
                sizes.append(len(dev["flat"]))
                keys.append(dev["flat"])
                biases.append(dev["bias"])
                masks.append(dev["tables"] != table)
                queries.append(q)
                if wires:
                    if "fields" not in dev:
                        dev["fields"] = self.put(bank["fields"])
                    pri, src, col, ops = zip(*wires, strict=True)
                    if wires not in dev:
                        role = self.put(nodes[list(ops)][:, None, :])
                        raw = self.actor.latent(dev["fields"][:, list(col)]).tanh()
                        dev[wires] = (
                            role,
                            raw + 0.25 * self.actor.input_content(raw + role).tanh(),
                        )
                    role, k = dev[wires]
                    v = self.actor.latent(
                        dev["fields"][[prefix[j] for j in pri], list(src)]
                    ).tanh()
                    query = v + 0.25 * self.actor.query(v + role).tanh()
                    relation.append(
                        (query * k).sum(dim=(-1, -2)).sum(-1)
                        / math.sqrt(64 * len(wires))
                    )
                else:
                    relation.append(None)
            q = self.put(torch.stack(queries))
            k = pad_sequence(keys, batch_first=True)
            bias = pad_sequence(biases, batch_first=True)
            mask = pad_sequence(masks, batch_first=True, padding_value=True)
        self.times["assembly_and_relation_dispatch"] += perf_counter() - tic
        tic = perf_counter()
        timed = self.timed_kernels and self.metrics[kind + "_batches"] < 16
        if timed:
            begin, end = torch.mps.Event(True), torch.mps.Event(True)
            begin.record()
        if kind == "context":
            weights = (
                (torch.bmm(k, q.unsqueeze(-1)).squeeze(-1) / math.sqrt(32))
                .masked_fill(mask, -torch.inf)
                .softmax(1)
            )
            out = torch.bmm(weights.unsqueeze(1), vals).squeeze(1)
        elif kind == "owner":
            out = (logits.softmax(1)[:, :, None] * vals).sum(1)
        elif kind == "template":
            recipe = self.actor.input_role(templates)
            joint = self.actor.next_read(values, recipe.tanh())
            out = (self.actor.query(context + (values + joint)) * recipe).sum(
                -1
            ) / math.sqrt(32)
        else:
            raw = torch.bmm(k, q.unsqueeze(-1)).squeeze(-1) / math.sqrt(32) - bias
            lp = raw.masked_fill(mask, -torch.inf).log_softmax(-1)
            for i, r in enumerate(relation):
                if r is not None:
                    lp[i, : sizes[i]] = (lp[i, : sizes[i]] + r).log_softmax(0)
            out = lp
        if timed:
            end.record()
        host = out.cpu()
        if timed:
            end.synchronize()
            self.times[kind + "_sampled_device_seconds"] += (
                begin.elapsed_time(end) / 1000
            )
            self.metrics[kind + "_sampled_groups"] += 1
        self.times[kind + "_compute_and_collect"] += perf_counter() - tic
        if self.device != "cpu":
            self.metrics["download_bytes"] += host.nbytes
            self.metrics["readback_barriers"] += 1
        self.metrics[kind + "_batches"] += 1
        self.metrics[kind + "_items"] += len(items)
        self.metrics[kind + "_rows"] += sum(sizes)
        self.metrics[f"{kind}_batch_{len(items)}"] += 1
        if kind == "context":
            return host.unbind()
        return (
            host.split(sizes)
            if kind in ("template", "owner")
            else [host[i, :sz] for i, sz in enumerate(sizes)]
        )

    @torch.no_grad()
    def serve(self):
        while True:
            msg = self.queue.get()
            if msg is None:
                return
            msgs = [msg]
            deadline = perf_counter() + 0.0008
            while len(msgs) < self.capacity:
                try:
                    msgs.append(
                        self.queue.get(timeout=max(0, deadline - perf_counter()))
                    )
                except queue.Empty:
                    break
            groups = defaultdict(list)
            for kind, data, f in msgs:
                groups[kind].append((data, f))
            for kind, rows in groups.items():
                try:
                    result = self.run_group(kind, [d for d, _ in rows])
                    for (_, f), z in zip(rows, result, strict=True):
                        f.set_result(z)
                except Exception as err:  # noqa: BLE001 - propagate kernel failure to all waiting native sessions
                    for _, f in rows:
                        f.set_exception(err)

    def close(self):
        self.queue.put(None)
        self.thread.join()


@torch.no_grad()
def trial(a, case, device, capacity, cap):
    n, _, _ = setup(a, case)
    start = perf_counter()
    service = Batch(n, device, capacity)

    def one(seed):
        with torch.no_grad():
            return run_one(a, case, "cache", seed, cap, worker=service)

    try:
        with ThreadPoolExecutor(max_workers=capacity) as pool:
            runs = list(pool.map(one, (193, 307, 411, 509)))
    finally:
        service.close()
    elapsed = perf_counter() - start
    return {
        "device": device,
        "capacity": capacity,
        "paid_cap": cap,
        "wall": elapsed,
        "throughput": sum(r["ops"] for r in runs) / elapsed,
        "metrics": service.metrics,
        "times": service.times,
        "runs": runs,
    }


if __name__ == "__main__":
    torch.set_num_threads(1)
    a = args()
    case = os.environ["TR_CASE"]
    if os.getenv("IK_TIMED_KERNELS") == "1":
        r = trial(a, case, "mps", 4, 128)
        (output(a) / f"metal-events-{case}.json").write_text(json.dumps(r))
        raise SystemExit(0)
    for rep in range(2):
        for capacity in (1, 4) if rep == 0 else (4, 1):
            for device in ("cpu", "mps") if rep == 0 else ("mps", "cpu"):
                tag = "kvbatch" if os.getenv("IK_BATCH_KV") == "1" else "batch"
                p = output(a) / f"{tag}-{case}-{device}-{capacity}-{rep}.json"
                if not p.exists():
                    r = trial(a, case, device, capacity, 128)
                    p.write_text(json.dumps(r))
                    print(p.name, r["throughput"], flush=True)
