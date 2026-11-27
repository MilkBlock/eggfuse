"""Check sampled positive Page targets as the first and only native request of a Run."""

from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np

from control_credit_pairs import Forks
from credit_scale_fit import load_shard
from discovery_score import token, packet
from discovery_states import cli
from next_cell_train import read, write_json


def audit(a):
    rng = np.random.default_rng(61029)
    log = []
    for idx in sorted(rng.choice(200, size=24, replace=False)):
        x = read(a.out / "packets" / f"{idx:04d}.pkl.gz")
        samples = defaultdict(list)
        # Sample eligible states independently of the model score. Cover all available provenances.
        for bit in (1, 2, 4, 8, 16):
            choices = [
                (b, i)
                for b in x["blocks"]
                for i, v in enumerate(b["evidence"])
                if v & bit
            ]
            for j in rng.choice(len(choices), min(3, len(choices)), replace=False):
                b, i = choices[j]
                p, event = b["anchor"]
                samples[p].append((event, b["cells"][i], int(b["evidence"][i])))
        for p, selected in samples.items():
            sh = load_shard(Path(p))
            with TemporaryDirectory() as tmp:
                f = Forks(a, idx, Path(tmp), sh["program"])
                rows = []
                for j, e in enumerate(sh["events"]):
                    run = e["frame"]["run"]
                    targets = {(c, b) for k, c, b in selected if k == j}
                    if targets:
                        if f.call(rows, run - 1)["sha"] != e["semantic_state"]:
                            raise ValueError("prefix mismatch")
                        base = f.call(rows, run)
                        uid = max((q["token"] for q in rows), default=0) + 1
                        for c, bits in sorted(
                            targets, key=lambda t: (t[0].rule, t[0].refs)
                        ):
                            new = f.call([*rows, packet(c, run, uid)], run)
                            log.append(
                                dict(
                                    idx=int(idx),
                                    source=Path(p).name,
                                    run=run,
                                    rule=c.rule,
                                    refs=c.refs,
                                    bits=bits,
                                    accepted=new["counts"]["accepted"]
                                    == base["counts"]["accepted"] + 1,
                                    signed_origin=new["origins"].get(uid, 0),
                                    ops_delta=new["ops"] - base["ops"],
                                )
                            )
                    for label, replies in [
                        ("generated", "response"),
                        ("assisted", "assisted_response"),
                    ]:
                        rows.extend(
                            packet(token(c), run, r[0])
                            for c, r in zip(e[label], e[replies], strict=True)
                        )
    write_json(a.out / "first-request-audit.json", log)


if __name__ == "__main__":
    audit(cli().parse_args())
