"""Cell Communication Protocol 0.1, ordered-pipe CPU client."""

import json
import struct
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from time import perf_counter

import numpy as np
import torch

from cell_transaction import MAGIC, Transaction, read_matrix

PREFIX = struct.Struct("<4sHHQQQ")
COUNTS = struct.Struct("<4I")
HASH = 1
VALUE = 2


@dataclass(frozen=True)
class Response:
    sequence: int
    run: int
    epoch: int
    rows: torch.Tensor
    value_ends: np.ndarray
    values: np.ndarray


class Client(Transaction):
    def __init__(self, proc, capacity, digest, window=4):
        super().__init__(proc, capacity)
        hello = json.loads(proc.stdout.readline())
        expected = {
            "protocol": "Cell Communication Protocol",
            "version": [0, 1],
            "program_sha256": digest,
            "commit_scope": "source_run",
            "transport": "ordered-pipe",
        }
        if any(hello.get(k) != v for k, v in expected.items()):
            raise ValueError("incompatible CCP service or compiled program")
        if window < 1:
            raise ValueError("invalid pipeline window")
        self.window = window
        self.sequence = self.epoch = 0
        self.pending = deque()
        self.reader = ThreadPoolExecutor(max_workers=1)

    def _prefix(self, tag, seq):
        return PREFIX.pack(tag, 0, 1, seq, self.run, self.epoch)

    def _read(self, seq, run, epoch, n, with_values):
        tick = perf_counter()
        data = self.proc.stdout.read(PREFIX.size + 8)
        if len(data) != 40 or PREFIX.unpack_from(data) != (
            b"CCPR",
            0,
            1,
            seq,
            run,
            epoch,
        ):
            raise ValueError("unaligned CCP response")
        length = struct.unpack_from("<Q", data, 32)[0]
        if length > 64 * 1024 * 1024 or (length and not with_values):
            raise ValueError("invalid observation payload size")
        rows = read_matrix(self.proc.stdout, n, 4)
        ends = read_matrix(self.proc.stdout, n if with_values else 0, 1, "<u8").ravel()
        if with_values and (ends[-1] != length or np.any(ends[1:] < ends[:-1])):
            raise ValueError("invalid observed value offsets")
        arena = read_matrix(self.proc.stdout, length, 1, "u1").ravel()
        return rows, ends, arena, perf_counter() - tick

    def enqueue(self, operations, references, observe=None):
        """Issue now; collector may continue inference before awaiting the ticket."""
        if len(self.pending) >= self.window:
            self.collect(self.pending[0])
        t = perf_counter()
        raw = np.asarray(operations)
        masks = np.broadcast_to(HASH if observe is None else observe, (len(raw),))
        if masks.dtype.kind not in "iu" or np.any(masks < 0) or np.any(masks > 3):
            raise ValueError("invalid CCP observation mask")
        masks = np.ascontiguousarray(masks, dtype=np.uint8)
        op, refs = self._prepare(operations, references)
        self.sequence += 1
        seq = self.sequence
        header = self._prefix(b"CCPQ", seq) + COUNTS.pack(MAGIC, len(op), len(refs), 0)
        self.costs["pack_seconds"] += perf_counter() - t
        t = perf_counter()
        future = self.reader.submit(
            self._read, seq, self.run, self.epoch, len(op), bool(np.any(masks & VALUE))
        )
        self.proc.stdin.writelines(
            (header, memoryview(op), memoryview(refs), memoryview(masks))
        )
        self.proc.stdin.flush()
        self.costs["request_write_seconds"] += perf_counter() - t
        self.costs["request_bytes"] += (
            len(header) + op.nbytes + refs.nbytes + masks.nbytes
        )
        ticket = Ticket(seq, self.run, self.epoch, op, refs.copy(), future)
        self.pending.append(ticket)
        self.costs["max_outstanding"] = max(
            self.costs["max_outstanding"], len(self.pending)
        )
        return ticket

    def collect(self, ticket):
        if ticket.response is None:
            self.costs["collection_barriers"] += 1
        while ticket.response is None:
            item = self.pending.popleft()
            t = perf_counter()
            rows, ends, arena, read_time = item.future.result()
            self.costs["receipt_wait_seconds"] += perf_counter() - t
            self.costs["receipt_read_seconds"] += read_time
            self.costs["response_bytes"] += (
                40 + rows.nbytes + ends.nbytes + arena.nbytes
            )
            out = self._record(item.op, item.refs, rows, item.run)
            item.response = Response(item.seq, item.run, item.epoch, out, ends, arena)
        return ticket.response

    def submit(self, operations, references):
        return self.collect(self.enqueue(operations, references)).rows

    def submit_chain(self, ops, refs, depth):
        observe = np.zeros(len(ops), dtype=np.uint8)
        observe[depth - 1 :: depth] = HASH
        return self.collect(self.enqueue(ops, refs, observe)).rows

    def send_proofs(self, operations, references):
        self.enqueue(operations, references, 0)

    def seal(self):
        self.flush()
        self.sequence += 1
        self.proc.stdin.write(self._prefix(b"CCPQ", self.sequence))
        self.costs["request_bytes"] += 32
        super().seal()
        if self.pending:
            self.collect(self.pending[-1])

    def close(self):
        self.reader.shutdown(wait=True)


@dataclass(eq=False)
class Ticket:
    seq: int
    run: int
    epoch: int
    op: np.ndarray
    refs: np.ndarray
    future: object
    response: Response | None = None


def read_repairs(pipe, frame):
    count = frame["typed_repairs"]
    length = frame["typed_repair_ops"]
    if not (0 <= count <= 100_000_000 and 0 <= length <= 100_000_000):
        raise ValueError("invalid repair publication")
    desc = read_matrix(pipe, count, 14)
    ops = read_matrix(pipe, length, 1).ravel()
    if (desc[-1, -1] if count else 0) != length or np.any(
        np.diff(desc[:, -1], prepend=0) < 0
    ):
        raise ValueError("invalid repair offsets")
    if np.any(desc[:, 3] != frame["run"]) or np.any(desc[:, 3] != desc[:, 1] + 1):
        raise ValueError("repair outside publication boundary")
    return desc, ops


def offline_repairs(blocks):
    """Convert typed system events to the archived replay schema after timing."""
    for desc, ops in blocks:
        start = 0
        for row in desc:
            t, run, table, visible, a, ao, av, b, bo, bv, present, ha, hb, end = map(
                int, row
            )
            yield {
                "token": t,
                "run": run,
                "merge_table": table,
                "visible_from_run": visible,
                "parents": [
                    {"address": {"token": a, "op": ao}, "version": av},
                    {"address": {"token": b, "op": bo}, "version": bv},
                ],
                "input_hashes": [ha % (1 << 64), hb % (1 << 64)] if present else None,
                "operations": ops[start:end].tolist(),
            }
            start = end
