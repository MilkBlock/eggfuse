"""Verify four physical graph representations and matched transport on the frozen corpus."""
import argparse
import hashlib
import json
from pathlib import Path

import torch

from encoder import EClassEncoder, EClassSchema, select_state


def physical_relation(view, arm):
    ports = view.port_nodes
    aliases = view.adjacency[-1].index_select(0, ports)
    if arm == 'pairwise':
        alias = aliases.index_select(1, ports) > 0
        return alias | torch.eye(len(ports), device=ports.device, dtype=torch.bool)
    membership = (aliases[:, view.stats['base_nodes']:] > 0).float()
    return (membership @ membership.T) > 0


def check_template(template, schema, encoder, device):
    pair = schema.bank(template, 'pairwise', device)
    incidence = schema.bank(template, 'incidence', device)
    explicit = schema.bank(template, 'explicit', device)
    singleton = schema.bank(template, 'singleton', device)
    count = len(template['ports'])
    identity = torch.eye(count, device=device, dtype=torch.bool)
    committed_relation = None
    for state, (i, j) in enumerate(zip(pair.indices, incidence.indices)):
        first = physical_relation(pair.views[i], 'pairwise')
        second = physical_relation(incidence.views[j], 'incidence')
        torch.testing.assert_close(first, second, rtol=0, atol=0)
        if state < 3:
            torch.testing.assert_close(first, identity, rtol=0, atol=0)
        else:
            committed_relation = first
            for cert in template['certificates']:
                if cert['visible_from_stage'] == 1:
                    assert bool(first[cert['left_port'], cert['right_port']])
    assert len(explicit.views) == len(singleton.views) == 1
    table = encoder.frozen_bank(incidence)
    assert table is encoder.frozen_bank(incidence)
    used = select_state(table, torch.tensor([1, 1], device=device), torch.tensor([True, False], device=device))
    torch.testing.assert_close(used[0], table[3], rtol=0, atol=0)
    torch.testing.assert_close(used[1], table[0], rtol=0, atol=0)
    matched = [encoder.frozen_bank(schema.bank(template, arm, device, 'matched'))
               for arm in ('pairwise', 'incidence')]
    torch.testing.assert_close(*matched, rtol=2e-5, atol=2e-6)
    return dict(ports=count, certified_pairs=int((committed_relation & ~identity).sum().item()) // 2,
                pair_post=pair.views[pair.indices[3]].stats, incidence_post=incidence.views[incidence.indices[3]].stats,
                matched_max_abs=float((matched[0]-matched[1]).abs().max()))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest', type=Path)
    p.add_argument('report', type=Path)
    p.add_argument('--device', choices=('cpu', 'mps'), default='cpu')
    args = p.parse_args()
    templates = json.loads(args.manifest.read_text())['templates']
    training = [t for t in templates if t['split']=='train']
    if not training:
        raise ValueError('empty training vocabulary')
    schema = EClassSchema(training)
    torch.set_num_threads(1)
    torch.manual_seed(1703)
    encoder = EClassEncoder(schema).to(args.device).eval()
    with torch.inference_mode():
        records = {t['id']:check_template(t, schema, encoder, args.device) for t in templates}
    report = dict(templates=len(records), manifest_sha256=hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
                  device=args.device, encoder_parameters=sum(p.numel() for p in encoder.parameters()), records=records,
                  scope='untrained encoder structural audit, every port and local receipt state; no neural accuracy claim')
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='records'}))


if __name__ == '__main__':
    main()
