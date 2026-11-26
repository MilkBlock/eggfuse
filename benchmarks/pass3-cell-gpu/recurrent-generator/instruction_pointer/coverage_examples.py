"""Offline complete-token normalizers, witnessed signature classes and real rollout failures."""

import gzip
import pickle
import random
from collections import Counter
from types import SimpleNamespace

import numpy as np
import torch

from address_corpus import extract
from address_scores import weight
from cell_transaction import STATUS
from discovery_sampling import Domain
from discovery_states import cli, save
from discrete_draft import Cell
from draft_dispatch import Dispatch
from draft_multitarget import snapshots
from parallel_fit import TRAIN
from query_environment import conditioned, setup
from query_examples import compile_paths
from query_fit import log_paths
from query_witnesses import groups
from recursive_train import folder
from transaction_native import execute


def dump(path, data):
    with gzip.open(path, "wb", compresslevel=1) as out:
        pickle.dump(data, out, protocol=5)


def pack(m, cells, gate, case, run):
    return compile_paths(extract(m, cells, case, run), [1] * len(cells), [], gate)


@torch.no_grad()
def examples(a):
    cfg = SimpleNamespace(**(vars(a) | {"out": a.contract}))
    gate = weight(a).to("mps").eval()
    donor = weight(a).to("mps").eval()
    donor.load_state_dict(torch.load(a.contract / "D.pt", weights_only=True))
    dest = a.out / "examples"
    dest.mkdir(exist_ok=True, parents=True)
    for case, src in TRAIN:
        aliases = groups(cfg, case, src, False)

        def build(args, d, case=case, src=src):
            m = conditioned(a, d, a.contract / f"state-{case}-{src}.jsonl")
            m.page = setup(cfg, m, "D", 256)[2]
            return m

        for m, r, gold in snapshots(a, case, src, build):
            path = dest / f"{case}-{src}-{r:04}.pkl.gz"
            if path.exists():
                continue
            domain = Domain(m)
            targets, sig, original = [], [], []
            for j, c in enumerate(gold):
                for x in [c, *sorted(aliases.get((r, c), ()), key=lambda v: v.refs)]:
                    targets.append(x)
                    sig.append(j)
                    original.append(True)
                    # Same native root request. Only that signed effect receives credit.
                    if (x.rule, True) in m.ids_index:
                        targets.append(Cell(x.rule, x.refs, True))
                        sig.append(j)
                        original.append(False)
            if len(set(targets)) != len(targets):
                raise ValueError("overlapping physical aliases across signatures")
            known = set(targets)
            if domain.size <= 512:
                other = [
                    c
                    for i in range(domain.size)
                    if (c := domain.decode(i)) not in known
                ]
                weights = np.ones(len(other))
                exact = True
            else:
                # Deterministic-mixture importance estimate of the *unknown complement*
                # of the complete-token partition. Failed donor slots contribute zero.
                k = 256
                rng = np.random.default_rng(7719 + r)
                freq = Counter(domain.draw("factored", random.Random(1991 + r), k))
                freq.update(i.cell for i in m.page.sample(m, (), 1, rng, Counter()))
                other = [c for c in freq if c not in known]
                counts = {(rule, h): n for rule, h, _, n in domain.entries}
                if other:
                    features = pack(m, other, gate, case, r)
                    p = (
                        log_paths(donor, features, np.arange(len(other)), "mps")
                        .prod(1)
                        .cpu()
                        .numpy()
                    )
                    weights = np.array(
                        [
                            freq[c]
                            / (k * (v + 1 / (len(counts) * counts[c.rule, c.higher])))
                            for c, v in zip(other, p, strict=True)
                        ]
                    )
                else:
                    weights = np.array([])
                exact = False
            state = pack(m, targets + other, gate, case, r)
            state.update(
                signature=np.array(sig),
                original=np.array(original),
                gains=np.array(list(gold.values())),
                importance=weights.astype(np.float32),
                exact=exact,
                domain=domain.size,
            )
            dump(path, state)
        print("packed", case, src, flush=True)


@torch.no_grad()
def failures(a):
    for case in sorted({c for c, _ in TRAIN}):
        collect_failures(a, case)


@torch.no_grad()
def collect_failures(a, case):
    cfg = SimpleNamespace(**(vars(a) | {"out": a.contract}))
    gate = weight(a).to("mps").eval()
    dest = a.out / "failures" / case
    dest.mkdir(parents=True, exist_ok=True)
    m = conditioned(a, folder(a.data, case), dest / "state.jsonl")
    marks, rates, _ = setup(cfg, m, "D", 16)
    tally = Counter()

    class TrainingRollout(Dispatch):
        def issue(self, items, txn, stats):
            before = self.m.context().clone()
            replies = super().issue(items, txn, stats)
            torch.testing.assert_close(before, self.m.context(), rtol=0, atol=0)
            bad = {}
            for item in items:
                st = STATUS[int(replies[item.uid][1])]
                c = item.cell
                tally[(st, c.rule)] += 1
                if st == "untriggered_rule":
                    assert not self.m.rule_features[self.m.rule_index[c.rule], 0]
                    bad[c] = "template"
                elif st == "binding":
                    bad[c] = "binding"
            # Stratify rare binding failures, keep all sampled 575 errors.
            if bad and (
                txn.run % 8 == 3
                or any(c.rule == 575 and v == "binding" for c, v in bad.items())
            ):
                cells = list(bad)
                packet = pack(self.m, cells, gate, case, txn.run)
                packet["kinds"] = list(bad.values())
                packet["rules"] = [(c.rule, c.higher) for c in cells]
                dump(
                    dest / f"page-{int(next(iter(replies.values()))[0])}.pkl.gz",
                    packet,
                )
            return replies

    policy = TrainingRollout(m, marks, {"flow": rates}, "empty", 1, 536, 2, mode="page")
    try:
        x = execute(
            a.data,
            case,
            study=policy,
            series=str(dest),
            seconds=300,
            runtime_binary=a.runtime_binary,
            observer_path=m.observer_path,
        )
    finally:
        m.close_observer()
    save(
        dest / "receipts.json",
        {
            "paid": x["paid"],
            "state_sha": x["state_sha"],
            "counts": [[k, r, n] for (k, r), n in sorted(tally.items())],
        },
    )
    print("failures", case, x["paid"], tally["binding", 575], flush=True)


if __name__ == "__main__":
    p = cli()
    p.add_argument("mode", choices=["examples", "failures"])
    a = p.parse_args()
    torch.set_num_threads(1)
    (examples if a.mode == "examples" else failures)(a)
    torch.mps.synchronize()
