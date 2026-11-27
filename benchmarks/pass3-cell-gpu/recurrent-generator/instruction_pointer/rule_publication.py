"""Read objective, same-publication native rule observations without altering support."""

import json
import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory


@contextmanager
def publication_observer(enabled, admission=False):
    if not enabled:
        yield None, None, None
        return
    with TemporaryDirectory() as directory:
        path = Path(directory) / "rule-state.jsonl"
        admission_path = Path(directory) / "admission.csv" if admission else None
        env = {**os.environ, "EGGFUSE_QUERY_OBSERVER": str(path)}
        if admission_path:
            env["EGGFUSE_ADMISSION_OBSERVER"] = str(admission_path)
        path.touch()
        with path.open() as reader:
            yield reader, admission_path, env


def read_rule_frame(reader, frame):
    run, epoch, check, terminal, rules = json.loads(reader.readline())
    if (run, epoch, terminal) != (
        frame["run"],
        frame["epoch"],
        bool(frame.get("final_publication")),
    ) or [(rid, wm) for rid, wm, _ in rules] != list(map(tuple, frame["rules"])):
        raise ValueError("rule telemetry and CCP publication disagree")
    flags = {rid: (wm, dirty) for rid, wm, dirty in rules}
    if len(flags) != len(rules):
        raise ValueError("duplicate native rule")
    return flags, check


def menu_codes(w, snapshot, static, mode):
    """Two objective numeric lanes per proposed template's actual dispatch rule."""
    menu = snapshot["menu"]
    codes = static[menu]
    if mode == "none":
        return codes
    if mode not in ("dirty", "both", "wm"):
        raise ValueError(mode)
    flags = snapshot["rule_state"]
    values = [flags[w.layouts[t][0][0]] for t in menu]
    offset = codes.new_zeros(codes.shape)
    offset[:, :2] = codes.new_tensor(
        [
            (
                float(d) if mode != "wm" else 0.0,
                wm / (32.0 + wm) if mode != "dirty" else 0.0,
            )
            for wm, d in values
        ]
    ).reshape(-1, 2)
    return codes + offset
