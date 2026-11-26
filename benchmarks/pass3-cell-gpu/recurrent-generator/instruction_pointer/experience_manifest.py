"""Unified decision index. Online observations and future labels occupy separate namespaces."""

import json
import sys
from pathlib import Path


def manifest(root):
    path = root / "experience.jsonl"
    with path.open("w") as out:
        for file in sorted(root.glob("experience/*/*/labels.json")):
            src = file.parent
            case, source = src.relative_to(root / "experience").parts
            frames = {}
            with (src / "frames.jsonl").open("rb") as data:
                while True:
                    pos = data.tell()
                    line = data.readline()
                    if not line:
                        break
                    frame = json.loads(line)
                    frames[frame["run"]] = (pos, frame["epoch"])
            autonomous = source == "self"
            pages = json.loads((src / "pages.json").read_text()) if autonomous else []
            label = {
                r["run"]: (i, r) for i, r in enumerate(json.loads(file.read_text()))
            }
            for i, p in enumerate(
                pages or [{"page": 0, "run": r} for r in sorted(label)]
            ):
                r = p["run"]
                offset, epoch = frames[r]
                if autonomous and epoch != p["epoch"]:
                    raise ValueError(
                        "decision did not observe the recorded publication"
                    )
                entry = label.get(r) if p["page"] == 0 else None
                base = src.relative_to(root)
                event = {
                    "id": [case, source, r, p["page"]],
                    "snapshot": {
                        "frames": str(base / "frames.jsonl"),
                        "publication_offset": offset,
                        "epoch": epoch,
                        "replay_from_start": True,
                    },
                    "behavior": {
                        "pages": str(base / "pages.json"),
                        "row": i,
                        "responses": str(base / "responses.json"),
                        "paid_before": p["paid_before"],
                        "submitted_ids": p["request_ids"],
                        "physical_slots": p["slot_budget"],
                        "policy": "frozen-D-seed536",
                    }
                    if autonomous
                    else None,
                    "offline": {"labels": str(file.relative_to(root)), "row": entry[0]}
                    if entry
                    else None,
                }
                out.write(json.dumps(event, separators=(",", ":")) + "\n")
    return path


if __name__ == "__main__":
    print(manifest(Path(sys.argv[1])))
