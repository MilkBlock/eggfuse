"""Matched readouts on A's published states, with A alone advancing the executor."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path
import torch
from protocol_experiment import dump
from protocol_learning import BoundaryRecorder, LearningStream, LearningPolicy
from protocol_model import ProtocolNet
from recursive_train import read, folder
from recursive_coverage import snapshot
from tempfile import TemporaryDirectory
from transaction_native import execute
from txn_policy import ResponseStream


class MatchedStudy(LearningPolicy):
    client_type = BoundaryRecorder

    def __init__(self, root, checkpoint):
        net = ProtocolNet().eval()
        net.load_state_dict(torch.load(checkpoint, weights_only=True))
        super().__init__(root, "B", net)
        self.stages = Counter()
        self.readouts = defaultdict(Counter)
        self.first = {}
        self.previous = {}

    def run_snapshot(self, frame, pub, rd, model, txn, stats, deadline):
        # A is the only writer. Named READ and COMPUTE cannot publish an RHS.
        for row in (*pub[0], *pub[2]):
            self.ports.pop(self.memory_address(*row[:2]), None)
        self.pending_masks = []
        self.rank_blocks = []
        txn.proof_results.clear()
        for rule, wm in frame["rules"]:
            self.stages["scheduled_rule_runs"] += 1
            s = MatchedStream(rd, model, rule, wm, stats, study=self)
            s.transaction = txn
            for paths in s.path_batches("stream", 0, deadline):
                if paths.shape[1] == 0:
                    self.pending_masks.append((rule, {}, len(paths)))
                txn.proofs_from_paths(s, paths)
        txn.flush()
        if txn.pending:
            txn.collect(txn.pending[-1])
        admitted = (
            torch.cat([torch.from_numpy(x) for x in txn.proof_results])
            if txn.proof_results
            else torch.empty(0, dtype=torch.bool)
        )
        ranked_hits = []
        at = 0
        for rule, masks, count in self.pending_masks:
            hits = admitted[at : at + count]
            at += count
            if not masks:
                self.stages["accepted_without_parents"] += int(hits.sum())
            else:
                ranked_hits.append(hits)
            for name, keep in masks.items():
                if name.startswith("postings_"):
                    self.stages[name] += int((hits & keep).sum())
                    continue
                self.readouts[name]["native_A_winners_retained"] += int(
                    (hits & keep).sum()
                )
                if (hits & ~keep).any() and name not in self.first:
                    self.first[name] = [txn.run, rule]
        assert at == len(admitted)
        if self.rank_blocks:
            scores = torch.cat(self.rank_blocks)
            hits = torch.zeros(len(scores), dtype=torch.bool)
            hits[scores[:, 0] >= 0] = (
                torch.cat(ranked_hits)
                if ranked_hits
                else torch.empty(0, dtype=torch.bool)
            )
            budget = min((scores >= 0).sum(0)).item()
            self.stages["matched_rank_budget"] += budget
            for col, name in enumerate(("A", "B")):
                order = scores[:, col].argsort(descending=True, stable=True)[:budget]
                self.readouts[name]["matched_budget_A_winners"] += int(
                    hits[order].sum()
                )


class MatchedStream(LearningStream):
    def select_query(self, success, occupancy, narrowed):
        b = super().select_query(success, occupancy, narrowed)
        self.study.stages["routed_computations"] += len(b)
        self.study.stages["B_reverts_to_direct"] += int((~b).sum())
        return torch.ones_like(b)

    def logits(self, h, depth, paths):
        a, z = ResponseStream.logits(self, h, depth, paths)
        st = self.study
        st.stages["root_scored" if not depth else "recursive_scored"] += len(a)
        if depth + 1 < len(self.roles):
            return a, z
        raw, enc, ok = self.read_values(depth, paths)
        meta = self.rd.meta(self.rule).expand(len(a), -1)
        state = torch.stack(
            (
                a.clamp(-12, 12) / 8,
                ok,
                self.tables[depth][0][paths[:, -1]],
                self.tables[depth][4][paths[:, -1], 4],
            ),
            1,
        )
        net = st.agent

        def score(x, state=state, base=a):
            return base + net.score(meta, net.value(x), state)

        swapped = raw.clone()
        for kind in range(6):
            ix = torch.where(raw[:, kind] != 0)[0]
            if len(ix):
                swapped[ix[0]] = st.previous.get(kind, raw[ix[0]])
                swapped[ix[1:]] = raw[ix[:-1]]
                st.previous[kind] = raw[ix[-1]].clone()
        # For the key intervention preserve the enumeration and replay every
        # prefix representation with bank and shared-column dot features erased.
        hx = self.model.start(meta[0]).expand(len(a), -1)
        for j in range(depth + 1):
            x = self.local(j, paths[:, : j + 1])
            x[:, : self.tables[j][1].shape[1] + 3] = 0
            masked, hx = self.model(hx, x)
        masked_state = state.clone()
        masked_state[:, 0] = masked.clamp(-12, 12) / 8
        tagless = raw.clone()
        kind = raw[:, :6].argmax(1)
        observed = torch.where(raw[:, :6].sum(1) > 0)[0]
        tagless[observed, 15 + (kind[observed] * 7) % 24] -= 1 / raw[
            observed, 6
        ].expm1().round().clamp_min(1)
        tagless[:, :6] = 0
        values = {
            "A": a,
            "B": a + net.score(meta, enc, state),
            "type_only": score(
                torch.cat((raw[:, :6], torch.zeros_like(raw[:, 6:])), 1)
            ),
            "no_type_tag": score(tagless),
            "same_type_replacement": score(swapped),
            "no_status": score(
                raw, torch.cat((state[:, :1], torch.zeros_like(state[:, 1:])), 1)
            ),
            "no_decision_keys": score(raw, masked_state, masked),
        }
        for name, s in values.items():
            keep = s >= 0
            r = st.readouts[name]
            r["complete_scored"] += len(keep)
            r["eligible_for_issue"] += int(keep.sum())
        st.rank_blocks.append(torch.stack((a, values["B"]), 1))
        issued = a >= 0
        if issued.any():
            masks = {name: (s[issued] >= 0) for name, s in values.items()}
            selected = paths[issued]
            linked = [(j, links[0]) for j, links in enumerate(self.links) if links]
            if linked:
                original = torch.ones(len(selected), dtype=torch.bool)
                perturbed = original.clone()
                for j, (i, c, d) in linked:
                    index = self.rd.index
                    src = torch.tensor([index.rows[k][2][c] for k in self.roles[i]])[
                        selected[:, i]
                    ]
                    dst = torch.tensor([index.rows[k][2][d] for k in self.roles[j]])[
                        selected[:, j]
                    ]
                    original &= src == dst
                    perturbed &= (src ^ 1) == dst
                masks.update(
                    postings_linked=torch.ones_like(original),
                    postings_original=original,
                    postings_flipped=perturbed,
                )
            st.pending_masks.append((self.rule, masks, len(selected)))
        return a, z


def main(root, out):
    torch.set_num_threads(1)
    results = {}
    for case in ("fact", "sum-divisors"):
        study = MatchedStudy(root, Path("run-recall/protocol-learning/model.pt"))
        m = execute(root, case, study=study, series="compute-shadow", seconds=300)
        prior = read(Path("run-recall/protocol-learning") / (case + ".json"))["arms"][
            "A"
        ][0]
        assert (
            m["state_sha"] == prior["state_sha"]
            and m["proof_paid"] == prior["proof_paid"]
        )
        assert (
            study.readouts["A"]["native_A_winners_retained"]
            + study.stages["accepted_without_parents"]
            == m["committed_tokens"]
        )
        dataset = folder(root, case)
        series = root / "protocol-ablation" / case
        with TemporaryDirectory() as tmp:
            first_state = None
            for run in range(1, prior["runs"] + 1):
                hashes = [
                    snapshot(
                        root,
                        dataset,
                        "replay",
                        series / arm / (case + "-stream-multi") / "issued.json",
                        run,
                        Path(tmp) / "state.json",
                    )[1]["state_sha"]
                    for arm in ("A", "B")
                ]
                if hashes[0] != hashes[1]:
                    first_state = run
                    break
        results[case] = dict(
            first_independent_A_B_state_difference=first_state,
            stages=study.stages,
            readouts=study.readouts,
            first_missed_A_winner=study.first,
            A_state=m["state_sha"],
        )
        dump(out, results)
        print(case, study.first, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("root", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    main(a.root, a.output)
