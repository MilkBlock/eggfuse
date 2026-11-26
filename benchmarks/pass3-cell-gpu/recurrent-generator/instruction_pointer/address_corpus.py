"""Offline query replay on witnessed local prefixes. No oracle tensors enter native generation."""

import gzip
import pickle

import torch

from draft_multitarget import snapshots
from metal_scaling import CASES
from parallel_budget import args
from parallel_fit import TRAIN


def files(a, split):
    return sorted((a.out / split).glob("*.pkl.gz"))


def read_state(path):
    with gzip.open(path, "rb") as f:
        return pickle.load(f)


@torch.no_grad()
def extract(m, g, case, run):
    domains = {}
    for tab in {-1} | {j for c in g for j in m.roles[c.rule]}:
        ids = m.ids if tab == -1 else m.rows[tab]
        live = (
            [True] * len(ids)
            if tab == -1
            else [k in m.pub.live and m.pub.live[k][0]["table"] == tab for k in ids]
        )
        keys = [m.graph(k) if tab == -1 else m.key(k) for k in ids]
        domains[tab] = {
            "keys": torch.stack(keys) if keys else torch.empty(0, 32),
            "live": live,
            "queries": [],
            "without_prefix": [],
            "without_reply": [],
            "gates": [],
        }
    seen = {}

    def add(
        tab,
        prefix,
        query,
        without_prefix,
        without_reply,
        copy=-1,
        project=-1,
        group=False,
        copykey=None,
        groupkey=None,
        slot=None,
    ):
        if prefix not in seen:
            d = domains[tab]
            seen[prefix] = len(d["queries"])
            d["queries"].append(query)
            d["without_prefix"].append(without_prefix)
            d["without_reply"].append(without_reply)
            d["gates"].append((copy, project, group, copykey, groupkey, slot))
        return seen[prefix]

    context = m.context()
    stripped = (
        (m.pub.total.float() / 16).asinh().tanh() + m.open_evidence + m.event
    ).tanh()
    add(-1, (), context, context, stripped)
    tokens = []
    for c in g:
        r = c.rule
        t = (r, c.higher)
        chain = [(-1, 0, m.ids_index.get(t, -1))]
        h = (context + m.graph(t)).tanh()
        h0 = h
        bare = (stripped + m.graph(t)).tanh()
        contract = m.owner_contract(r, c.refs[0]) if c.refs else {}
        for i, (ref, tab) in enumerate(zip(c.refs, m.roles[r], strict=True)):
            slot = m.enc.nodes[m.enc.cat.inputs["generated", r][i]]
            query = (h + slot).tanh()
            copy = m.index.get((tab, m.last), -1)
            project = (
                m.index.get((tab, (c.refs[0][0], contract[i])), -1)
                if i in contract
                else -2
            )
            switch = i == 1 and bool(contract)
            qi = add(
                tab,
                (r, c.higher, c.refs[:i]),
                query,
                (h0 + slot).tanh(),
                (bare + slot).tanh(),
                copy,
                project,
                switch,
                m.key(m.last) if copy >= 0 else None,
                m.key(c.refs[0][:2]) if switch else None,
                slot if switch else None,
            )
            entry = m.pub.live.get(ref[:2])
            y = (
                m.index.get((tab, ref[:2]), -1)
                if entry and entry[0]["table"] == tab and entry[0]["version"] == ref[2]
                else -1
            )
            chain.append((tab, qi, y))
            bare = m.enc.actor.next_read((m.key(ref[:2]) + slot)[None], bare[None])[0]
            h = m.enc.actor.next_read((m.key(ref[:2]) + slot)[None], h[None])[0]
        tokens.append((r, c.refs, chain))
    for d in domains.values():
        for name in ("queries", "without_prefix", "without_reply"):
            d[name] = (
                torch.stack(d[name]).numpy() if d[name] else torch.empty(0, 32).numpy()
            )
        d["keys"] = d["keys"].numpy()
        d["gates"] = [
            (c, p, s, *[v.numpy() if v is not None else None for v in features])
            for c, p, s, *features in d["gates"]
        ]
    return {"case": case, "run": run, "domains": domains, "tokens": tokens}


def main(a):
    for split, sources in (("train", TRAIN), ("eval", [(c, "teacher") for c in CASES])):
        if split not in a.splits:
            continue
        dest = a.out / split
        dest.mkdir(parents=True, exist_ok=True)
        for case, source in sources:
            for m, r, g in snapshots(a, case, source):
                with gzip.open(
                    dest / f"{case}-{source}-{r:04d}.pkl.gz", "wb", compresslevel=1
                ) as f:
                    pickle.dump(extract(m, g, case, r), f, protocol=5)


if __name__ == "__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        p = args()
        p.add_argument("--splits", nargs="+", default=["train", "eval"])
        main(p.parse_args())
