"""Link the previously verified EggCC/grammar bank without counting it as new collection."""

import gzip
import json
from collections import Counter
from types import SimpleNamespace

from discovery_sampling import encode
from discovery_states import cli
from query_witnesses import groups
from recursive_train import read


def archive(a):
    old = a.out.parent / "experience-ablation"
    cfg = SimpleNamespace(**(vars(a) | {"out": a.contract}))
    counts = Counter()
    with gzip.open(a.out / "historical-credit.jsonl.gz", "wt", compresslevel=1) as f:
        for path in sorted((old / "experience").glob("*/*/labels.json")):
            case, source = path.parent.parent.name, path.parent.name
            alias = groups(cfg, case, "teacher", False) if source == "teacher" else {}
            for s in read(path):
                classes = [
                    (encode(c), [encode(x) for x in sorted(v, key=lambda c: c.refs)])
                    for (r, c), v in alias.items()
                    if r == s["run"] and v
                ]
                counts["decision_states"] += 1
                counts["verified_equivalent_alternatives"] += sum(
                    len(xs) for _, xs in classes
                )
                counts["direct_omissions"] += len(s["omitted"])
                f.write(
                    json.dumps(
                        {
                            "case": case,
                            "source": source,
                            "run": s["run"],
                            "labels": str(path),
                            "epochs_and_pages": str(old / "experience.jsonl"),
                            "classes": classes,
                            "role": "historical",
                            "split": "quarantined_shared_EggCC_Rule_family",
                        }
                    )
                    + "\n"
                )
            if source == "self":
                for r in read(path.parent / "responses.json"):
                    counts[r["status"]] += 1
    (a.out / "archive.json").write_text(json.dumps(counts, indent=2) + "\n")
    print(counts)


if __name__ == "__main__":
    archive(cli().parse_args())
