"""Predict native child credits of a named graph request using shared graph weights."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F

from alternate_proofs import digest
from higher_cell import read
from ripsat_replay import unpack
from train_layout_bandit import fixed_features
from train_ripsat import layout_id


COUNTS = ('uncontested_effects', 'owned_valid', 'failed_steps')
BAKE_FILES = ('codes.pt', 'catalog.json', 'shared.pt', 'boundary.pt')


def graph_inputs(baked):
    features, _ = fixed_features(baked)
    descriptors = []
    for graph in unpack(read(baked/'catalog.json')):
        root_inputs = {slot for _, slot in graph[0][2]}
        inputs = {s for _, _, wires in graph for parent, s in wires if parent < 0}
        fanout = Counter((parent, s) for _, _, wires in graph for parent, s in wires if parent >= 0)
        groups = Counter(group for _, group, _ in graph)
        descriptors.append([len(inputs-root_inputs), len(fanout), sum(fanout.values()),
                            max(fanout.values(), default=0), max(groups.values())])
    extra = torch.tensor(descriptors, dtype=features.dtype).log1p()
    return torch.cat((features[1:], extra), dim=1)


class ReceiptValue(nn.Module):
    def __init__(self, context_width, graph_width):
        super().__init__()
        self.key = nn.Sequential(nn.Linear(graph_width, 48), nn.Tanh(), nn.Linear(48, 48))
        self.query = nn.Sequential(nn.Linear(context_width, 32), nn.Tanh(), nn.Linear(32, 48))
        self.bias = nn.Linear(48, len(COUNTS))

    def forward(self, context, key):
        q = self.query(context).reshape(-1, len(COUNTS), 16)
        return ((q * key.reshape(-1, len(COUNTS), 16)).sum(-1) / 4 + self.bias(key)).clamp(-14, 8)


def load_rows(logs, baked):
    study = read(baked/'study.json')
    sha = {k: digest(baked/k) for k in BAKE_FILES}
    held = {u for u, g in enumerate(unpack(read(baked/'catalog.json')))
            if int(layout_id(g)[:8], 16) % 8 == 0}
    files = {}
    provenance = {}
    common = set()
    for path in sorted(logs.glob('*.json')):
        report = read(path)
        program, seed = report['program'], report['seed']
        if (not all(report[k] for k in ('omit', 'attach', 'explore'))
                or report['policy'] is not None or report['catalog'] != sha['catalog.json']
                or report['scorer'] != sha['shared.pt'] or report['reader'] != sha['boundary.pt']
                or report['actor'] != study['root_weights'] or report['tape'] != study['training'][program]):
            raise ValueError('incompatible native exploration')
        key = (program, seed)
        if key in files:
            raise ValueError('duplicate native episode')
        common.add((report['binary'], json.dumps(report.get('recovery'), sort_keys=True)))
        path = path.with_suffix('.json.gz')
        provenance[path.name] = digest(path)
        with gzip.open(path, 'rt') as stream:
            log = json.load(stream)
        if any(held.intersection(menu) for menu in log['menus']):
            raise ValueError('withheld graph in exploration menu')
        rows = []
        sums = Counter()
        for menu, x, u, propensity, _, counts, _ in log['rows']:
            if u is None:
                if any(counts.values()):
                    raise ValueError('standalone issued an internal step')
                continue
            if not 0 < propensity <= 1 or u not in log['menus'][menu]:
                raise ValueError('invalid graph action')
            rows.append((x, u, [counts.get(k, 0) for k in COUNTS]))
            sums.update(counts)
        if any(sums[k] != report['credit'].get(k, 0) for k in COUNTS):
            raise ValueError('training targets differ from native aggregate')
        files[key] = rows
    seeds = sorted({s for _, s in files})
    if (len(common) != 1 or len(seeds) < 2 or
            set(files) != {(p, s) for p in study['training'] for s in seeds}):
        raise ValueError('expected crossed training-program and rollout-seed data')
    def pack(keys):
        rows = [row for key in keys for row in files[key]]
        x, u, y = zip(*rows, strict=True)
        return torch.tensor(x), torch.tensor(u), torch.tensor(y, dtype=torch.float)
    return (pack([k for k in files if k[1] != seeds[-1]]),
            pack([k for k in files if k[1] == seeds[-1]]), seeds, sha, provenance, common.pop())


def fit(logs, baked, out, epochs):
    train, valid, seeds, sha, provenance, (binary, recovery) = load_rows(logs, baked)
    device = 'mps'
    graphs = graph_inputs(baked).to(device)
    torch.manual_seed(1703)
    model = ReceiptValue(train[0].shape[1], graphs.shape[1]).to(device)
    rate = train[2].mean(0).to(device)
    if not torch.all(rate > 0):
        raise ValueError('missing native outcome category')
    with torch.no_grad():
        model.bias.bias.copy_(rate.log())
    opt = torch.optim.AdamW(model.parameters(), lr=.002)
    train = [t.to(device) for t in train]
    valid = [t.to(device) for t in valid]
    def loss(batch, ix):
        x, u, y = batch
        logs = model(x[ix], model.key(graphs[u[ix]]))
        return (F.poisson_nll_loss(logs, y[ix], reduction='none') / rate).mean()
    best = float('inf')
    history = []
    for epoch in range(epochs):
        for ix in torch.randperm(len(train[0])).split(512):
            value = loss(train, ix.to(device))
            opt.zero_grad()
            value.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 2)
            opt.step()
        with torch.no_grad():
            score = sum(float(loss(valid, ix.to(device))) * len(ix)
                        for ix in torch.arange(len(valid[0])).split(1024)) / len(valid[0])
        history.append(score)
        if score < best:
            best, selected = score, epoch + 1
            state = {k: t.detach().cpu().clone() for k, t in model.state_dict().items()}
    out.mkdir(parents=True, exist_ok=True)
    frozen = model.cpu().eval()
    frozen.load_state_dict(state)
    with torch.no_grad():
        keys = frozen.key(graphs.cpu())
        torch.save(dict(keys=keys, bias=frozen.bias(keys)), out/'values.pt')
    torch.save(state, out/'policy.pt')
    report = dict(objective='native_receipt_value', bake=sha, policy=digest(out/'policy.pt'),
                  compiled=digest(out/'values.pt'), counts=COUNTS, prices=[1., .25, -.0625], device=device, selected_epoch=selected,
                  validation_loss=history, training_seeds=seeds[:-1], validation_seed=seeds[-1],
                  training_actions=len(train[0]), validation_actions=len(valid[0]), binary=binary,
                  recovery=json.loads(recovery), training_counts=train[2].sum(0).cpu().tolist(),
                  context_width=train[0].shape[1], episodes=provenance)
    (out/'training.json').write_text(json.dumps(report, indent=2)+'\n')


class ReceiptChoice:
    static_scores = None

    def __init__(self, folder, baked):
        info = read(folder/'training.json')
        if (info['objective'] != 'native_receipt_value' or tuple(info['counts']) != COUNTS or
                any(info['bake'][k] != digest(baked/k) for k in BAKE_FILES) or
                info['policy'] != digest(folder/'policy.pt')):
            raise ValueError('incompatible receipt policy')
        self.checkpoint = info['policy']
        if info['compiled'] != digest(folder/'values.pt'):
            raise ValueError('compiled receipt action keys changed')
        weights = torch.load(folder/'policy.pt', weights_only=True)
        self.model = ReceiptValue(info['context_width'], weights['key.0.weight'].shape[1]).eval()
        self.model.load_state_dict(weights)
        self.prices = torch.tensor(info['prices'])
        fixed = torch.load(folder/'values.pt', weights_only=True)
        self.keys = fixed['keys'].reshape(-1, len(COUNTS), 16)
        self.bias = fixed['bias']

    def select(self, req, options, context, issuer):
        q = self.model.query(context).view(len(COUNTS), 16)
        ids = torch.as_tensor(options)
        rates = ((self.keys[ids] * q).sum(-1) / 4 + self.bias[ids]).clamp(-14, 8).exp()
        values = rates @ self.prices
        best = int(values.argmax())
        issuer.claim_counts['receipt_value_decisions'] += 1
        return options[best] if values[best] > 0 else None


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('logs', 'baked', 'out'):
        p.add_argument(key, type=Path)
    p.add_argument('--epochs', type=int, default=24)
    a = p.parse_args()
    torch.set_num_threads(1)
    fit(a.logs, a.baked, a.out, a.epochs)
