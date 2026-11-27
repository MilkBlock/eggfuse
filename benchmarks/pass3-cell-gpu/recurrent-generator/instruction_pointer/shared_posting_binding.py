"""Frozen complete draws on independently verified, randomly addressed two-field domains."""

import json
import os
from collections import Counter
from pathlib import Path

import numpy as np
import torch

from binding_model import read_packet
from completion_context import read
from first_parent import records
from foundation_completion import Completion, Decision
from head_joint_index import prepare, draw
from partner_index import noise
from partner_index_worlds import args, frozen
from query_environment import conditioned
from selective_trials import inputs
from shared_posting import SparseCompletion, propose, PROPOSALS


@torch.no_grad()
def run(a):
    mdl = frozen(a, a.seeds[0])
    out = []
    base = Path(os.environ["ARTIFACT_ROOT"]) / "partner-index/worlds"
    for mode in ("hard", "multi"):
        for example in (511000, 511001):
            for flip in (0, 1):
                d = base / mode / f"1024-two-{example}-{flip}"
                z = read_packet(d / "binding.pkl")
                labels = {
                    tuple(z["addrs"][j][v] for j, v in enumerate(g)) for g in z["gold"]
                }
                prog = read(d / "program.json")
                inp = inputs(z, False)
                st = prepare(mdl, inp)
                decoders = [
                    Completion(mdl, "rule"),
                    SparseCompletion(mdl),
                    SparseCompletion(mdl, anchor=True),
                ]
                m = conditioned(a, d, d / "query.jsonl")
                try:
                    for line in (d / "public.jsonl").open():
                        f = json.loads(line)
                        f.pop("observed_fields", None)
                        m.update(f)
                        for dec in decoders:
                            dec.publish(m, prog, f, Counter())
                        if f["run"] == 2:
                            break
                    rid = z["rule"]
                    for arm in ("A", "B", "C", "C-anchor"):
                        rng = np.random.default_rng(7823)
                        root_ref = sorted(labels)[0][0]
                        offered = ""
                        if arm == "A":
                            root_pos = z["addrs"][0].index(root_ref)
                            rand = noise(np.random.default_rng(681), 128, 2)
                            roots = torch.full(
                                (1, 128), root_pos, device="mps", dtype=torch.int64
                            )
                            positions = (
                                st[1][0].draw(roots, rand[:, :, 1, 0])[0].cpu().tolist()
                            )
                            conditional = [
                                (root_ref, z["addrs"][1][v]) for v in positions
                            ]
                            ix = draw(inp, st, noise(rng, 128, 2))[0].cpu().tolist()
                            refs = [
                                tuple(z["addrs"][j][v] for j, v in enumerate(g))
                                for g in ix
                            ]
                        elif arm == "B":
                            dec = decoders[0]
                            refs = [
                                dec.finish(
                                    Decision(dec.net, rng, Counter()), fixed_rule=rid
                                )[1].refs
                                for _ in range(128)
                            ]

                            class ForcedFirst(Decision):
                                def pick(self, labels, *args, **kwargs):
                                    if self.prefix:
                                        value = self.prefix.pop(0)
                                        assert value in labels
                                        return value
                                    return super().pick(labels, *args, **kwargs)

                            oracle = ForcedFirst(
                                dec.net, np.random.default_rng(681), Counter()
                            )
                            conditional = []
                            for _ in range(128):
                                oracle.prefix = [dec.mem.lookup(root_ref)[0], root_ref]
                                conditional.append(
                                    dec.finish(oracle, fixed_rule=rid)[1].refs
                                )
                        else:
                            dec = decoders[1 if arm == "C" else 2]
                            refs = [c.refs for c in dec.bind(rid, 128, rng, Counter())]
                            tab, row = dec.mem.loc[root_ref[:2]]
                            bank = dec.mem.banks[tab]
                            assert bank.refs[row] == root_ref
                            prefix = [
                                (
                                    bank,
                                    torch.full(
                                        (128,), row, device="mps", dtype=torch.long
                                    ),
                                )
                            ]
                            source_rows = prefix[0][1]
                            tb = dec.mem.banks[dec.schemas[rid][0][1]]
                            wires = [
                                (bank, source_rows, sc, tc)
                                for sc, tc in dec.wiring[rid][0, 1]
                            ]
                            u = torch.from_numpy(
                                np.random.default_rng(681).random(
                                    (128, PROPOSALS, 5), dtype=np.float32
                                )
                            ).to("mps")
                            choices = propose(tb, wires, u).cpu().tolist()
                            offered = sum(
                                any((root_ref, tb.refs[i]) in labels for i in group)
                                for group in choices
                            )
                            conditional = [
                                c.refs
                                for c in dec.complete(
                                    rid,
                                    128,
                                    np.random.default_rng(681),
                                    Counter(),
                                    prefix,
                                )
                            ]
                        roots = {g[0] for g in labels}
                        out.append(
                            dict(
                                mode=mode,
                                example=example,
                                flip=flip,
                                arm=arm,
                                slots=len(refs),
                                given_first_proposal_hit=offered,
                                given_first_valid=sum(r in labels for r in conditional),
                                valid_first=sum(r[0] in roots for r in refs),
                                valid_token=sum(r in labels for r in refs),
                                distinct=len(set(refs) & labels),
                                targets=len(labels),
                            )
                        )
                finally:
                    m.close_observer()
                records(a.out / "binding.csv", out)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
