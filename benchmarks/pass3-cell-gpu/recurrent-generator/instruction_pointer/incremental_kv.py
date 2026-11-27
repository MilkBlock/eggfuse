"""Inference cache scoped to one frozen decoder, native session and Recipe catalogue."""

import math
from collections import Counter
from time import perf_counter

import torch

from actor import rotate
from cell_kv_model import CellKV, public_values


class InferenceCache:
    def __init__(self, net):
        if net.training or torch.is_grad_enabled():
            raise ValueError("incremental K/V requires a frozen inference session")
        if type(net).instance_embedding is not CellKV.instance_embedding:
            raise ValueError(
                "cache requires the validated native Cell instance encoder"
            )
        self.net = net
        self.count = Counter()
        self.seconds = Counter()
        self.epoch = None
        self.port_rows = None
        self.payload = {}
        self.port_values = {}
        self.owner_values = {}
        self.records = ()
        self.result = None
        self.rk = self.rv = None
        self.header = None
        self.parent_code = None
        self.parents = []
        self.ordinals = []
        self.parent_owners = []
        self.offsets = [0]
        self.issued = []
        self.world = None
        self.weights = tuple((id(p), p._version) for p in net.parameters())
        net.published_kv = self.published
        net.response_kv = self.responses

    def published(self, w, s):
        if (
            torch.is_grad_enabled()
            or self.net.training
            or self.weights != tuple((id(p), p._version) for p in self.net.parameters())
        ):
            raise ValueError("model updated during frozen session")
        if self.world is not None and w is not self.world:
            raise ValueError("new native world needs a fresh cache")
        self.world = w
        start = perf_counter()
        ports = tuple(s["ports"])
        epoch = s["epoch"]
        self.count["public_row_visits"] += len(ports)
        if epoch == self.epoch and ports == self.port_rows:
            self.count["public_view_hits"] += 1
            return self.result
        self.rk = self.rv = None
        actor = self.net.actor
        _, codes, types = self.net.cache
        refs = [p[0] for p in ports]
        positions = {r: i for i, r in enumerate(refs)}
        owners = {}
        for i, p in enumerate(ports):
            owners.setdefault(p[1], []).append(i)
        empty = types[:0]

        def stack(seq):
            return torch.stack(seq) if seq else empty

        new = [
            p
            for p in ports
            if p[0] not in self.payload or self.payload[p[0]][0] != p[4]
        ]
        if new:
            dyn = actor.dynamic(public_values([p[4] for p in new]))
            self.payload.update(
                (p[0], (p[4], t)) for p, t in zip(new, dyn.unbind(), strict=True)
            )
        self.payload = {r: self.payload[r] for r in refs}
        self.count["payload_encoded"] += len(new)
        # A live parent's projected value changes on age, forwarded bit, type or payload.
        stamp = [(p[0], p[3], p[4], p[5], epoch) for p in ports]
        changed = [i for i, key in enumerate(stamp) if key not in self.port_values]
        if changed:
            age = types.new_tensor(
                [
                    [math.log1p(max(0, epoch - refs[i][2])) / 8, float(ports[i][5])]
                    for i in changed
                ]
            )
            v = (
                types[[ports[i][3] for i in changed]]
                + stack([self.payload[refs[i]][1] for i in changed])
                + actor.age(age)
            ).tanh()
            ek = actor.input_content(v)
            self.port_values.update(
                (stamp[i], (v[j], ek[j])) for j, i in enumerate(changed)
            )
        self.count["versioned_rows_encoded"] += len(changed)
        self.port_values = {k: self.port_values[k] for k in stamp}
        value = stack([self.port_values[k][0] for k in stamp])
        ext_keys = stack([self.port_values[k][1] for k in stamp])
        groups = []
        signatures = []
        rebuild = []
        for uid, ix in owners.items():
            parents = [
                [positions[r] for r in ports[i][6] if r in positions] for i in ix
            ]
            signature = (
                uid,
                ports[ix[0]][2],
                tuple(stamp[i] for i in ix),
                tuple(tuple(stamp[j] for j in js) for js in parents),
            )
            signatures.append(signature)
            groups.append(torch.tensor(ix))
            if signature not in self.owner_values:
                first = ports[ix[0]]
                source = types[first[3]] if first[2] < 0 else codes[first[2]]
                parent = stack(
                    [
                        value[js].mean(0) if js else torch.zeros_like(source)
                        for js in parents
                    ]
                ).mean(0)
                rebuild.append(
                    (signature, (source + value[ix].mean(0) + parent).tanh())
                )
        if rebuild:
            vals = stack([v for _, v in rebuild])
            keys = actor.input_content(vals)
            read_vals = actor.latent(vals)
            self.owner_values.update(
                (k, (v, keys[i], read_vals[i])) for i, (k, v) in enumerate(rebuild)
            )
        self.count["owners_encoded"] += len(rebuild)
        self.owner_values = {k: self.owner_values[k] for k in signatures}
        vectors = [
            stack([self.owner_values[k][j] for k in signatures]) for j in range(3)
        ]
        owner_id = {uid: i for i, uid in enumerate(owners)}
        group = torch.tensor([owner_id[p[1]] for p in ports], dtype=torch.long)
        tables = torch.tensor([p[3] for p in ports], dtype=torch.long)
        self.result = (
            refs,
            positions,
            group,
            groups,
            tables,
            value,
            *vectors,
            ext_keys,
        )
        self.port_rows = ports
        self.epoch = epoch
        self.seconds["published_update"] += perf_counter() - start
        return self.result

    def responses(self, records, epoch, codes, positions, values):
        start = perf_counter()
        n = len(self.records)
        # Native Instances owns an append-only sequence. Verify reuse against the
        # supplied snapshot, including payloads, even for offline/replay callers.
        if len(records) < n or records[:n] != self.records:
            raise ValueError("receipt history diverged within native session")
        actor = self.net.actor
        if len(records) > n:
            block = records[n:]
            mask = (1 << 64) - 1
            h = (
                public_values(
                    [
                        tuple(v & mask for v in (reply[0], run, ep, reply[2], reply[3]))
                        for run, ep, _, _, reply in block
                    ]
                )
                * 0.125
            )
            h[torch.arange(len(block)), [reply[1] for *_, reply in block]] += 1
            static = codes[[r[2] for r in block]] + actor.dynamic(h)
            self.header = (
                static if self.header is None else torch.cat((self.header, static))
            )
            offset = len(self.parents)
            for i, (_, ep, _, refs, _) in enumerate(block, n):
                self.issued.append(ep)
                self.parents.extend(refs)
                self.ordinals.extend(range(len(refs)))
                self.parent_owners.extend([i] * len(refs))
                self.offsets.append(len(self.parents))
            if len(self.parents) > offset:
                v = (
                    actor.dynamic(
                        public_values(
                            [
                                tuple(x & mask for x in ref)
                                for ref in self.parents[offset:]
                            ]
                        )
                    )
                    * 0.125
                )
                self.parent_code = (
                    v if self.parent_code is None else torch.cat((self.parent_code, v))
                )
            self.count["receipt_headers_encoded"] += len(block)
            self.records = records
        begin = 0 if self.rk is None else n
        if begin < len(records):
            off = self.offsets[begin]
            ages = values.new_tensor(
                [(math.log1p(epoch - ep) / 8, 1.0) for ep in self.issued[begin:]]
            )
            row = self.header[begin:] + actor.age(ages)
            if off < len(self.parents):
                ix = [positions.get(r, len(values)) for r in self.parents[off:]]
                padded = torch.cat((values, values.new_zeros(1, values.shape[1])))
                read = rotate(
                    padded[ix] + self.parent_code[off:],
                    torch.tensor(self.ordinals[off:]),
                )
                row = row.index_add(
                    0, torch.tensor(self.parent_owners[off:]) - begin, read
                )
            row = row.tanh()
            rk, rv = actor.input_content(row), actor.latent(row)
            self.rk = rk if begin == 0 else torch.cat((self.rk, rk))
            self.rv = rv if begin == 0 else torch.cat((self.rv, rv))
            self.count["receipt_dynamic_rows"] += len(row)
        self.count["receipt_rows_read"] += len(records)
        self.seconds["receipt_update"] += perf_counter() - start
        return self.rk, self.rv
