"""Policies B-D. Only frozen CCP calls cross the native boundary."""

from collections import Counter
from time import perf_counter

import numpy as np
import torch

from ccp_v01 import Client
from protocol_model import RAW, WIDTH, ProtocolNet, decode, value_inputs
from txn_policy import ResponsePolicy, ResponseStream


class BoundaryRecorder(Client):
    def __init__(self, *args):
        super().__init__(*args)
        self.proof_results = []
        self.confirmed_rows = 0

    def _record(self, op, refs, response, run):
        self.proof_results.append(response[op[:, 0] == 0, 1] == 0)
        self.confirmed_rows += len(self.proof_results[-1])
        return super()._record(op, refs, response, run)


class LearningPolicy(ResponsePolicy):
    def __init__(self, root, arm, net=None, collect=False, route="learned"):
        super().__init__(root, route)
        self.arm = arm
        self.agent = net or ProtocolNet().eval()
        self.collect = collect
        self.record_boundaries = False
        self.ports = {}
        self.address_mask = 0
        self.latest = torch.zeros(WIDTH)
        self.latest_raw = torch.zeros(RAW)
        self.samples = []
        self.queries = []
        self.boundaries = []
        self.recent = 0.0
        self.types_seen = Counter()

    def memory_address(self, owner, op):
        # Training relabels the neural cache namespace. CCP keeps its own signed
        # session handles. Neither handle is a numeric feature of a learned head.
        return int(owner) ^ self.address_mask, int(op)

    def feedback(self, raw):
        encoded = self.agent.value(raw)
        if len(encoded):
            self.latest = encoded[-1]
            self.latest_raw = raw[-1]
            self.types_seen.update(
                {str(i): int(v) for i, v in enumerate(raw[:, :6].sum(0)) if v}
            )
        return encoded

    def controls(self, txn, stats, progress, paths, left, exhausted=False):
        context = torch.tensor(
            [
                progress,
                np.log1p(paths) / 8,
                np.log1p(left) / 8,
                txn.used / txn.capacity,
                len(txn.pending) / txn.window,
                self.recent,
                exhausted,
                np.log1p(stats["run_proofs"]) / 8,
                np.log1p(stats["run_visits"]) / 12,
                float(self.latest.abs().sum() > 0),
            ],
            dtype=torch.float,
        )
        return torch.cat((context, self.latest))

    def run_snapshot(self, frame, pub, rd, model, txn, stats, deadline):
        rows, _, retired, _ = pub
        for t, op in retired:
            self.ports.pop(self.memory_address(t, op), None)
        for row in rows:
            self.ports.pop(self.memory_address(row[0], row[1]), None)
        rules = frame["rules"]
        self.latest = torch.zeros(WIDTH)
        self.latest_raw = torch.zeros(RAW)
        self.recent = 0.0
        if self.record_boundaries:
            txn.proof_results.clear()
            txn.confirmed_rows = 0
        stats["run_proofs"] = stats["run_visits"] = 0
        base = stats["visits"]
        start_rows = len(self.boundaries)
        seen = txn.verdicts["accepted"]

        def boundary(index, paths, end=False):
            nonlocal seen
            if self.arm != "D" and not self.record_boundaries:
                return False
            stats["run_visits"] = stats["visits"] - base
            x = self.controls(
                txn, stats, index / max(1, len(rules)), paths, len(rules) - index, end
            )
            if self.record_boundaries:
                self.boundaries.append(
                    (x, stats["run_proofs"], txn.confirmed_rows, txn.used)
                )
                # Explore queue states while retaining the complete training Run.
                if txn.used and len(self.boundaries) % 3 == 0:
                    txn.flush()
                if txn.pending and len(self.boundaries) % 2 == 0:
                    txn.collect(txn.pending[-1])
                    self.recent = (txn.verdicts["accepted"] - seen) / max(1, paths)
                    seen = txn.verdicts["accepted"]
                return False
            if self.arm != "D":
                return False
            observe, submit, seal = (self.agent.boundary(x) > 0).tolist()
            stats["boundary_decisions"] += 1
            issued = 0
            if submit and txn.used:
                txn.flush()
                issued += 1
                stats["neural_submit"] += 1
                stats["neural_controls"] += 1
            if observe and txn.pending:
                txn.collect(txn.pending[-1])
                self.recent = (txn.verdicts["accepted"] - seen) / max(1, paths)
                seen = txn.verdicts["accepted"]
                issued += 1
                stats["neural_observe"] += 1
                stats["neural_controls"] += 1
            if seal:
                stats["neural_seal"] += 1
                stats["neural_controls"] += 1
                stats["seal_before_exhaustion"] += int(not end)
            if not (issued or seal):
                stats["neural_continue"] += 1
                stats["neural_controls"] += 1
            return seal

        stopped = False
        for index, (rule, wm) in enumerate(rules):
            if perf_counter() >= deadline:
                raise TimeoutError
            if index and index % 16 == 0 and boundary(index, 0):
                stopped = True
                break
            stream = LearningStream(rd, model, rule, wm, stats, study=self)
            stream.transaction = txn
            for paths in stream.path_batches("stream", 0.0, deadline):
                txn.proofs_from_paths(stream, paths)
                stats["run_proofs"] += len(paths)
                if boundary(index, len(paths)):
                    stopped = True
                    break
            if stopped:
                break
        if not stopped and not boundary(len(rules), 0, True):
            stats["fixed_seals"] += 1
        if self.record_boundaries:
            txn.flush()
            if txn.pending:
                txn.collect(txn.pending[-1])
            outcomes = (
                np.concatenate(txn.proof_results)
                if txn.proof_results
                else np.empty(0, bool)
            )
            assert len(outcomes) == stats["run_proofs"]
            for i in range(start_rows, len(self.boundaries)):
                x, position, confirmed, buffered = self.boundaries[i]
                future = outcomes[position:]
                queued = outcomes[confirmed:position]
                unsent = outcomes[position - buffered : position]
                observe = bool(len(queued) and abs(queued.mean() - float(x[5])) > 0.20)
                submit = bool(unsent.sum() > 0.25)
                self.boundaries[i] = (
                    x,
                    int(future.sum()),
                    len(future),
                    observe,
                    submit,
                )


class LearningStream(ResponseStream):
    def programs(self, depth):
        if self.study.arm in ("C", "D"):
            return decode(
                self.study.agent,
                self.rd,
                self.rule,
                depth,
                self.transaction.capacity,
                self.stats,
            )
        return super().programs(depth)

    def issue_program(self, plan, inputs):
        txn = self.transaction
        txn.flush()
        steps = plan.steps
        depth = len(steps)
        count = len(inputs[0])
        rows = []
        raws = []
        self.scope_context = []
        for at in range(0, count, txn.capacity // depth):
            size = min(txn.capacity // depth, count - at)
            packed = []
            widths = []
            for x in inputs:
                fields = x[at : at + size].numpy().copy()
                local = (fields[:, :, 0] == 0) & (fields[:, :, 1] >= 0)
                fields[:, :, 1] += local * (np.arange(size)[:, None] * depth)
                packed.append(fields)
                widths.append(fields.shape[1])
            refs = np.concatenate(packed, axis=1).reshape(-1, 4)
            ops = np.zeros((size, depth, 5), dtype=np.int64)
            ops[:, :, 0] = 1
            ops[:, :, 2] = self.rule
            ops[:, :, 3] = [pc for pc, _ in steps]
            ops[:, :, 4] = np.arange(size)[:, None] * sum(widths) + np.cumsum(widths)
            masks = np.zeros((size, depth), dtype=np.uint8)
            scope = self.study.controls(txn, self.stats, 0.0, size, 0)
            self.scope_context.append(
                torch.cat((scope[:10], self.study.latest_raw)).expand(size, -1)
            )
            observe = True
            if self.study.arm == "D":
                observe = self.study.agent.scope(scope).item() >= 0
                self.stats["observe_scope_decisions"] += 1
                self.stats["observe_value_scopes"] += int(observe)
                self.stats["neural_controls"] += 1
            masks[:, -1] = 3 if observe else 1
            t = perf_counter()
            result = txn.collect(txn.enqueue(ops.reshape(-1, 5), refs, masks.ravel()))
            self.stats["compute_response_seconds"] += perf_counter() - t
            rows.append(result.rows[depth - 1 :: depth])
            t = perf_counter()
            raws.append(value_inputs(result)[depth - 1 :: depth])
            self.stats["value_decode_seconds"] += perf_counter() - t
        self.result_raw = torch.cat(raws)
        t = perf_counter()
        self.result_value = self.study.feedback(self.result_raw)
        self.stats["value_encode_seconds"] += perf_counter() - t
        self.stats["issued_local_edges"] += count * sum(
            link is not None and link[0] == "local"
            for _, args in steps
            for link in args
        )
        self.stats["compute_programs"] += count
        return torch.cat(rows)

    def select_query(self, success, occupancy, narrowed):
        raw = self.result_raw[success]
        state = torch.stack(
            (
                occupancy.float().log1p() / 8,
                torch.ones_like(occupancy),
                torch.zeros_like(occupancy),
            ),
            1,
        )
        if self.study.collect:
            self.study.queries.append(
                (
                    raw,
                    state,
                    (occupancy > narrowed).float(),
                    torch.cat(self.scope_context)[success],
                )
            )
            return torch.ones(len(raw), dtype=torch.bool)
        return (
            self.study.agent.query(
                torch.cat((self.result_value[success], state), 1)
            ).flatten()
            >= 0
        )

    def read_values(self, depth, paths):
        # A named field of the selected producer. No value search or table scan.
        ix, inv = paths[:, -1].unique(return_inverse=True)
        keys = [self.study.memory_address(*self.roles[depth][i]) for i in ix.tolist()]
        cache = self.study.ports
        missing = [j for j, k in enumerate(keys) if k not in cache]
        for offset in range(0, len(missing), self.transaction.capacity):
            selected = missing[offset : offset + self.transaction.capacity]
            addr = self.port_refs(depth)[ix[selected]]
            refs = torch.cat((addr, addr.new_zeros(len(addr), 1)), 1)
            ops = np.zeros((len(refs), 5), dtype=np.int64)
            ops[:, 0] = 2
            ops[:, 2] = self.rule
            ops[:, 3] = -1
            ops[:, 4] = np.arange(1, len(refs) + 1)
            r = self.transaction.collect(self.transaction.enqueue(ops, refs, 2))
            t = perf_counter()
            raw = value_inputs(r)
            encoded = self.study.feedback(raw)
            self.stats["value_encode_seconds"] += perf_counter() - t
            self.stats["port_read_failures"] += int((r.rows[:, 1] != 14).sum())
            self.stats["port_reads"] += len(raw)
            for i, j in enumerate(selected):
                cache[keys[j]] = (raw[i], encoded[i], int(r.rows[i, 1] == 14))
        self.stats["port_cache_hits"] += len(keys) - len(missing)
        vals = [cache[k] for k in keys]
        raw, enc, ok = zip(*vals, strict=True)
        return torch.stack(raw)[inv], torch.stack(enc)[inv], torch.tensor(ok)[inv]

    def logits(self, h, depth, p):
        score, z = super().logits(h, depth, p)
        if depth + 1 != len(self.roles):
            return score, z
        # Preserve all earlier stream cursors. In training, ask the native verifier
        # for complete decisions at the final stage, including baseline misses.
        raw, enc, ok = self.read_values(depth, p)
        meta = self.rd.meta(self.rule).expand(len(p), -1)
        state = torch.stack(
            (
                score.clamp(-12, 12) / 8,
                ok,
                self.tables[depth][0][p[:, -1]],
                self.tables[depth][4][p[:, -1], 4],
            ),
            1,
        )
        if self.study.collect:
            matrix = torch.stack(
                [self.port_refs(j)[p[:, j]] for j in np.argsort(self.order)], 1
            )
            refs = torch.cat((matrix, matrix.new_full((*matrix.shape[:2], 1), -1)), 2)
            labels = []
            for block in refs.split(self.transaction.capacity):
                ops = np.zeros((len(block), 5), dtype=np.int64)
                ops[:, 2] = self.rule
                ops[:, 3] = -1
                ops[:, 4] = p.shape[1] * np.arange(1, len(block) + 1)
                response = self.transaction.collect(
                    self.transaction.enqueue(ops, block.reshape(-1, 4), 0)
                )
                labels.append(response.rows[:, 1] == 0)
            self.study.samples.append((raw, meta, state, torch.cat(labels).float()))
            return torch.full_like(score, -100), z
        residual = self.study.agent.score(meta, enc, state)
        return score + residual, z
