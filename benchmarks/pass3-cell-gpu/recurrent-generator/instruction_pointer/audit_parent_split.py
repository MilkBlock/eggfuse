"""Verify the saved checkpoint lineage, program identities and per-Run label exposure."""
import argparse
from collections import Counter
import json
from pathlib import Path

from alternate_proofs import digest
from entry_coverage import split_runs


def audit(root, calibration):
    def read(p):
        return json.loads(p.read_bytes())
    selected, _, reserved = split_runs(root, 1703)
    train = {r['directory'] for r, _ in selected}
    held = {'fact', 'loopfact', 'sum-divisors'}
    program = {n:digest(root/n/'program.json') for n in train | held}
    if train & held or {program[n] for n in train} & {program[n] for n in held}:
        raise ValueError('workload identity overlap')
    lineage_root = calibration.parent
    foundation = read(lineage_root/'expanded'/'structural'/'training.json')
    field = read(lineage_root/'disagreement'/'training.json')
    foundation_hash = digest(lineage_root/'expanded'/'structural'/'model.pt')
    field_hash = digest(lineage_root/'disagreement'/'model.pt')
    if (foundation_hash != foundation['weights_sha256'] or foundation_hash != field['frozen_sha256']
        or field_hash != field['weights_sha256'] or set(field['native']) - train):
        raise ValueError('incorrect field scorer lineage or exposure')
    exposure = {}
    for name in ('final-parent', 'opaque-parent'):
        stage = calibration/name
        log = read(stage/'training.json')
        if log['weights_sha256'] != digest(stage/'model.pt') or log['initial_sha256'] != digest(calibration/'model.pt'):
            raise ValueError('terminal checkpoint lineage mismatch')
        if set(log['source_exposure']) != train:
            raise ValueError('different training program set')
        counts = Counter()
        by_source = {}
        for n, row in log['source_exposure'].items():
            if {(n,r) for r in row.get('runs', [])} & reserved:
                raise ValueError('calibration Run used to fit terminal head')
            c = row.get('counts', {})
            by_source[n] = sum(v for k,v in c.items() if k not in ('teacher_prefixes','perturbed_prefixes'))
            counts.update(c)
        exposure[name] = dict(total=sum(by_source.values()), by_source=by_source, counts=counts)
    calibrations = []
    for stage in (calibration, calibration/'opaque-parent'/'calibrated'):
        log = read(stage/'training.json')
        used = {(n,r) for n,rs in log['runs'].items() for r in rs}
        if used != reserved or not {n for n,r in used} <= train or log['weights_sha256'] != digest(stage/'model.pt'):
            raise ValueError('unexpected calibration exposure or checkpoint')
        calibrations.append(dict(programs=len(log['runs']), runs=len(used), offsets=log['selected']['offsets'],
                                 weights=log['weights_sha256'], initial=log['initial_sha256']))
    if calibrations[0]['initial'] != field_hash or calibrations[-1]['initial'] != digest(calibration/'opaque-parent'/'model.pt'):
        raise ValueError('incorrect final recalibration')
    return dict(held_programs={n:program[n] for n in sorted(held)}, training_programs={n:program[n] for n in sorted(train)},
                terminal=exposure, calibration=calibrations, field_training_programs=sorted(field['native']),
                foundation_hash=foundation_hash, field_hash=field_hash)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for k in ('root', 'calibration', 'out'):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    a.out.write_text(json.dumps(audit(a.root,a.calibration),indent=2)+'\n')
