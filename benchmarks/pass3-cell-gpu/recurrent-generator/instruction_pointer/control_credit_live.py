"""Two live CCP clients restore the same real exit and allocate one neural page before/after publication."""

import hashlib
import random
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import numpy as np
import torch

from control_credit_pairs import Forks, digest
from credit_scale_buffer import Lane, submit
from discovery_native import configure
from discovery_sampling import encode
from discovery_score import token
from discovery_states import read, save
from discrete_cells import from_q
from discrete_draft import plan
from execution_control import CONTINUE, SEAL, SUBMIT, representation
from execution_control_data import arguments


@torch.no_grad()
def branch(a, sh, e, now, seed):
    lane = Lane(a, sh["idx"], 2, sh["signature"])
    paid_pages = []
    try:
        _, _, page = configure(
            a, lane.m, "D", a.cap, lambda *args: (None, None, lane.page)
        )

        def issue(cells):
            ys = submit(lane.client, cells, 256)
            if ys:
                lane.m.observe_reply(plan(cells), dict(enumerate(ys)))
            return ys

        def draw(offset):
            start = perf_counter()
            before = page.count.copy()
            items = page.sample(
                lane.m, (), 1, np.random.default_rng(seed + offset), Counter()
            )
            gen = perf_counter() - start
            ys = issue([x.cell for x in items])
            paid_pages.append(
                {
                    "run": lane.client.run,
                    "gen_seconds": gen,
                    "submit_seconds": perf_counter() - start - gen,
                    "tokens": [encode(x.cell) for x in items],
                    "response": ys,
                    "device": dict(page.count - before),
                }
            )

        lane.advance()
        for w in sh["history"]:
            lane.m.update(lane.frame)
            r = w["run"]
            if r != lane.client.run or w["epoch"] != lane.client.epoch:
                raise ValueError("prefix schedule diverged")
            if w["reason"] == "teacher_prefix":
                replies = submit(
                    lane.client, list(map(from_q, w["selected"])), w["width"]
                )
                if replies != w["responses"]:
                    raise ValueError("teacher prefix receipts differ")
            draft = []
            last = []
            for act in w["actions"]:
                if r == e["run"] and act["action"] == SEAL:
                    break
                if act["action"] == CONTINUE:
                    draft.extend(map(token, act["tokens"]))
                    page.remaining = max(0, page.remaining - a.cap)
                elif act["action"] == SUBMIT:
                    y = issue(draft)
                    last = [row[1] for row in y]
                    if [v[0] for v in y] != act["ids"] or last != act["status"]:
                        raise ValueError("autonomous prefix receipts differ")
                    draft = []
            if r == e["run"]:
                assert not draft and act["action"] == SEAL
                x = representation(
                    lane.m, act["pages"], round(6 * act["x"][-5]), 0, act["sent"], last
                )
                torch.testing.assert_close(x, torch.tensor(act["x"]), rtol=0, atol=0)
                prefix = digest(
                    [list(lane.client.offline_tape(r)), lane.frame, act["x"]]
                )
                break
            lane.client.seal()
            lane.advance()
        start = perf_counter()
        if now:
            draw(0)
        lane.client.seal()
        lane.advance()
        if lane.done:
            raise ValueError("unmatched next publication")
        lane.m.update(lane.frame)
        if not now:
            draw(0)
        # Two common follow-up pages driven by each branch's actual Response.
        for offset in (1, 2):
            lane.client.seal()
            lane.advance()
            if lane.done:
                break
            lane.m.update(lane.frame)
            draw(offset)
        while not lane.done:
            lane.client.seal()
            lane.advance()
        elapsed = perf_counter() - start
        tape = list(lane.client.offline_tape(lane.terminal["runs"]))
        return {
            "prefix": prefix,
            "pages": paid_pages,
            "wall": elapsed,
            "sha": lane.terminal["state_sha"],
            "tape": tape,
        }
    finally:
        lane.close()


def run(a):
    a.pages = 6
    policy_sha = hashlib.sha256(a.checkpoint.read_bytes()).hexdigest()
    for idx in range(a.first, a.programs):
        cohort = "shuffle" if idx % 2 else ""
        sh = read((a.source or a.out) / cohort / "experience" / f"{idx}.json")
        path = a.out / "live" / f"{idx}.json"
        if path.exists():
            prior = read(path)
            for pair in prior:
                if (
                    pair.get("checkpoint", sh["checkpoint_sha256"]) != policy_sha
                    or pair.get("slots_per_page", 16) != a.cap
                    or pair.get("selection", [0, 2]) != [a.skip, a.pairs_per_program]
                ):
                    raise ValueError(
                        "saved pairs belong to another policy or sampling budget"
                    )
            continue
        eligible = [e for e in sh["history"][:-3] if e["reason"] == "exploration_seal"]
        rng = random.Random(9083 + idx)
        rng.shuffle(eligible)
        eligible.sort(key=lambda e: bool(e["actions"][-1]["sent"]) != (idx % 2 == 0))
        result = []
        with TemporaryDirectory() as t:
            f = Forks(a, idx, Path(t), sh["tape"]["program_sha256"])
            for e in eligible[a.skip : a.skip + a.pairs_per_program]:
                arms = {}
                for now in (True, False) if idx % 2 else (False, True):
                    b = branch(a, sh, e, now, 98311 * idx + e["run"])
                    rep = f.call(b.pop("tape"))
                    assert rep["sha"] == b["sha"]
                    b.update(facts=sorted(rep["facts"]), ops=rep["ops"])
                    arms["continue" if now else "seal"] = b
                left, right = arms["seal"], arms["continue"]
                assert (
                    left["prefix"] == right["prefix"]
                    and len(left["pages"]) == len(right["pages"]) == 3
                )
                result.append(
                    dict(
                        idx=idx,
                        checkpoint=policy_sha,
                        selection=[a.skip, a.pairs_per_program],
                        slots_per_page=a.cap,
                        signature=sh["signature"],
                        cohort=cohort or "neural",
                        run=e["run"],
                        stage=e["stage"],
                        paid_prefix=e["actions"][-1]["sent"],
                        gained=sorted(set(right["facts"]) - set(left["facts"])),
                        lost=sorted(set(left["facts"]) - set(right["facts"])),
                        **arms,
                    )
                )
        tmp = path.with_suffix(".tmp")
        save(tmp, result)
        tmp.replace(path)
        if idx % 10 == 0:
            print("paired CCP", idx, flush=True)


if __name__ == "__main__":
    p = arguments()
    p.add_argument("--first", type=int, default=0)
    p.add_argument("--source", type=Path)
    p.add_argument("--skip", type=int, default=0)
    p.add_argument("--pairs-per-program", type=int, default=2)
    a = p.parse_args()
    torch.set_num_threads(1)
    (a.out / "live").mkdir(exist_ok=True)
    run(a)
