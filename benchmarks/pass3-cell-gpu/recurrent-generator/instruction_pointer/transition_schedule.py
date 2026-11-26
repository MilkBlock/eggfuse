"""Attribute actual native untriggered receipts to scheduled alternatives offline."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def count(path):
    result = Counter()
    v = json.loads(path.read_text())
    if v["block"] or v["case"].startswith("grammar"):
        return {}
    flags = {
        r: [d for _, _, d in rules]
        for r, _, check, end, rules in map(
            json.loads, (path.parent / "state.jsonl").open()
        )
        if check and not end
    }
    previous = 0
    for x in v["trace"]:
        n = x["replies"].get("untriggered_rule", 0)
        ds = flags[x["run"]]
        kind = "some_dirty" if any(ds) else "none_dirty"
        result[kind] += n - previous
        previous = n
    assert sum(result.values()) == v["verdicts"].get("untriggered_rule", 0)
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    rows = []
    for path in a.root.glob("native/*/*/native-address/*/mixed-n480-u1920-*/run.json"):
        counts = count(path)
        if counts:
            v = json.loads(path.read_text())
            rows.append(
                dict(seed=path.relative_to(a.root).parts[1], case=v["case"], **counts)
            )
    with a.output.open("w") as f:
        w = csv.DictWriter(
            f, ["seed", "case", "none_dirty", "some_dirty"], lineterminator="\n"
        )
        w.writeheader()
        w.writerows(rows)
