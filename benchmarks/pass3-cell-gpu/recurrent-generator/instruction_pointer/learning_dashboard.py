"""Project completed runs with exact saved-checkpoint and asynchronous native measurements."""

import csv
import json
from collections import defaultdict

GROUPS = {
    "matched-end-to-end": "full-s71",
    "A-batched": "local-s71",
    "B-batched": "local-s71",
    "C-batched": "local-s71",
    "read-width-32": "full-s71",
    "read-width-64": "full-s71",
}


def joined(art, report, group, stem):
    directory = art / "continuation-exposure" / group
    journal = directory / (stem + "-live.jsonl")
    if not journal.exists():
        return {}
    rows = defaultdict(dict)
    if not group.startswith("read-width-"):
        sources = [report / "native-local-s71-t100000.csv"]
    else:
        sources = []
    sources += sorted(report.glob(f"native-{group}_{stem}-t*.csv"))
    for path in sources:
        if not path.exists():
            continue
        step = int(path.stem.rsplit("-t", 1)[1])
        with path.open() as f:
            for row in csv.DictReader(f):
                if (row["case"], row["cap"]) != ("loopfact", "256") or row.get("error"):
                    continue
                for key in ("coverage", "ept", "eps", "paid", "continuation_ept"):
                    if row.get(key):
                        rows[step][f"native_256/loopfact_g{row['seed']}_{key}"] = float(
                            row[key]
                        )
    with journal.open() as f:
        for line in f:
            if not line.endswith("\n"):
                break
            r = json.loads(line)
            if r.get("kind") == "metrics":
                rows[r["step"]].update(r["metrics"])
    return rows


def publish(sink, art):
    from cell_dashboard import REPORT, signature

    for group, stem in GROUPS.items():
        points = joined(art, REPORT / "matched-learning", group, stem)
        if points:
            sink.publish(
                "training and native " + group,
                signature(points),
                {
                    "source": str(art / "continuation-exposure" / group),
                    "training_seed": 71,
                    "native_program": "loopfact",
                    "generation_seeds": [193, 307],
                    "paid_cap": 256,
                    "step_unit": "actual cumulative complete Token exposures",
                },
                sorted(points.items()),
            )


if __name__ == "__main__":
    from cell_dashboard import DEFAULT_ART, DEFAULT_LOG, Sink, projection_lock

    with projection_lock(DEFAULT_LOG):
        sink = Sink(DEFAULT_LOG)
        try:
            publish(sink, DEFAULT_ART)
        finally:
            sink.db.close()
