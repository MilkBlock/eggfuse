"""Offline decomposition of subset selection into opcode admissibility and sampled decisions."""

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from recursive_train import binary, folder, read


def audit(data, out):
    rows = []
    with TemporaryDirectory(dir=out) as tmp:
        frames = Path(tmp) / "memory.jsonl"
        for p in sorted(
            p
            for arm in ("set", "relative")
            for p in (out / "paired").glob(f"*-{arm}-0/*.json")
        ):
            if p.stem in ("ref", "prefix"):
                continue
            x = read(p)
            cmd = [
                binary(data),
                "replay",
                folder(data, x["case"]) / "program.json",
                p.parent / (p.stem + "-stream-multi") / "issued.json",
                "time",
                "--memory",
                frames,
            ]
            replay = json.loads(subprocess.check_output(cmd))
            assert replay["state_sha"] == x["state_sha"]
            with frames.open() as f:
                schedule = {
                    v["run"]: dict(v["rules"]) for line in f if (v := json.loads(line))
                }
            counts = Counter()
            for page in x["pages"]:
                selected = set(page["selected"])
                alphabet = schedule[page["run"]]
                admissible = [
                    u
                    for u, r in zip(page["uids"], page["rules"], strict=True)
                    if r in alphabet
                ]
                assert selected <= set(admissible)
                counts["outside_current_opcodes"] += len(page["uids"]) - len(admissible)
                counts["in_current_opcodes"] += len(admissible)
                counts["deferred_by_position_sampler"] += len(admissible) - len(
                    selected
                )
                counts["later_selected_with_earlier_admissible_deferred"] += int(
                    any(
                        u not in selected
                        and any(v in selected for v in admissible[i + 1 :])
                        for i, u in enumerate(admissible)
                    )
                )
                counts["multiple_selected"] += len(selected) > 1
            rows.append(
                {
                    "case": x["case"],
                    "arm": x["arm"],
                    "device": p.parent.name.split("-")[0],
                    "counts": dict(counts),
                }
            )
    (out / "published" / "position-mask.json").write_text(
        json.dumps(rows, indent=1) + "\n"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("data", "out"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    audit(args.data, args.out)
