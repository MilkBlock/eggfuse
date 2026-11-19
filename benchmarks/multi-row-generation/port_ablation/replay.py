"""CPU-only replay of saved held-out traces, binding routes to actual emitted tokens."""

import argparse
import json
from pathlib import Path
import sys

import numpy as np

from data import audit, dataset

HERE = Path(__file__).resolve().parent


def ordered_projection(left, right, ptr, routes):
    g = np.arange(len(left))[:, None]
    selected = (left[g, ptr[..., 0]], right[g, ptr[..., 1]])
    return np.stack(
        [
            selected[side][..., col] if side != 2 else np.full(ptr.shape[:2], col, dtype=np.int32)
            for side, col in routes
        ],
        axis=-1,
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("--capacity", action="store_true")
    args = p.parse_args()
    prefix = "capacity" if args.capacity else "results"
    traces = args.root / ("capacity-traces" if args.capacity else "traces")
    result = json.loads((args.root / f"{prefix}.json").read_text())
    total = 0
    for t in json.loads((HERE / "corpus/manifest.json").read_text())["templates"]:
        if t["split"] != "heldout":
            continue
        d = dataset("collision", t)
        for name in result["fits"]:
            with np.load(traces / f"{t['id']}-{name}.npz", allow_pickle=False) as z:
                first, second = (
                    {k: z[f"{s}_{k}"] for k in ("active", "pointers", "rows")} for s in (0, 1)
                )
                token = z["token"]
                w = 32
                assert np.isfinite(token).all()
                for width, value in [
                    (2, first["active"]),
                    (8, first["pointers"][..., 0]),
                    (8, first["pointers"][..., 1]),
                ]:
                    np.testing.assert_array_equal(token[..., w : w + width], np.eye(width)[value])
                    w += width
                cols = len(t["stages"][0]["outputs"])
                parent = token[..., w : w + cols]
                np.testing.assert_array_equal(parent, first["rows"])
                np.testing.assert_array_equal(
                    first["rows"],
                    ordered_projection(
                        d["a"], d["b"], first["pointers"], t["stages"][0]["outputs"]
                    ),
                )
                np.testing.assert_array_equal(
                    second["rows"],
                    ordered_projection(
                        parent, d["requests"], second["pointers"], t["stages"][1]["outputs"]
                    ),
                )
                actual = audit(d, first, second)
                stored = result["panels"][t["id"] + "/collision"][name]
                for stage in ("run1", "run2"):
                    assert {k: v for k, v in actual[stage].items() if k != "per_graph"} == stored[
                        stage
                    ]
                assert [int(g["complete"]) for g in actual["run2"]["per_graph"]] == stored[
                    "complete_by_graph"
                ]
                total += len(token)
    assert "torch" not in sys.modules
    print(
        json.dumps(
            dict(trace_occurrences=total, two_run_lineage="verified", tensor_runtime_imported=False)
        )
    )


if __name__ == "__main__":
    main()
