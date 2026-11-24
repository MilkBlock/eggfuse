"""Use the learned CCP instruction/operand decoder on event-selected parent roles."""

from pathlib import Path
import numpy as np
import torch
from protocol_model import decode
from benefit_policy import BenefitNet


class Computation:
    def __init__(self, out):
        self.model = BenefitNet().eval()
        self.model.load_state_dict(
            torch.load(
                Path("run-recall/computation-benefit/residual.pt"), weights_only=True
            )
        )
        weights = self.model.state_dict()
        weights.update(torch.load(out / "computation.pt", weights_only=True))
        self.model.load_state_dict(weights)
        self.programs = {}

    def address(self, mem, r, order, depth, paths, txn, stats, window):
        k = (r, order, depth)
        if k not in self.programs:
            self.programs[k] = decode(
                self.model, mem.rd, r, depth, txn.capacity, stats, order=order
            )
        plans = self.programs[k]
        if not plans:
            return window
        (plan,) = plans
        dst = mem.bank(mem.roles[r][order[depth]])
        if not len(dst.ports):
            return window
        args = []
        for _, operands in plan.steps:
            cols = []
            for op in operands:
                if op is None or op[0] == "local":
                    value = [0, -1 if op is None else op[1], 0, 0]
                    cols.append(np.broadcast_to(value, (len(paths), 4)))
                else:
                    j, col = op
                    stats["operand_port_reads"] += len(paths)
                    refs = mem.bank(mem.roles[r][order[j]]).rows[paths[:, j]]
                    cols.append(np.column_stack((refs, np.full(len(refs), col))))
            args.append(torch.from_numpy(np.stack(cols, axis=1)))
        stats["computation_programs"] += len(paths)
        stats["local_result_operands"] += len(paths) * sum(
            1
            for _, args0 in plan.steps
            for op in args0
            if op is not None and op[0] == "local"
        )
        rows = txn.compute_chain(r, [pc for pc, _ in plan.steps], args)
        ok = rows[:, 1] == 14
        stats["response_queries"] += int(ok.sum())
        raw = ((rows[:, 3, None] >> torch.arange(63, -1, -1)) & 1).float() * 2 - 1
        code = mem.rd.index.code(mem.rd.index.encoder(raw)).numpy()
        col = plan.output_column
        if col not in dst.fields:
            stats["posting_index_reads"] += len(dst.ports)
        postings, offset = dst.postings(col)
        # Failed computations yield no evidence. Keep the original neural address
        # for those rows; split batches so the two posting arrays remain distinct.
        return [
            (ix, p, s, n)
            for ix, p, s, n in [
                (
                    np.flatnonzero(ok.numpy()),
                    postings,
                    offset[code],
                    offset[code + 1] - offset[code],
                ),
                (np.flatnonzero(~ok.numpy()), *window),
            ]
            if len(ix)
        ]
