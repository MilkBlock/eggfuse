"""Content-addressed corpus ledger. Optimizer exposures are reported separately."""

import argparse
from collections import Counter
from pathlib import Path
from next_cell_train import read, write_json
from next_cell_corpus import digest
from credit_scale_fit import load_shard


def inventory(a):
    sources = {}
    by_mode = {}
    for root in [
        a.buffer_root,
        a.buffer_root / "diverse",
        a.buffer_root / "fine",
        a.dual,
        a.buffer_root / "held",
    ]:
        count = Counter()
        stages = Counter()
        for f in sorted((root / "buffer").glob("*.json.gz")):
            sh = load_shard(f)
            evidence = {
                k: digest(p.read_bytes())
                for k in ("credit", "page-dual")
                if (p := root / k / f.name).exists()
            }
            sources[str(f)] = dict(sha256=digest(f.read_bytes()), sidecars=evidence)
            count["files"] += 1
            count["repair_events"] += len(sh["repair_events"])
            for e, s in zip(sh["events"], sh["scheduler"]):
                count["issued_on_pure" if sh["branch"] == 2 else "issued_on_mixed"] += (
                    len(e["generated"])
                )
                count["replayed_shuffle_or_random_supplements"] += len(e["assisted"])
                count["publications"] += bool(e["frame"]["updates"])
                count["retirement_frames"] += bool(e["frame"]["retired"])
                count["disabled_rule_frames"] += any(not dirty for _, _, dirty in s[-1])
                count["versioned_update_frames"] += any(
                    row["version"] > 0 for _, row in e["frame"]["updates"]
                )
                count["runs"] += 1
                stages[str(s[2])] += 1
        by_mode[str(root)] = dict(counts=count, enabled=stages)
    signature = {}
    by_split = {}
    for split, files in [("train", range(200)), ("held", range(256, 264))]:
        totals = Counter()
        for idx in files:
            path = a.out / "packets" / f"{idx:04}.pkl.gz"
            x = read(path)
            signature[idx] = x["signature"]
            totals.update(x["counts"])
        by_split[split] = totals
    if {signature[k] for k in range(200)} & {signature[k] for k in range(256, 264)}:
        raise ValueError("shared topology")
    write_json(a.out / "sources.json", sources)
    write_json(
        a.out / "inventory.json",
        dict(
            by_source=by_mode,
            by_split=by_split,
            normalized_signatures=signature,
            source_ledger_sha256=digest((a.out / "sources.json").read_bytes()),
            packet_bytes=sum(
                p.stat().st_size for p in (a.out / "packets").glob("*.pkl.gz")
            ),
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for field in ("out", "buffer-root", "dual"):
        p.add_argument("--" + field, required=True, type=Path)
    inventory(p.parse_args())
