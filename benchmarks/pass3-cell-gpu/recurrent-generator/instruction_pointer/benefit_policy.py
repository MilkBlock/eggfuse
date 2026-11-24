"""Counterfactual computation policy with fixed source Run boundaries."""

from time import perf_counter
import numpy as np
import torch
from torch import nn
from protocol_learning import LearningPolicy, LearningStream
from protocol_model import RAW, WIDTH, ProtocolNet, decode
from recursive_agent import Compose
from txn_policy import ResponseStream, plans


class BenefitNet(ProtocolNet):
    graph_operands = True

    def __init__(self):
        super().__init__()
        # No Observe/Seal/Submit head is called or fitted in this experiment.
        del (
            self.scope,
            self.boundary,
            self.query,
            self.proof,
            self.structure,
            self.status,
        )
        self.operand = nn.Sequential(nn.Linear(6, 16), nn.Tanh(), nn.Linear(16, 1))
        self.timing = nn.Sequential(nn.Linear(5, 24), nn.Tanh(), nn.Linear(24, 1))
        self.correction = nn.Sequential(
            nn.Linear(WIDTH + 24 + 4 + 1, 32), nn.Tanh(), nn.Linear(32, 1)
        )
        nn.init.zeros_(self.correction[-1].weight)
        nn.init.zeros_(self.correction[-1].bias)
        self.compose = Compose()

    def prediction(self, meta, z, raw, base, has, arm):
        v = self.value(raw) * has[:, None]
        corr = self.correction(torch.cat((meta, z, v, has[:, None]), 1)).flatten()
        # Residual may recover additional proofs without vetoing an existing
        # final decision on the same path. Subsequent states can still diverge.
        return base + (corr.clamp(min=0) if arm == "residual" else corr)


class BenefitPolicy(LearningPolicy):
    def __init__(
        self, root, net, arm, base_route="learned", collect=False, *, activate=False
    ):
        super().__init__(root, "B", net, collect, base_route)
        self.variant = arm
        self.examples = []
        self.activate = activate

    def run_snapshot(self, frame, pub, rd, model, txn, stats, deadline):
        for rule, wm in frame["rules"]:
            if self.activate or self.collect:
                stream = getattr(self, "stream_class", BenefitStream)(
                    rd, self.agent.compose, rule, wm, stats, study=self
                )
            else:
                stream = ResponseStream(rd, model, rule, wm, stats, study=self)
            stream.transaction = txn
            for paths in stream.path_batches("stream", 0, deadline):
                txn.proofs_from_paths(stream, paths)


class BenefitStream(LearningStream):
    def programs(self, depth):
        if not depth:
            return []
        if self.study.collect:
            return plans(self.rd, self.rule, depth, True)
        # Templates without primitive atoms have no computation actions.
        if not any(
            "primitive" in x["call"] for x in self.rd.iface.rules[self.rule]["query"]
        ):
            return []
        return decode(
            self.study.agent,
            self.rd,
            self.rule,
            depth,
            self.transaction.capacity,
            self.stats,
        )

    def children(self, paths, depth, block):
        if not hasattr(self, "evidence"):
            self.evidence = {}
        self.evidence[depth] = (len(paths), None)
        yield from super().children(paths, depth, block)

    def route_logits(self, features):
        if self.study.collect:
            return torch.ones_like(features[:, 0])
        return self.study.agent.timing(features).flatten()

    select_query = ResponseStream.select_query

    def remember_response(self, depth, selected, success):
        n, raw = self.evidence[depth]
        if raw is None:
            raw = torch.zeros(n, RAW)
        raw[selected] = self.result_raw[success]
        self.evidence[depth] = (n, raw)

    def score_children(self, h, depth, p, parents):
        score, z = ResponseStream.logits(self, h, depth, p)
        if depth + 1 != len(self.roles):
            return score, z
        evidence = self.evidence[depth][1]
        raw = evidence[parents] if evidence is not None else torch.zeros(len(p), RAW)
        has = raw[:, :6].sum(1)
        meta = self.rd.meta(self.rule).expand(len(p), -1)
        if self.study.collect:
            # Offline native labels of actual proposals on this trajectory.
            matrix = torch.stack(
                [self.port_refs(i)[p[:, i]] for i in np.argsort(self.order)], 1
            )
            refs = torch.cat((matrix, matrix.new_full((*matrix.shape[:2], 1), -1)), 2)
            labels = []
            for part in refs.split(self.transaction.capacity):
                op = np.zeros((len(part), 5), dtype=np.int64)
                op[:, 2] = self.rule
                op[:, 3] = -1
                op[:, 4] = part.shape[1] * np.arange(1, len(part) + 1)
                r = self.transaction.collect(
                    self.transaction.enqueue(op, part.reshape(-1, 4), 0)
                )
                labels.append(r.rows[:, 1] == 0)
            seq = torch.stack(
                [self.local(j, p[:, : j + 1]) for j in range(depth + 1)], 1
            )
            self.study.examples.append((meta, seq, raw, torch.cat(labels), score))
            return torch.full_like(score, -100), z
        start = perf_counter()
        result = self.study.agent.prediction(
            meta, z, raw, score, has, self.study.variant
        )
        self.stats["decision_value_seconds"] += perf_counter() - start
        self.stats["complete_with_typed_computation"] += int(has.sum())
        self.stats["additional_final_proposals"] += int(
            ((score < 0) & (result >= 0)).sum()
        )
        return result, z
