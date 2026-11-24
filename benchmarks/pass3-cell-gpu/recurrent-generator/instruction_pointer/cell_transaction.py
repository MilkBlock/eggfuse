"""CPU tensor/typed-buffer transport for sealed Cell transactions.

Operation and reference matrices use little-endian int64. Offsets in the last
operation column are cumulative exclusive ends into the shared reference matrix.
"""

import struct
from collections import Counter
from time import perf_counter

import numpy as np
import torch

MAGIC = 0x31585443
STATUS = (
    "accepted",
    "duplicate",
    "untriggered_rule",
    "arity",
    "unknown_output",
    "retired",
    "hidden",
    "type",
    "version",
    "binding",
    "watermark",
    "unbound_primitive",
    "guard",
    "unbound_input",
    "computed",
    "bad_dependency",
    "invalid_computation",
    "pending_port",
)


def read_matrix(pipe, rows, cols, dtype="<i8"):
    result = np.empty((rows, cols), dtype=dtype)
    if not rows:
        return result
    view = memoryview(result).cast("B")
    while view:
        n = pipe.readinto(view)
        if not n:
            raise EOFError("native transaction ended inside a buffer")
        view = view[n:]
    return result


class PortView:
    """Lightweight index entry into the immutable native publication buffers."""

    __slots__ = ("hashes", "row")

    def __init__(self, row, hashes):
        self.row = row
        self.hashes = hashes

    def __getitem__(self, name):
        if name == "hashes":
            return self.hashes
        if name == "version":
            return int(self.row[3])
        if name == "table":
            return int(self.row[2])
        if name == "forwarded":
            return bool(self.row[4])
        raise KeyError(name)


def memory_frame(pipe, frame):
    counts = [
        int(frame[k])
        for k in ("typed_rows", "typed_hashes", "typed_retired", "typed_accepted")
    ]
    if min(counts) < 0 or sum(counts) > 100_000_000:
        raise ValueError("invalid publication size")
    rows = read_matrix(pipe, counts[0], 6)
    hashes = read_matrix(pipe, counts[1], 1, "<u8").ravel()
    retired = read_matrix(pipe, counts[2], 2)
    accepted = read_matrix(pipe, counts[3], 2)
    if (rows[-1, 5] if len(rows) else 0) != len(hashes) or np.any(
        np.diff(rows[:, 5], prepend=0) < 0
    ):
        raise ValueError("invalid native field offsets")
    return rows, hashes, retired, accepted


def update_memory(reader, frame, publication, repair_types=None):
    rows, hashes, retired, accepted = publication
    store = reader.store
    if store.rng is not None:
        raise ValueError(
            "on-policy transaction memory requires native address identities"
        )
    for t, r in accepted:
        store.types[int(t)] = ("generated", int(r))
    if repair_types is None:
        repair_types = ((e["token"], e["merge_table"]) for e in frame["repair_events"])
    for token, table in repair_types:
        store.types[int(token)] = ("repair", reader.iface.tables[int(table)])
    changed = set()
    retire = [(int(t), int(op)) for t, op in retired]
    for addr in retire:
        t, op = addr
        row = store.visible.pop(addr)
        tab = row["table"]
        reader.live[tab].pop(addr)
        owners = store.by_table[tab]
        del owners[t][op]
        if not owners[t]:
            del owners[t]
        changed.add(tab)
    start = 0
    updates = []
    for data in rows:
        t, op, table, version, forward, end = map(int, data)
        if (
            not 0 <= table < len(reader.iface.tables)
            or op < 0
            or version < 0
            or forward not in (0, 1)
        ):
            raise ValueError("invalid published port")
        addr = (t, op)
        if t < 0 and t % 2:
            store.types[t] = ("initial", reader.iface.tables[table])
        if reader.iface.exports[store.types[t]].get(op) != reader.iface.tables[table]:
            raise ValueError("bad static port")
        values = hashes[start:end]
        row = PortView(data, values)
        store.visible[addr] = row
        store.by_table[table][t][op] = row
        reader.live[table][addr] = None
        changed.add(table)
        updates.append((addr, table, values))
        start = end
    t = perf_counter()
    reader.index.advance_rows(retire, updates)
    reader.count["index_update_seconds"] += perf_counter() - t
    for tab in changed:
        reader.versions[tab] += 1


class Transaction:
    def __init__(self, proc, capacity):
        if not 1 <= capacity <= 65536:
            raise ValueError("invalid transaction capacity")
        self.proc = proc
        self.capacity = capacity
        self.costs = Counter()
        self.verdicts = Counter()
        self.sizes = Counter()
        self.chunks = []
        self.used = 0
        self.paid = self.proofs = self.computations = 0
        self.accepted = []
        self.run = 0

    def submit(self, operations, references):
        """Submit one batch. Runtime IDs are allocated in wire order.

        References [0, earlier_operation, 0, 0] name computation results local
        to this transaction. The result matrix remains live after the next call.
        """
        t = perf_counter()
        op, refs = self._prepare(operations, references)
        n = len(op)
        header = struct.pack("<4I", MAGIC, n, len(refs), 0)
        self.costs["pack_seconds"] += perf_counter() - t
        t = perf_counter()
        self.proc.stdin.write(header)
        self.proc.stdin.write(memoryview(op))
        if len(refs):
            self.proc.stdin.write(memoryview(refs))
        self.proc.stdin.flush()
        self.costs["request_write_seconds"] += perf_counter() - t
        t = perf_counter()
        response = read_matrix(self.proc.stdout, n, 4)
        self.costs["receipt_read_seconds"] += perf_counter() - t
        self.costs["request_bytes"] += len(header) + op.nbytes + refs.nbytes
        self.costs["response_bytes"] += response.nbytes
        return self._record(op, refs, response, self.run)

    def _prepare(self, operations, references):
        op = np.ascontiguousarray(operations, dtype="<i8").copy()
        refs = np.ascontiguousarray(references, dtype="<i8")
        n = len(op)
        if not (
            1 <= n <= self.capacity
            and op.shape == (n, 5)
            and refs.ndim == 2
            and refs.shape[1] == 4
            and len(refs) <= 1048576
        ):
            raise ValueError("invalid typed transaction shape")
        op[:, 1] = np.arange(self.paid + 1, self.paid + 1 + n)
        self.paid += n
        proofs = int(np.count_nonzero(op[:, 0] == 0))
        self.proofs += proofs
        self.computations += n - proofs
        self.sizes[n] += 1
        return op, refs

    def _record(self, op, refs, response, run):
        t = perf_counter()
        if not np.array_equal(response[:, 0], op[:, 1]):
            raise RuntimeError("transaction reply ID mismatch")
        status = response[:, 1]
        if np.any(status < 0) or np.any(status >= len(STATUS)):
            raise RuntimeError("unknown transaction status")
        counts = np.bincount(status, minlength=len(STATUS))
        self.verdicts.update(
            {STATUS[i]: int(counts[i]) for i in np.flatnonzero(counts)}
        )
        keep = (op[:, 0] == 0) & (status == 0)
        if keep.any():
            widths = np.diff(op[:, 4], prepend=0)
            self.accepted.append(
                (
                    run,
                    op[keep][:, 1:3],
                    widths[keep],
                    refs[np.repeat(keep, widths)],
                )
            )
        self.costs["receipt_decode_audit_seconds"] += perf_counter() - t
        return torch.from_numpy(response)

    def proofs_from_paths(self, stream, paths):
        t = perf_counter()
        n, k = paths.shape
        refs = np.empty((n, k, 4), dtype="<i8")
        refs[:, :, 3] = -1
        for j, role in enumerate(stream.order):
            refs[:, role, :3] = stream.port_refs(j)[paths[:, j]].numpy()
        self.costs["tensor_conversion_seconds"] += perf_counter() - t
        while len(refs):
            count = min(len(refs), self.capacity - self.used)
            self.chunks.append((stream.rule, refs[:count]))
            self.used += count
            refs = refs[count:]
            if self.used == self.capacity:
                self.flush()

    def flush(self):
        if not self.used:
            return
        t = perf_counter()
        op = np.zeros((self.used, 5), dtype="<i8")
        start = 0
        groups = []
        for rule, refs in self.chunks:
            end = start + len(refs)
            op[start:end, 2] = rule
            op[start:end, 3] = -1
            op[start:end, 4] = refs.shape[1]
            groups.append(refs.reshape(-1, 4))
            start = end
        op[:, 4] = op[:, 4].cumsum()
        refs = np.concatenate(groups)
        self.costs["pack_seconds"] += perf_counter() - t
        self.send_proofs(op, refs)
        self.chunks.clear()
        self.used = 0

    def send_proofs(self, operations, references):
        self.submit(operations, references)

    def compute(self, rule, atom, refs):
        """Batched independent scalar queries; use submit for a local DAG."""
        self.flush()
        t = perf_counter()
        n, arity, width = refs.shape
        if width != 4:
            raise ValueError("malformed computation operands")
        refs = refs.detach().contiguous().cpu().numpy()
        self.costs["tensor_conversion_seconds"] += perf_counter() - t
        blocks = []
        for start in range(0, n, self.capacity):
            t = perf_counter()
            block = refs[start : start + self.capacity]
            ops = np.empty((len(block), 5), dtype="<i8")
            ops[:, 0] = 1
            ops[:, 2] = rule
            ops[:, 3] = atom
            ops[:, 4] = arity * np.arange(1, 1 + len(block))
            self.costs["pack_seconds"] += perf_counter() - t
            blocks.append(self.submit(ops, block.reshape(-1, 4)))
        return torch.cat(blocks) if blocks else torch.empty((0, 4), dtype=torch.int64)

    def compute_chain(self, rule, atoms, operands):
        """Submit independent DAGs; rebase each prefix's local references within a transaction."""
        if len(atoms) != len(operands) or not atoms:
            raise ValueError("one operand matrix required per computation")
        if len(atoms) == 1:
            return self.compute(rule, atoms[0], operands[0])
        self.flush()
        t = perf_counter()
        depth = len(atoms)
        if depth > self.capacity:
            raise ValueError("transaction capacity smaller than one dependency chain")
        rows = len(operands[0])
        inputs = []
        for j, refs in enumerate(operands):
            if refs.ndim != 3 or len(refs) != rows or refs.shape[2] != 4:
                raise ValueError("malformed computation chain")
            a = refs.detach().contiguous().cpu().numpy()
            if np.any((a[:, :, 0] == 0) & (a[:, :, 1] >= j)):
                raise ValueError("forward or cyclic local reference")
            inputs.append(a)
        self.costs["tensor_conversion_seconds"] += perf_counter() - t
        widths = np.array([a.shape[1] for a in inputs])
        span = int(widths.sum())
        responses = []
        limit = self.capacity // depth
        for start in range(0, rows, limit):
            t = perf_counter()
            size = min(limit, rows - start)
            ops = np.empty((size, depth, 5), dtype="<i8")
            ops[:, :, 0] = 1
            ops[:, :, 2] = rule
            ops[:, :, 3] = atoms
            ops[:, :, 4] = np.arange(size)[:, None] * span + widths.cumsum()
            refs = np.empty((size, span, 4), dtype="<i8")
            offset = 0
            for entry, width in zip(inputs, widths, strict=True):
                fields = refs[:, offset : offset + width]
                fields[:] = entry[start : start + size]
                local = (fields[:, :, 0] == 0) & (fields[:, :, 1] >= 0)
                fields[:, :, 1] += local * (np.arange(size)[:, None] * depth)
                offset += width
            self.costs["pack_seconds"] += perf_counter() - t
            all_results = self.submit_chain(
                ops.reshape(-1, 5), refs.reshape(-1, 4), depth
            )
            responses.append(all_results[depth - 1 :: depth])
        return (
            torch.cat(responses)
            if responses
            else torch.empty((0, 4), dtype=torch.int64)
        )

    def submit_chain(self, ops, refs, depth):
        return self.submit(ops, refs)

    def seal(self):
        self.flush()
        t = perf_counter()
        self.proc.stdin.write(struct.pack("<4I", MAGIC, 0, 0, 1))
        self.proc.stdin.flush()
        self.costs["request_write_seconds"] += perf_counter() - t
        self.costs["request_bytes"] += 16
        self.costs["seals"] += 1

    def offline_tape(self, runs):
        """Compatibility with the legacy replay tool, outside the timed interval."""
        for run, ops, widths, refs in self.accepted:
            if run > runs:
                break
            start = 0
            for (token, rule), width in zip(ops.tolist(), widths, strict=True):
                parents = [
                    {"address": {"token": t, "op": op}, "version": v}
                    for t, op, v, _ in refs[start : start + width].tolist()
                ]
                start += width
                yield {"run": run, "rule": rule, "token": token, "parents": parents}
