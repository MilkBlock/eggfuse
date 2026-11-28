"""Checkpoint-only CPU evaluation in a separate process, with metrics returned to the live journal."""

import io
import multiprocessing
import warnings
from concurrent.futures import ProcessPoolExecutor
from types import SimpleNamespace

import torch


@torch.no_grad()
def evaluate(options, weights):
    from continuous_trials import instrument
    from exposure_data import observed
    from exposure_worlds import world
    from prefix_train import make
    from scaling_archive import directory
    from scaling_eval import Sampling

    torch.set_num_threads(1)
    a = SimpleNamespace(**options)
    directory(a)  # Private native export directory for this evaluation.
    metrics = {}
    state = torch.load(io.BytesIO(weights), map_location="cpu", weights_only=True)
    for seed in (193, 307):
        net = make(a, "rel")
        w, align = world(a, net.actor, "loopfact")
        net.load_state_dict(state)
        net.eval()
        instrument(net, "exact")
        result, trace = observed(w, align, a, Sampling(net, 1.0, True), seed, 256)
        ops = {uid: row["effective_ops"] for uid, row in trace.entries.items()}
        for higher in trace.higher.values():
            ops.update((step["uid"], step["effective_ops"]) for step in higher["steps"])
        ordered = [ops[reply[0]] for *_, reply in trace.responses]
        paid = len(ordered)
        if sum(ordered) != result["ops"] or paid != result["stats"].get("paid", 0):
            raise ValueError("native paid-request ledger mismatch")
        prefix = f"native_256/loopfact_g{seed}_"
        metrics.update({prefix + k: result[k] for k in ("coverage", "eps", "ept")})
        metrics[prefix + "paid"] = paid
        first = next((i for i, op in enumerate(ordered, 1) if op > 0), None)
        if first is not None and first < paid:
            metrics[prefix + "continuation_ept"] = sum(ordered[first:]) / (paid - first)
    return metrics


class NativeChecks:
    def __init__(self, args, journal):
        self.options = {
            k: v
            for k, v in vars(args).items()
            if k not in ("native_export_dir", "_export_scratch")
        }
        self.pool = ProcessPoolExecutor(
            max_workers=1, mp_context=multiprocessing.get_context("spawn")
        )
        self.journal = journal

    def submit(self, net, exposure):
        snapshot = io.BytesIO()
        torch.save(net.state_dict(), snapshot)
        future = self.pool.submit(evaluate, self.options, snapshot.getvalue())

        def record(done):
            try:
                metrics = done.result()
            except Exception as exc:
                warnings.warn(f"Native evaluation at {exposure} failed: {exc}")
                metrics = {"native_256/check_failed": 1}
            self.journal.log(metrics, exposure)

        future.add_done_callback(record)

    def finish(self):
        self.pool.shutdown(wait=True)
