"""Free 64-slot draws on held-out policy states; exact forks only after generation."""

import json
import random
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
import torch

from control_credit_pairs import Forks
from coverage_eval import choices
from credit_scale_fit import load_shard
from discovery_sampling import Domain, seed_for
from discovery_score import packet, token, write_csv
from discovery_states import cli
from next_cell_train import read
from query_environment import conditioned


@torch.no_grad()
def test(a):
    rows = []
    for idx in range(256, 264):
        record = read(a.out / "packets" / f"{idx:04}.pkl.gz")
        eligible = [
            s
            for s in record["blocks"]
            if Path(s["anchor"][0]).name.split("-")[1] == "2"
        ]
        eligible.sort(key=lambda s: s["anchor"][1])
        selected = [eligible[i] for i in sorted({0, len(eligible) // 2})]
        path = Path(selected[0]["anchor"][0])
        if any(Path(s["anchor"][0]) != path for s in selected):
            raise ValueError("expected one held policy trajectory per program")
        sh = load_shard(path)
        targets = {b["anchor"][1]: b for b in selected}
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            obs = root / "observer.jsonl"
            obs.write_text("".join(json.dumps(x) + "\n" for x in sh["scheduler"]))
            m = conditioned(a, a.previous / "programs" / f"{idx:04}", obs)
            try:
                pages = {
                    (seed, arm): choices(a, m, arm, 64, seed)[2]
                    for seed in (9633, 5003)
                    for arm in ("ce200mixed", "ce200", "ce24", "initial")
                }

                def publish(f):
                    for page in pages.values():
                        page.publication(f)

                m.on_page_publication = publish
                fork = Forks(a, idx, root, sh["program"])
                prefix = []
                for j, e in enumerate(sh["events"]):
                    m.update(e["frame"])
                    r = e["frame"]["run"]
                    if j in targets:
                        torch.testing.assert_close(
                            m.context(), torch.tensor(e["context"]), atol=0, rtol=0
                        )
                        if fork.call(prefix, r - 1)["sha"] != e["semantic_state"]:
                            raise ValueError("held prefix mismatch")
                        b = targets[j]
                        classes = {
                            c: g
                            for g, (start, end) in enumerate(
                                zip(b["offsets"][:-1], b["offsets"][1:])
                            )
                            for c in b["cells"][start:end]
                        }
                        trials = []
                        domain = Domain(m)
                        for seed, arm in [
                            *pages,
                            (9633, "factored"),
                            (5003, "factored"),
                        ]:
                            noise = seed_for(r, seed)
                            cells = (
                                [
                                    v.cell
                                    for v in pages[seed, arm].sample(
                                        m,
                                        (),
                                        1,
                                        np.random.default_rng(noise),
                                        Counter(),
                                    )
                                ]
                                if arm != "factored"
                                else list(domain.draw(arm, random.Random(noise), 64))
                            )
                            trials.append((seed, arm, cells))
                        first = max((q["token"] for q in prefix), default=0) + 1
                        base = fork.call(prefix, r)
                        for seed, arm, cells in trials:
                            qs = [packet(c, r, first + i) for i, c in enumerate(cells)]
                            rep = fork.call(prefix + qs, r)
                            rows.append(
                                dict(
                                    program=idx,
                                    run=r,
                                    seed=seed,
                                    arm=arm,
                                    slots=64,
                                    complete=len(cells),
                                    accepted=rep["counts"]["accepted"]
                                    - base["counts"]["accepted"],
                                    distinct_known=len(
                                        {classes[c] for c in cells if c in classes}
                                    ),
                                    known=len(b["offsets"]) - 1,
                                    positive_requests=sum(
                                        rep["origins"].get(q["token"], 0) > 0
                                        for q in qs
                                    ),
                                    ops_delta=rep["ops"] - base["ops"],
                                )
                            )
                    for label, replies in [
                        ("generated", "response"),
                        ("assisted", "assisted_response"),
                    ]:
                        prefix.extend(
                            packet(token(c), r, res[0])
                            for c, res in zip(e[label], e[replies], strict=True)
                        )
            finally:
                m.close_observer()
    write_csv(a.out / "family-free.csv", rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    test(cli().parse_args())
