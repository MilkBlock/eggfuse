"""Static experiment specification and graph tensors. Source IDs never enter GNN features."""

import hashlib
import json
from pathlib import Path

from encoders import GraphSchema

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "corpus/manifest.json"
STEPS = 1536
BATCH = 32
SEEDS = (1703, 1709)
VALUE_CLASSES = 16


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Study:
    def __init__(self):
        self.templates = json.loads(MANIFEST.read_text())["templates"]
        self.train = [t for t in self.templates if t["split"] == "train"]
        self.held = [t for t in self.templates if t["split"] == "heldout"]
        if {t["family_id"] for t in self.train} & {t["family_id"] for t in self.held}:
            raise ValueError("held-out family leaked into training")
        self.schema = GraphSchema(self.train)
        self.rules = sorted({r for t in self.templates for r in t["rule_ids"]})
        self.columns = max(
            s[k] if k != "outputs" else len(s[k])
            for t in self.templates
            for s in t["stages"]
            for k in ("left_width", "right_width", "outputs")
        )

    def static(self, t):
        return (
            *(tuple(map(tuple, s["outputs"])) for s in t["stages"]),
            tuple(self.rules.index(r) for r in t["rule_ids"]),
        )
