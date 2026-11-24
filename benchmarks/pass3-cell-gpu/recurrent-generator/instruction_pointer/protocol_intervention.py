"""Independent rollouts with the trained decoder frozen and feedback channels ablated."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import torch

from protocol_experiment import CASES
from protocol_learning import LearningPolicy
from protocol_model import ProtocolNet
from recursive_coverage import Target, snapshot
from recursive_train import folder, read
from transaction_native import execute


class Intervention(LearningPolicy):
    def feedback(self, raw):
        if self.variant == "B-same-type":
            replacement = raw.clone()
            for kind in range(6):
                indices = torch.where(raw[:, kind] != 0)[0]
                if not len(indices):
                    continue
                replacement[indices[0]] = self.previous.get(kind, raw[indices[0]])
                replacement[indices[1:]] = raw[indices[:-1]]
                self.previous[kind] = raw[indices[-1]].clone()
            self.changed += int((replacement != raw).any(1).sum())
            return super().feedback(replacement)
        return super().feedback(torch.zeros_like(raw) if self.arm == "B" else raw)

    def controls(self, *args, **kwargs):
        x = super().controls(*args, **kwargs)
        if self.arm == "D":
            x[5] = 0
            x[9:] = 0
        return x


def run(root, dest, cases):
    torch.set_num_threads(1)
    output = {}
    for case in cases:
        d = folder(root, case)
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            target = Target(
                read(d / "program.json"),
                snapshot(root, d, "reference", "-", None, path)[0],
            )
            seed = target.match(snapshot(root, d, "reference", "-", 0, path)[0])
        output[case] = {}
        for variant in ("B", "B-same-type", "D"):
            arm = variant[0]
            net = ProtocolNet().eval()
            net.load_state_dict(torch.load(dest / "model.pt", weights_only=True))
            study = Intervention(
                root, arm, net, route="chain" if "stride" in case else "learned"
            )
            study.variant = variant
            study.previous = {}
            study.changed = 0
            series = "protocol-ablation/intervention-" + variant
            m = execute(root, case, study=study, series=series, seconds=240)
            out = root / series / (case + "-stream-multi")
            output[case][variant] = {
                "substituted_values": study.changed,
                "derived": len(target.match(read(out / "state.json")) - seed),
                "paid": m["paid"],
                "state_sha": m["state_sha"],
                "controls": m["work"].get("neural_controls", 0),
                "seal_early": m["work"].get("seal_before_exhaustion", 0),
                "accepted": m["verdicts"].get("accepted", 0),
                "observes": m["work"].get("neural_observe", 0),
                "queries": m["work"].get("response_queries", 0),
            }
        print(case, output[case], flush=True)
    (dest / "interventions.json").write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("dest", type=Path)
    p.add_argument("cases", nargs="*")
    a = p.parse_args()
    run(a.root, a.dest, a.cases or CASES)
