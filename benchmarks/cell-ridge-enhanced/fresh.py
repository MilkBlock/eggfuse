"""Additional fixed sequences after model selection; no fitting or correction."""
import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np


def load_module(path, name):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    old_path = root/'benchmarks/cell-real-algebra/study.py'
    new_path = Path(__file__).parent/'anchored.py'
    old = load_module(old_path, 'old_ridge')
    new = load_module(new_path, 'new_ridge')
    _, facts, target, train, valid, test = old.t.dataset()
    models = {'baseline': old.load_adapter(args.baseline), 'candidate': new.load_adapter(args.candidate)}
    results = {}
    for name, model in models.items():
        rows = []
        for seed, length in ((49999, 12), (67867967, 48), (32452843, 96)):
            ids = np.tile(np.flatnonzero(test), 4)
            z = model.encode(facts[ids])
            actions = np.random.default_rng(seed).integers(0, 17, (length, len(ids)))
            actions[2] = 15; actions[5] = 16; actions[8] = actions[7]
            exact = np.ones(len(ids), dtype=bool)
            for a in actions:
                z = model.step(z, a)
                ids = target[ids, a]
                out = model.decode(z)
                exact &= np.isfinite(z).all(1) & np.isfinite(out).all(1) & ((out >= .5) == facts[ids]).all(1)
            rows.append(dict(seed=seed, steps=length, trajectories=len(ids), all_steps_exact=int(exact.sum())))
        results[name] = rows
    results['source_sha256'] = {str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest()
                               for path in (old_path, new_path, Path(__file__), new_path.parent/'study.py')}
    results['weights_sha256'] = {name:hashlib.sha256(path.read_bytes()).hexdigest()
                                for name, path in (('baseline', args.baseline), ('candidate', args.candidate))}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2)+'\n')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
