"""Join every signed request with the native scheduler row at generation time."""

import argparse
import json
from collections import Counter
from pathlib import Path

from cell_transaction import STATUS
from credit_scale_fit import load_shard


def audit(folder):
    result = Counter()
    for path in sorted((folder / "buffer").glob("*.json.gz")):
        sh = load_shard(path)
        runs = {r[0]: r for r in sh["scheduler"] if not r[3]}
        if len(runs) != len(sh["events"]):
            raise ValueError("missing schedule observation")
        for event in sh["events"]:
            f = event["frame"]
            _run, epoch, check, _, rules = runs[f["run"]]
            assert epoch == f["epoch"] and [x[:2] for x in rules] == f["rules"]
            dirty = {r: d for r, w, d in rules}
            result["decisions"] += 1
            result["rule_rows"] += len(rules)
            result["clean"] += sum(not v for v in dirty.values())
            result["check_disabled"] += not check
            phase = (
                "mixed"
                if any(dirty.values()) and not all(dirty.values())
                else "all_dirty"
                if any(dirty.values())
                else "none_dirty"
            )
            result[phase + "_frames"] += 1
            result[phase + "_tokens"] += len(event["generated"])
            result[phase + "_with_exact_bindings"] += int(event["known_bindings"] > 0)
            for c, r in zip(event["generated"], event["response"], strict=True):
                clean = not dirty[c[0]]
                rejected = STATUS[r[1]] == "untriggered_rule"
                if rejected != bool(check and clean):
                    raise ValueError("admission state drift")
                result["signed"] += 1
                result["clean_signed"] += clean
                result["untriggered"] += rejected
                result[phase + "_untriggered"] += rejected
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("folder", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    a.output.write_text(json.dumps(audit(a.folder), indent=2) + "\n")
