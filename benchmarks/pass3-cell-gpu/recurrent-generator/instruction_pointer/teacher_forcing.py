"""Teacher-forced complete-token likelihoods for the dense typed prefix decoder."""

from collections import defaultdict
from math import sqrt

import torch
from torch.nn.utils.rnn import pad_sequence

from operand_read_model import words
from prefix_attention import static_wires


def complete_nll(net, examples, device="cpu"):
    if net.arm != "C" or not net.typed or net.mode != "direct":
        raise ValueError("requires the direct dense typed prefix decoder")
    groups = defaultdict(list)
    roots, terms, destinations = [], [], []
    offset = 0
    for w, state, targets in examples:
        net.prepare(w)
        net.physical = ("held", 0)
        m = net.state(w, state)
        nodes, codes, _ = net.cache
        root_pos = {r: i for i, r in enumerate(m["families"])}
        menu = {t: i for i, t in enumerate(m["menu"])}
        variant = {}
        variant_scores = []
        root_ids, variant_ids = [], []
        prefixes = defaultdict(dict)
        accesses = defaultdict(list)
        # CPU collation of observed names only. No model operation for each target.
        for i, (t, refs) in enumerate(targets):
            rid = w.layouts[t][0][0]
            ix = tuple(m["pos"][ref] for ref in refs)
            family = rid, ix[0] if ix and len(m["families"][rid]) > 1 else None
            if family not in variant:
                variant[family] = len(variant_scores)
                variant_scores.extend(net.variant_prob(w, m, *family).unbind())
            variant_ids.append(variant[family] + m["families"][rid].index(menu[t]))
            root_ids.append(root_pos[rid])
            for j, target in enumerate(ix):
                key = (t if j else rid, j)
                pre = ix[:j]
                row = prefixes[key].setdefault(pre, len(prefixes[key]))
                accesses[key].append((offset + i, row, target))
        roots.append(m["root_lp"][root_ids] + torch.stack(variant_scores)[variant_ids])
        if not prefixes:
            offset += len(targets)
            continue
        flat = m["keys"][m["group"]] + m["ek"]
        bias = torch.bincount(m["group"]).float().log()[m["group"]]
        encoded = None
        for (tid, j), rows in prefixes.items():
            rid = w.layouts[tid][0][0]
            pre = torch.tensor(list(rows), dtype=torch.long)
            h = (m["ctx"] + codes[tid]).tanh().expand(len(rows), -1)
            for k in range(j):
                h = net.actor.next_read(m["ext"][pre[:, k]], h)
            q = net.actor.query(h + nodes[w.cat.inputs["generated", rid][j]])
            relation = None
            wires = static_wires(w, rid, j)
            if wires:
                if encoded is None:
                    bits = words([p[4] for p in m["ports"]])[0].reshape(
                        len(flat), -1, 2, 32
                    )
                    encoded = net.actor.latent(bits).tanh()
                prev, src, col, op = map(list, zip(*wires))
                role = nodes[op][:, None, :]
                filled = encoded[pre[:, prev], src]
                values = encoded[:, col]
                rq = filled + 0.25 * net.actor.query(filled + role).tanh()
                rk = values + 0.25 * net.actor.input_content(values + role).tanh()
                relation = (
                    rq.flatten(1).to(device) @ rk.flatten(1).to(device).T
                ) / sqrt(64 * len(wires))
            mask = m["tables"] != w.roles[rid][j]
            groups[len(flat).bit_length(), len(rows).bit_length()].append(
                (q, flat, bias, mask, relation, accesses[tid, j])
            )
        offset += len(targets)
    for items in groups.values():
        qs, ks = (
            pad_sequence([x[i] for x in items], batch_first=True).to(device)
            for i in (0, 1)
        )
        scores = torch.bmm(qs, ks.transpose(1, 2)) / sqrt(32)
        for i, (q, k, bias, mask, relation, edges) in enumerate(items):
            logits = scores[i, : len(q), : len(k)] - bias.to(device)
            if relation is not None:
                logits = logits + relation
            lp = logits.masked_fill(mask.to(device), -torch.inf).log_softmax(-1)
            dst, row, col = zip(*edges)
            terms.append(lp[list(row), list(col)])
            destinations.extend(dst)
    result = torch.cat(roots).to(device)
    if terms:
        result = result.index_add(
            0, torch.tensor(destinations, device=device), torch.cat(terms)
        )
    return -result
