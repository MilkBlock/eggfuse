"""Two recurrent proposal waves per Run. Only real verifier replies enter the policy."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
from torch import nn

from model import Actor, HIDDEN, LEAVES, RANKS, ROWS, set_loss


class FeedbackActor(Actor):
    def __init__(self):
        super().__init__()
        self.reply_context = nn.Parameter(torch.zeros(HIDDEN, 8))
        self.reply_score = nn.Parameter(torch.zeros(8))

    def propose(self, features, token, reply, wave, mode, shuffle=False, exclude_closed=False):
        forbidden = None
        if exclude_closed and wave == 1:
            status, leaf, anchor, _ = reply.unbind(-1)
            actions = torch.arange(LEAVES * RANKS, device=features.device)
            same_leaf = leaf[..., None] == actions // RANKS
            same_row = anchor[..., None] == features[:, None, :, 0]
            forbidden = (((status == 1) | (status == 3))[..., None] & same_leaf & same_row).any(1)
        if mode == 0:
            return self.step(features, token, forbidden=forbidden)
        status, leaf, anchor, detail = reply.unbind(-1)
        own_peer = lambda x: torch.stack([x, x.flip(1)], dim=2)
        code = own_peer(status)
        accepted = code == 1
        rejected = (code == 2) & (mode == 2)
        signals = torch.cat([accepted, rejected, rejected & (own_peer(detail) == -4),
                             (code == 3) & (mode == 2)], dim=2).float()
        adjust = None
        if mode == 2:
            if shuffle:
                leaf, anchor = leaf.flip(1), anchor.flip(1)
            actions = torch.arange(LEAVES * RANKS, device=features.device)
            same = ((own_peer(leaf)[..., None] == actions // RANKS) &
                    (own_peer(anchor)[..., None] == features[:, None, None, :, 0]))
            offset = 4 * int(wave == 0)
            closed = (accepted | (code == 3)).float()
            value = (closed * self.reply_score[offset:offset+4:2] +
                     rejected * self.reply_score[offset+1:offset+4:2])
            adjust = (same * value[..., None]).sum(2)
        return self.step(features, token, context_adjust=signals @ self.reply_context.T,
                         score_adjust=adjust, forbidden=forbidden)

    def metal_weights(self):
        return super().metal_weights() + torch.cat([self.reply_context.flatten(), self.reply_score]).detach().tolist()


def training_reply(token, labels, closed):
    """Simulator for supervision only. labels are measured GPU route outcomes before RHS dedup."""
    out = []
    for row in range(ROWS):
        leaf, addr, rank, active = token[:, row, -4:].long().unbind(-1)
        idx = ((leaf - 1) * RANKS + rank - 1).clamp_min(0)[:, None]
        fact = labels.gather(1, idx).squeeze(1)
        present = active.bool()
        duplicate = closed.gather(1, idx).squeeze(1)
        accepted = present & ~duplicate & (fact == 1)
        code = torch.where(duplicate, 3, torch.where(accepted, 1, 2)) * active
        detail = torch.where(code == 2, fact, -1)
        out.append(torch.stack([code, leaf-1, addr-1, detail], -1))
        closed = closed.scatter(1, idx, (duplicate | accepted)[:, None])
    return torch.stack(out, 1), closed


def train(data, dest, seed, mode, updates):
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    summary = json.loads((data/'summary.json').read_text())
    names = [n for n, s in summary.items() if s['split'] == 'train']
    assert len(names) == 4
    datasets = []
    for name in names:
        with np.load(data/name/'training.npz') as z:
            arrays = tuple(torch.from_numpy(z[k]) for k in ('features','positive','receipt'))
            datasets.append((arrays, np.flatnonzero(arrays[1].any(1).numpy())))
    model = FeedbackActor()
    optimizer = torch.optim.Adam(model.parameters(), lr=.007)
    losses = []
    for step in range(updates):
        samples = []
        for j in range(12):
            arrays, active = datasets[int(rng.integers(len(datasets)))]
            end = int(rng.choice(active)) if j % 2 == 0 else int(rng.integers(11, len(arrays[0])))
            start = max(0, end - 11)
            samples.append(tuple(x[start:start+12] for x in arrays))
        features, positives, labels = map(torch.stack, zip(*samples))
        token = torch.zeros(len(samples), ROWS, HIDDEN+4)
        reply = torch.zeros(len(samples), ROWS, 4, dtype=torch.long)
        loss = 0
        for t in range(features.shape[1]):
            closed = torch.zeros_like(positives[:, t])
            for wave in range(2):
                logits, token = model.propose(features[:, t], token, reply, wave, mode)
                loss = loss + set_loss(logits, positives[:, t] & ~closed)
                reply, closed = training_reply(token.detach(), labels[:, t], closed)
        loss = loss / (2 * features.shape[1])
        optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(model.parameters(), 1.)
        optimizer.step()
        if step % 40 == 0:
            losses.append(float(loss.detach()))
    dest.mkdir(parents=True, exist_ok=False)
    torch.save(model.state_dict(), dest/'actor.pt')
    checkpoint = dict(schema='eggfuse.recurrent-receipts/v1', rows=ROWS, hidden=HIDDEN, ranks=RANKS,
                      leaves=LEAVES, waves=2, feedback=mode, train=names, seed=seed, updates=updates,
                      loss_every_40=losses, weights=model.metal_weights())
    (dest/'actor.json').write_text(json.dumps(checkpoint, separators=(',', ':'))+'\n')
    print(dest, losses, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('data', type=Path)
    p.add_argument('--updates', type=int, default=480)
    p.add_argument('--seeds', type=int, nargs='+', default=[1703,1709])
    p.add_argument('--modes', type=int, nargs='+', default=[0,1,2], choices=[0,1,2])
    args = p.parse_args()
    for seed in args.seeds:
        for mode in args.modes:
            train(args.data, args.data/f'train-{seed}-{mode}', seed, mode, args.updates)
