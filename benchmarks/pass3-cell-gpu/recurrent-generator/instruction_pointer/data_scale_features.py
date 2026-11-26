"""Factor frozen teacher-forced features by actual named request, before sampling plan bridges."""

import argparse
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch

from discrete_cells import Marks, from_q
from recursive_train import read
from response_study import memory


@torch.no_grad()
def encode(a, d):
    marks = Marks()
    rng = np.random.default_rng(7139)
    m = memory(a, d)
    req = read(d / "teacher.json")["requests"]
    groups = defaultdict(list)
    for i, q in enumerate(req):
        groups[q["run"]].append(i)
    xx = []
    yy = []
    offsets = []
    vectors = []
    state = []
    event = []
    run_ids = []
    for frame in map(json.loads, (d / "memory.jsonl").read_text().splitlines()):
        m.update(frame)
        ids = groups[frame["run"]]
        if not ids:
            continue
        input_tables = {t for r, _ in m.ids for t in m.roles[r]}
        output_tables = {t for r, _ in m.ids for t in m.output_tables[r].values()}
        if input_tables & output_tables:
            raise ValueError(
                "same-stage draft local ports require contextual feature encoding"
            )
        state.append(m.state)
        event.append(m.event)
        run_ids.append(frame["run"])
        for i in ids:
            assert i == len(vectors)
            c = from_q(req[i])
            labels = []
            got = marks.draw(m, rng, Counter(), target=c, records=labels)
            if got != c:
                raise ValueError(("teacher mark is unrepresentable", d, c, got))
            offsets.append((len(xx), len(labels)))
            vectors.append(m.embed(c))
            for x, y, _ in labels:
                xx.append(x)
                yy.append(y)
    packed = {
        "mark": torch.stack(xx),
        "label": torch.tensor(yy, dtype=torch.uint8),
        "offsets": torch.tensor(offsets),
        "vector": torch.stack(vectors),
        "state": torch.stack(state),
        "event": torch.stack(event),
        "runs": run_ids,
    }
    torch.save(packed, d / "work.pt")
    (d / "work.pt").replace(d / "features.pt")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--data", type=Path, default=Path("/tmp/dfm-local/data"))
    p.add_argument(
        "--actor", type=Path, default=Path("run-recall/higher-scaling/weights/actor.pt")
    )
    p.add_argument("--first", type=int, default=0)
    a = p.parse_args()
    torch.set_num_threads(1)
    i = a.first
    while True:
        d = a.out / "programs" / f"{i:04d}"
        if (d / "verified.json").exists():
            if not (d / "features.pt").exists():
                encode(a, d)
            if i % 20 == 0:
                print("encoded", i, flush=True)
            i += 1
        elif (a.out / "corpus.json").exists():
            break
        else:
            time.sleep(1)


if __name__ == "__main__":
    main()
