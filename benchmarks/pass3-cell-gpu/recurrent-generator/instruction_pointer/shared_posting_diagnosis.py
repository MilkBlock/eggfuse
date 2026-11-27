"""Offline forced-prefix decomposition. Gold addresses never reach the live generator."""

import json
from collections import Counter, defaultdict

import numpy as np
import torch

from binding_model import read_packet
from completion_context import read
from first_parent import records
from foundation_completion import Choice, Completion
from foundation_study import BASE, CASES
from partner_index_worlds import args, frozen
from query_environment import conditioned
from recursive_train import folder
from shared_posting import FieldPostings


@torch.no_grad()
def diagnose(a):
    out = []
    for case in CASES:
        model = frozen(a, a.seeds[0]).cpu()
        model.load_state_dict(
            torch.load(
                BASE / f"{case}-ce-count.pt", map_location="cpu", weights_only=True
            )
        )
        for source in (case, "rollout-" + case):
            path = BASE / "corpus" / source
            groups = defaultdict(list)
            for x in read_packet(path / "examples.pkl"):
                if x["z"] and x["g"]:
                    groups[x["run"]].append(x)
            rng = np.random.default_rng(635)
            runs = set(rng.choice(sorted(groups), min(18, len(groups)), replace=False))
            d = folder(a.data, case)
            m = conditioned(a, d, path / "observer")
            prog = read(d / "program.json")
            dec = Completion(model, "rule", "cpu")
            sparse = FieldPostings(model.mapping, "cpu")
            try:
                for line in (path / "frames").open():
                    f = json.loads(line)
                    if f.get("final_publication"):
                        continue
                    m.update(f)
                    dec.publish(m, prog, f, Counter())
                    sparse.publish(m, f, Counter())
                    if f["run"] not in runs:
                        continue
                    for x in groups[f["run"]]:
                        rid = x["rid"]
                        tabs, roles = dec.schemas[rid]
                        for g in rng.choice(
                            len(x["g"]), min(3, len(x["g"])), replace=False
                        ):
                            refs = [
                                x["z"]["addrs"][j][v] for j, v in enumerate(x["g"][g])
                            ]
                            for j, ref in enumerate(refs):
                                q = dec.ctx + dec.rkeys[dec.rpos[rid]] + roles[j]
                                bound = [dec.mem.lookup(v) for v in refs[:j]]
                                if bound:
                                    q = q + torch.stack([b[1] for b in bound]).mean(0)
                                q = q.tanh()
                                pgs, keys, bias = dec.page_options(tabs[j])
                                pg = dec.mem.lookup(ref)[0]
                                page = dec.mem.pages[pg]
                                pos = page.refs.index(ref)
                                pp = (
                                    Choice(q, keys, bias, 1)
                                    .logp(dec.net)[pgs.index(pg)]
                                    .exp()
                                )
                                zero = q.new_zeros(len(page.refs))
                                prior = Choice(q, page.keys, zero, 1).logp(dec.net)
                                dense = zero.clone()
                                sparse_score = zero.clone()
                                tb = sparse.banks[tabs[j]]
                                rows = torch.tensor(
                                    [sparse.loc[k[:2]][1] for k in page.refs]
                                )
                                wires = 0
                                for i, (_, _, source_fields) in enumerate(bound):
                                    sb = sparse.banks[tabs[i]]
                                    sx = sb.offsets[sparse.loc[refs[i][:2]][1]]
                                    for sc, tc in dec.wiring[rid][i, j]:
                                        wires += 1
                                        dense += 6 * (
                                            page.fields[:, tc] @ source_fields[sc]
                                        )
                                        ix = tb.offsets[rows] + tc
                                        # Same readout and temperature, both kernels normalized
                                        # to unit self-similarity; no posting proposal involved.
                                        delta = tb.lo[ix] - sb.lo[sx + sc]
                                        u, v = sb.frac[sx + sc], tb.frac[ix]
                                        dot = (
                                            (delta == 0) * ((1 - u) * (1 - v) + u * v)
                                            + (delta == 1) * u * (1 - v)
                                            + (delta == -1) * (1 - u) * v
                                        )
                                        norm = (
                                            (u.square() + (1 - u).square())
                                            * (v.square() + (1 - v).square())
                                        ).sqrt()
                                        sparse_score += 6 * (dot / norm).mean(-1)
                                rowp = (prior + dense).softmax(0)[pos]
                                out.append(
                                    dict(
                                        case=case,
                                        source=source,
                                        run=f["run"],
                                        rule=rid,
                                        role=j,
                                        wires=wires,
                                        pages=len(pgs),
                                        rows=len(page.refs),
                                        page_p=float(pp),
                                        conditional_row_p=float(rowp),
                                        end_p=float(pp * rowp),
                                        uniform_page=len(page.refs)
                                        / sum(len(dec.mem.pages[i].refs) for i in pgs),
                                        raw_mlp_p=float(prior.exp()[pos]),
                                        dense_field_only_p=float(dense.softmax(0)[pos]),
                                        sparse_same_readout_p=float(
                                            (prior + sparse_score).softmax(0)[pos]
                                        ),
                                        uniform_row=1 / len(page.refs),
                                    )
                                )
            finally:
                m.close_observer()
            if out:
                records(a.out / "diagnosis.csv", out)
            print(source, len(out), flush=True)


if __name__ == "__main__":
    torch.set_num_threads(1)
    diagnose(args())
