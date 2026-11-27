"""Count productive issued requests at their actual native snapshot, excluding unissued omissions."""

import gzip
import hashlib
import json
import os
import pickle
from collections import Counter, defaultdict
from pathlib import Path

from joint_cell_replay import target
from partner_index_worlds import args
from scaling_archive import directory, load


def collect(a):
    d = directory(a)
    root = Path(os.environ["ARTIFACT_ROOT"])
    counts = defaultdict(Counter)
    provenance = Counter()
    for entry in map(json.loads, (d / "archive.jsonl").read_text().splitlines()):
        path = root / entry["path"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != entry["sha"]:
            raise ValueError("archive changed since native verification")
        shard = load(path)
        effects = dict(shard["origins"])
        for i, src, sha, _, _ in entry["states"]:
            event = shard["events"][i]
            reply = "response" if src == "generated" else "assisted_response"
            for raw, rec in zip(event[src], event[reply], strict=True):
                if not rec[1] and effects.get(rec[0], 0) > 0:
                    counts[entry["program"], sha][target(raw)] += 1
                    provenance[src, shard["branch"]] += 1
    tmp = d / "issued-frequency.tmp"
    with gzip.open(tmp, "wb", compresslevel=4) as f:
        pickle.dump(dict(counts), f)
    tmp.replace(d / "issued-frequency.pkl.gz")
    (d / "issued-frequency.json").write_text(
        json.dumps(
            {
                "states": len(counts),
                "programs": len({k[0] for k in counts}),
                "state_named_tokens": sum(map(len, counts.values())),
                "productive_occurrences": sum(sum(c.values()) for c in counts.values()),
                "by_source_branch": {str(k): v for k, v in provenance.items()},
            }
        )
    )


if __name__ == "__main__":
    collect(args())
