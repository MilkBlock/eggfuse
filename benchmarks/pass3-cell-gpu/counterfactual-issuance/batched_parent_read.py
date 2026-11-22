"""Offline fixed-depth two-parent reader on generated token histories."""
import argparse
import json
import statistics
import time

import torch
from torch import nn
from torch.nn import functional as F


def histories(rng, batch, ports, vocab):
    left = torch.rand(batch, vocab, generator=rng).argsort()[:, :ports]
    right = torch.randint(vocab, (batch, ports), generator=rng)
    return left, right


def encode(embed, ids):
    return F.normalize(embed(ids), dim=-1)


class BucketEncoder(nn.Module):
    """Four reusable symbol alphabets for generated nonnegative 30-bit keys."""

    def __init__(self, width):
        super().__init__()
        self.codes = nn.Embedding(64, width // 4)
        self.register_buffer('mult', torch.tensor([1126487633, 984316147, 180550531, 746773517]))
        self.register_buffer('bias', torch.tensor([38069, 6761, 1217, 32533]))

    def forward(self, ids):
        hashes = ((ids[..., None] * self.mult + self.bias) % 2147483647) % 64
        return F.normalize(self.codes(hashes), dim=-1).flatten(-2)


def presence(lhs, rhs, bucketed):
    contributions = lhs * rhs.sum(1, keepdim=True)
    if bucketed:
        # All four projections of a true key must be present on the right.
        return 4 * contributions.unflatten(-1, (4, -1)).sum(-1).amin(-1)
    return contributions.sum(-1)


def train_encoder(device, width, steps, seed, bucketed=False, ports=32):
    vocab = 128
    torch.manual_seed(seed)
    embed = (BucketEncoder(width) if bucketed else nn.Embedding(2 * vocab, width)).to(device)
    optimizer = torch.optim.Adam(embed.parameters(), lr=.025)
    rng = torch.Generator().manual_seed(518)
    for _ in range(steps):
        left, right = [x.to(device) for x in histories(rng, 64, ports, vocab)]
        if bucketed:
            names = torch.randint(1 << 30, (vocab,), generator=rng).to(device)
            left, right = names[left], names[right]
        match = left[:, :, None] == right[:, None, :]
        lhs, rhs = encode(embed, left), encode(embed, right)
        existence = presence(lhs, rhs, bucketed)
        loss = F.binary_cross_entropy_with_logits(8 * (existence - .5), match.any(-1).float())
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

    return embed


def experiment(device, width, steps, seed, bucketed=False):
    vocab, ports, beam = 128, 32, 12
    embed = train_encoder(device, width, steps, seed, bucketed)
    left, right = [x.to(device) for x in histories(torch.Generator().manual_seed(225), 256, ports, vocab)]
    target = left[:, :, None] == right[:, None, :]
    with torch.no_grad():
        def issue(mode, cached=None):
            lhs, rhs = cached if cached is not None else (encode(embed, left), encode(embed, right))
            if mode == 'all_pairs':
                parent = torch.arange(ports, device=device).expand(len(left), -1)
            elif mode == 'blind':
                parent = torch.arange(beam, device=device).expand(len(left), -1)
            else:
                score = presence(lhs, rhs, bucketed)
                parent = score.topk(beam, dim=1).indices
            chosen = lhs if mode == "all_pairs" else lhs.gather(1, parent[..., None].expand(-1, -1, width))
            scores = chosen @ rhs.transpose(1, 2)
            values, flat = scores.flatten(1).topk(ports, dim=1)
            lidx = flat // ports if mode == "all_pairs" else parent.gather(1, flat // ports)
            return lidx * ports + flat % ports, values > .999

        def sync():
            if device == 'mps':
                torch.mps.synchronize()

        rows = {}
        for mode in ['all_pairs', 'blind', 'pooled']:
            indices, mask = issue(mode)
            labels = target.flatten(1).gather(1, indices)
            tp = int((labels & mask).sum())
            assert not int((target.sum((1, 2)) > ports).sum())
            rows[mode] = dict(correct=tp, extra=int(mask.sum())-tp, missed=int(target.sum())-tp)
        cached = encode(embed, left), encode(embed, right)
        for field, bank in [('median_ms', None), ('cached_ms', cached)]:
            samples = {k: [] for k in rows}
            for cycle in range(12):
                order = list(rows)
                for mode in order[cycle % 3:] + order[:cycle % 3]:
                    sync()
                    start = time.perf_counter()
                    issue(mode, bank)
                    sync()
                    if cycle >= 3:
                        samples[mode].append((time.perf_counter()-start)*1000)
            for mode in rows:
                rows[mode][field] = statistics.median(samples[mode])
        # Rename every subject while preserving every legal pair. The vocabulary
        # head uses untouched rows; the bucket head reuses trained symbol codes.
        if bucketed:
            names = torch.randperm(65536, generator=torch.Generator().manual_seed(991))[:vocab].to(device) + 1000000
            left, right = names[left], names[right]
        else:
            left, right = left + vocab, right + vocab
        for mode in rows:
            indices, mask = issue(mode)
            labels = target.flatten(1).gather(1, indices)
            rows[mode]['renamed_correct'] = int((labels & mask).sum())
            rows[mode]['renamed_extra'] = int((~labels & mask).sum())
        max_possible = int(target.sum(2).topk(beam, dim=1).values.sum())
    return dict(encoding="buckets" if bucketed else "vocabulary", width=width, steps=steps, seed=seed, targets=int(target.sum()),
                best_possible_with_beam=max_possible, results=rows)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output')
    p.add_argument('--devices', nargs='+', choices=['cpu', 'mps'], default=['cpu'])
    args = p.parse_args()
    torch.set_num_threads(1)
    result = {device: [experiment(device, width, steps, 27, bucketed)
                       for width, steps, bucketed in [(16, 200, False), (64, 0, False), (64, 200, False),
                                                      (128, 0, False), (128, 200, False),
                                                      (256, 0, True), (256, 200, True)]]
              for device in args.devices}
    with open(args.output, 'w') as out:
        json.dump(result, out, indent=2)
        out.write('\n')
