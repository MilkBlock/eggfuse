"""Ablate state source and same-state omissions at fixed optimizer budgets."""

import json
from types import SimpleNamespace

import numpy as np
import torch

from address_scores import weight
from coverage_fit import BUDGETS, SEEDS
from coverage_onpolicy import coverage_gradient, freeze
from discovery_states import cli, read, save
from discrete_cells import from_q
from parallel_fit import TRAIN
from query_environment import conditioned, setup
from query_witnesses import groups
from recursive_train import folder


@torch.no_grad()
def load_states(a):
    cfg = SimpleNamespace(**(vars(a) | {"out": a.contract}))
    banks = {"teacher": [], "self": []}
    for case in sorted({c for c, _ in TRAIN}):
        for source, bank in banks.items():
            dest = a.out / "experience" / case / source
            labels = {p["run"]: p for p in read(dest / "labels.json")}
            observer = (
                dest / "state.jsonl"
                if source == "self"
                else a.contract / f"state-{case}-teacher.jsonl"
            )
            pages = (
                {p["run"]: p for p in read(dest / "pages.json") if p["page"] == 0}
                if source == "self"
                else {}
            )
            aliases = groups(cfg, case, "teacher", False) if source == "teacher" else {}
            m = conditioned(a, folder(a.data, case), observer)
            m.page = setup(cfg, m, "D", 256)[2]
            for line in (dest / "frames.jsonl").open():
                frame = json.loads(line)
                r = frame["run"]
                m.update(frame)
                if r not in labels:
                    continue
                if source == "self":
                    last, event, state, ctx = pages[r]["context"]
                    m.last = tuple(last) if last else None
                    m.event, m.state = torch.tensor(event), torch.tensor(state)
                    torch.testing.assert_close(
                        m.context(), torch.tensor(ctx), atol=0, rtol=0
                    )
                g = {}
                for q, gain in labels[r]["executed"]:
                    c = from_q(q)
                    for alt in [c, *aliases.get((r, c), ())]:
                        if alt in g and g[alt] != c:
                            raise ValueError("ambiguous native signature")
                        g[alt] = c
                extra = {from_q(q): from_q(q) for q, gain in labels[r]["omitted"]}
                if set(extra).intersection(g):
                    raise ValueError("omission overlaps executed signature")
                bank.append((case, r, freeze(m), g, g | extra))
            m.close_observer()
    return banks


def train(a):
    banks = load_states(a)
    print("states", {k: len(v) for k, v in banks.items()}, flush=True)
    gate = weight(a).to("mps").eval()
    aliases = {}
    for arm, with_self, omissions in (
        ("T", False, False),
        ("TO", False, True),
        ("TS", True, False),
        ("TSO", True, True),
    ):
        sources = ["teacher", "self"] if with_self else ["teacher"]
        if omissions and all(r[3] == r[4] for s in sources for r in banks[s]):
            aliases[arm] = arm[:-1]
            continue
        for seed in a.seeds:
            dest = a.out / "weights" / str(seed)
            dest.mkdir(parents=True, exist_ok=True)
            if (dest / f"{arm}.pt").exists():
                continue
            rng = np.random.default_rng(seed)
            sampling = np.random.default_rng(seed + 2)
            net = weight(a).to("mps")
            opt = torch.optim.AdamW(net.parameters(), lr=0.00015)
            history = []
            for step in range(a.updates):
                # Draw both bank indices on all arms to pair the entire schedule.
                teacher = banks["teacher"][rng.integers(len(banks["teacher"]))]
                own = banks["self"][rng.integers(len(banks["self"]))]
                use_self = with_self and step % 2 == 1
                case, r, m, executed, full = own if use_self else teacher
                b = int(rng.choice(BUDGETS))
                credit = full if omissions else executed
                loss, hit, slots, draws = coverage_gradient(
                    net, m, credit, gate, b, sampling
                )
                opt.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(
                    net.parameters(), 5, error_if_nonfinite=True
                )
                opt.step()
                history.append(
                    [
                        case,
                        "self" if use_self else "teacher",
                        r,
                        b,
                        hit,
                        slots,
                        draws,
                        len(credit),
                    ]
                )
            save(dest / f"{arm}.json", history)
            torch.save(net.cpu().state_dict(), dest / f"{arm}.pt")
            print("trained", arm, seed, len(history), flush=True)
    save(a.out / "aliases.json", aliases)


if __name__ == "__main__":
    p = cli()
    p.add_argument("--updates", type=int, default=256)
    p.add_argument("--seeds", nargs="+", type=int, default=SEEDS)
    a = p.parse_args()
    torch.set_num_threads(1)
    train(a)
