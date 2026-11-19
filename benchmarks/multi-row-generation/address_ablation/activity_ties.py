"""Resolve tied address scores with the activation bit carried by the generated Pair."""
import argparse
import json
import os
from pathlib import Path

import numpy as np
import torch

from trace_transfer import (
    FIG20, LAYOUTS, AddressModel, aggregate, check_saved, coordinates, figure20_data,
    host, project_parent, request_metrics, sha,
)


def select(scores, active, prefer_active):
    top = scores == scores.amax(dim=-1, keepdim=True)
    if prefer_active:
        live_top = top & active[:, None, :]
        top = torch.where(live_top.any(dim=-1, keepdim=True), live_top, top)
    return top.to(torch.int32).argmax(dim=-1)


@torch.inference_mode()
def run(address_root, producer_root):
    if not torch.backends.mps.is_available() or os.environ.get('PYTORCH_ENABLE_MPS_FALLBACK') != '0':
        raise RuntimeError('MPS with fallback disabled required')
    baseline_file = address_root / 'trace-transfer.json'
    baseline = json.loads(baseline_file.read_text())
    hashes = {baseline_file.name: sha(baseline_file)}
    source = figure20_data()
    manifest = json.loads((FIG20 / 'corpus/manifest.json').read_text())
    panels = {}
    for seed in (1703, 1709):
        checkpoint = address_root / f'packed-{seed}' / 'final.pt'
        hashes[f'packed-{seed}'] = sha(checkpoint)
        assert hashes[f'packed-{seed}'] == baseline['trace_and_weight_hashes'][str(checkpoint)]
        model = AddressModel('packed').eval().to('mps')
        model.load_state_dict(torch.load(checkpoint, map_location='cpu', weights_only=True))
        for template in manifest['templates']:
            if template['split'] != 'heldout':
                continue
            tid = template['id']
            data = source.dataset('test', template)
            path = producer_root / 'traces' / f'{tid}-pairwise-{seed}.npz'
            hashes[path.name] = sha(path)
            assert hashes[path.name] == baseline['trace_and_weight_hashes'][str(path)]
            with np.load(path, allow_pickle=False) as saved:
                token = saved['token']
                first, second = ({k: saved[f'{stage}_{k}'] for k in ('active','pointers','rows')}
                                 for stage in range(2))
            device_token = torch.as_tensor(token, device='mps')
            rows = device_token[..., 50:55].long()
            active = device_token[..., 32:34].argmax(-1).bool()
            requests = torch.as_tensor(data['requests'], device='mps')
            consumer_active = torch.as_tensor(second['active'], device='mps')
            consumer_request = torch.as_tensor(second['pointers'][..., 1], device='mps').long()
            for layout in LAYOUTS:
                query, length, ports = coordinates(requests[..., 2:4], layout)
                bank, _, _ = coordinates(rows[..., :2], layout)
                decisions = {}
                for order in ('original', 'reversed'):
                    slots = torch.arange(rows.shape[1], device='mps')
                    if order == 'reversed':
                        slots = slots.flip((0,))
                    scores = model.address_scores('make', query, bank[:, slots], length, ports)
                    for prefer in (False, True):
                        parent = slots[select(scores, active[:, slots], prefer)]
                        emitted = project_parent(rows, requests, consumer_active, consumer_request, parent)
                        decisions[order, prefer] = (host(parent), host(scores[..., slots]),
                                                     {k: host(v) for k, v in emitted.items()})
                # Independent provenance and legality audit begins after all choices are made.
                valid = check_saved(data, token, first)
                legal = np.asarray(source.audit(data, first, second)['request_legal'], dtype=bool)
                reference = baseline['by_panel'][f'{layout}/packed-{seed}'][tid]
                for (order, prefer), (picks, scores, emitted) in decisions.items():
                    metrics, _ = request_metrics(data, first, valid, legal, picks, scores)
                    endpoint = source.audit(data, first, emitted)['run2']
                    if order == 'original' and not prefer:
                        assert metrics == reference['requests']
                        assert endpoint['nonempty_complete_graphs'] == reference['nonempty_complete_after']
                    original = decisions['original', prefer][0]
                    row = dict(legal=int(legal.sum()), correct=metrics['all']['ready_correct'],
                               inactive=metrics['all']['ready_inactive_selected'],
                               legal_physical_slot_changed=int(((picks != original) & legal).sum()))
                    for k in ('nonempty_complete_graphs', 'wrong_parent', 'absent_parent',
                              'illegal_producer', 'duplicates', 'missing', 'illegal'):
                        row[k] = endpoint[k]
                    arm = 'active_tie' if prefer else 'address_only'
                    panels.setdefault(f'{seed}/{layout}/{arm}/{order}', {})[tid] = row
    return dict(device='mps', scope='frozen frontier intervention', input_sha256=hashes,
                panels=panels, totals={k: aggregate(list(v.values())) for k, v in panels.items()})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('address_root', 'producer_root', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    result = run(args.address_root, args.producer_root)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
