"""Account for the frozen historical Stream modules used in a real native control run."""

import json
from unittest.mock import patch

import torch

from competition_egg import egg
from cell_kv_runtime import native
from continuous_trials import CappedReference, reference
from partner_index_worlds import args
from scaling_archive import directory
from scaling_eval import Sampling, frozen
from scaling_fit import atomic


@torch.no_grad()
def run(a):
    modules = {}
    touched = {}

    class Audited(CappedReference):
        def run_snapshot(self, frame, pub, rd, model, txn, stats, deadline):
            modules.update(compose=model, prefix=self.prefix, field=rd.index.encoder)
            return super().run_snapshot(frame, pub, rd, model, txn, stats, deadline)

    def observe(m, inputs):
        for p in m.parameters(recurse=False):
            touched[id(p)] = p

    hook = torch.nn.modules.module.register_module_forward_pre_hook(observe)
    try:
        with patch("continuous_trials.CappedReference", Audited):
            r = reference(a, "loopfact", egg(a, "loopfact")[1], 193, 256)
    finally:
        hook.remove()
    actual = {}
    for component, m in modules.items():
        params = list(m.named_parameters())
        actual[component] = {
            "registered": sum(p.numel() for _, p in params),
            "forward_observed": sum(p.numel() for _, p in params if id(p) in touched),
            "tensors": [k for k, p in params if id(p) in touched],
        }
    atomic(
        directory(a) / "historical-parameters.json",
        {
            "method": "historical reference",
            "program": "loopfact",
            "seed": 193,
            "paid": r["paid"],
            "ops": r["ops"],
            "graph": r["graph"],
            "components": actual,
            "this_phase_training_exposures": 0,
            "this_phase_training_seconds": 0,
        },
    )
    d = directory(a)
    if json.loads((d / "campaign.json").read_text())["locked"]:
        blank = {}
        for case in ("loopfact", "sum-divisors"):
            net, w, ref = frozen(a, "sweep", case)
            trial = native(a, w, policy=Sampling(net, 1, True), seed=193, slots=6,
                           submit_pages=2, receipt_memory=True, rule_state=True,
                           reference=ref, paid_limit=0)
            if trial["stats"].get("paid", 0) or trial["stats"].get("neural_tokens", 0):
                raise ValueError("zero-budget native run issued a request")
            blank[case] = {k: trial[k] for k in ("graph", "facts", "ops", "covered", "reference")}
        atomic(d / "zero-paid.json", blank)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
