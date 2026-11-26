"""Spend the same number of named neural requests now or after the next publication."""

import gzip
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from itertools import chain
from pathlib import Path
from tempfile import TemporaryDirectory

from control_credit_pairs import Forks, difference, event_requests
from discovery_states import read
from execution_control import CONTINUE, SEAL
from execution_control_data import arguments


def accounted(result):
    c = result["counts"]
    return c["accepted"] + c["duplicates"] + sum(c["rejected"].values())


def allocation_target(delta, exact_counts):
    if not delta["same_schedule"] or not exact_counts:
        return None
    if delta["gained"] and not delta["lost"]:
        return CONTINUE
    if delta["lost"] and not delta["gained"]:
        return SEAL
    return None


def timing(a, cohort, idx):
    name = f"{cohort}-{idx:04d}.json.gz"
    path = a.out / "allocation" / name
    if path.exists():
        return
    with gzip.open(a.out / "ledger" / name) as inp:
        sh = json.load(inp)
    raw = read(
        a.out
        / ("shuffle" if cohort == "shuffle" else "")
        / "experience"
        / f"{idx}.json"
    )
    accepted = {q["token"]: q for q in raw["tape"]["requests"]}
    blocks = [event_requests(e, accepted)[0] for e in raw["history"]]
    records = []

    def page(w):
        return next(
            (
                (i, act)
                for i, act in enumerate(w["control_events"])
                if act["action"] == CONTINUE
                and not act["draft"]
                and act["generated"] > 0
            ),
            None,
        )

    with TemporaryDirectory() as t:
        f = Forks(a, idx, Path(t), sh["program"])
        for j, (w, v) in enumerate(zip(sh["windows"], sh["windows"][1:])):
            left, right = page(w), page(v)
            if not left or not right or right[1]["sent"]:
                continue
            i, first = left
            _, second = right
            k = min(first["generated"], second["generated"], a.cap)
            cut = first["sent"]
            prefix = list(chain.from_iterable(blocks[:j])) + blocks[j][:cut]
            pre = blocks[j][cut : cut + k]
            post = blocks[j + 1][:k]
            assert len(pre) == len(post) == k
            suffix = list(chain.from_iterable(blocks[j + 2 :]))
            arms = [prefix + pre, prefix + post]
            # Alternate branch execution order, including long-horizon measurement.
            order = (0, 1) if (idx + j) % 2 else (1, 0)
            now = {}
            end = {}
            for arm in order:
                now[arm] = f.call(arms[arm], w["run"] + 1)
                end[arm] = f.call(arms[arm] + suffix)
            due = all(
                accounted(now[n]) == len(arms[n])
                and accounted(end[n]) == len(arms[n]) + len(suffix)
                for n in order
            )
            terminal = difference(end[1], end[0])
            records.append(
                {
                    "run": w["run"],
                    "action_index": i,
                    "state": first["state"],
                    "paid_each": k,
                    "pages_each": 1,
                    "prefix_paid": len(prefix),
                    "suffix_paid": len(suffix),
                    "pre": pre,
                    "post": post,
                    "generation_seconds": [
                        first["generation_seconds"],
                        second["generation_seconds"],
                    ],
                    "direct": difference(now[1], now[0]),
                    "terminal": terminal,
                    "receipts_accounted": due,
                    "target": allocation_target(terminal, due),
                }
            )
        # Independently verify every original same-Token delayed comparison by
        # counting all paid requests in both arms, and collect the actual native
        # verdicts on the delayed batch with the identical delayed prefix.
        delays = []
        for rec in sh["pairs"]:
            if "delay" not in rec:
                continue
            j = rec["run"] - 1
            r = rec["delay"]["run"]
            base = (
                list(chain.from_iterable(blocks[:j])) + blocks[j][: rec["paid_prefix"]]
            )
            batch = rec["batch"]
            intervening = list(chain.from_iterable(blocks[j + 1 : r - 1]))
            suffix = list(chain.from_iterable(blocks[r - 1 :]))
            later = [dict(q, run=r) for q in batch]
            cut = base + intervening
            clock = f.call(cut, r)
            spent = f.call(cut + later, r)
            whole = f.call(cut + later + suffix)
            early = f.call(base + batch + intervening + suffix)
            if not (
                early["sha"] == rec["terminal"]["continue_hash"]
                and whole["sha"] == rec["delay"]["delta"]["seal_hash"]
            ):
                raise ValueError("delayed fork not reproducible")

            def counts(v):
                c = v["counts"]
                return Counter(
                    {
                        **c["rejected"],
                        "accepted": c["accepted"],
                        "duplicate": c["duplicates"],
                    }
                )

            statuses = counts(spent)
            statuses.subtract(counts(clock))
            accounted_pair = (
                accounted(early)
                == accounted(whole)
                == len(base) + len(batch) + len(intervening) + len(suffix)
                and all(n >= 0 for n in statuses.values())
                and sum(statuses.values()) == len(batch)
            )
            delays.append(
                {
                    "state": rec["state"],
                    "origin": rec["origin"],
                    "run": rec["run"],
                    "later_run": r,
                    "verdicts": {k: v for k, v in statuses.items() if v},
                    "paid": len(batch),
                    "accounted": accounted_pair,
                }
            )
    with gzip.open(path.with_suffix(".tmp"), "wt") as out:
        json.dump({"records": records, "delays": delays}, out, separators=(",", ":"))
    path.with_suffix(".tmp").replace(path)


if __name__ == "__main__":
    p = arguments()
    p.add_argument("--workers", type=int, default=4)
    a = p.parse_args()
    (a.out / "allocation").mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        for i, _ in enumerate(
            pool.map(
                lambda v: timing(a, *v),
                [(c, i) for c in ("neural", "shuffle") for i in range(a.programs)],
            )
        ):
            if i % 20 == 0:
                print("matched budgets", i, flush=True)
