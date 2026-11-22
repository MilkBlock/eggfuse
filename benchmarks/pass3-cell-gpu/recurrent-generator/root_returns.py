"""Parameter-space policy search on the second issuer, with paired source executions."""
import argparse
import json
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import torch

from capture import execute, inputs, load_catalog, read, verify
from chain_check import serial_compiler
from compound_model import CompoundActor, compiled_actions
from fept import retained, measure


def train(args):
    if args.updates < 1 or args.radius <= 0 or args.rate <= 0 or args.cost_weight <= 0:
        raise ValueError("updates, radius, rate and cost weight must be positive")
    if not 0 < args.coverage_floor <= 1:
        raise ValueError("coverage floor must be in (0,1]")
    torch.set_num_threads(1)
    rng = np.random.default_rng(args.seed)
    model = read(args.checkpoint / 'policy.json')
    release = args.exp / 'pass3-release-reproduction-20261120'
    donor = release / 'sum-bits/program.json'
    joins, tails, wires = compiled_actions(read(donor), model['three_step'])
    actor = CompoundActor(joins, wires)
    actor.load_state_dict(torch.load(args.checkpoint / 'actor.pt', weights_only=True))
    row = actor.root.rows[1].detach()
    abstain = actor.root.abstain[-1].detach()
    center = row.numpy().copy()
    if args.tune_stop:
        center = np.append(center, abstain.item()).astype(center.dtype)

    def install(vector):
        row.copy_(torch.from_numpy(vector[:row.numel()]))
        if args.tune_stop:
            abstain.fill_(float(vector[-1]))
    cases = []
    for name in model['train']:
        image, program, gold = inputs(args.exp / 'repair-bake-families-20261120', release, name)
        source = args.source / name
        cases.append((image, gold, load_catalog(image, program, donor), source, retained(source, image)))

    args.out.mkdir(parents=True, exist_ok=False)
    with TemporaryDirectory() as tmp:
        libraries = {}
        def compile_kernel(code):
            digest = hashlib.sha256(code.encode()).hexdigest()
            if digest not in libraries:
                path = Path(tmp) / digest
                path.mkdir()
                libraries[digest] = serial_compiler(path)(code)
            return libraries[digest]

        def rollout(vector):
            install(vector)
            totals = []
            for image, gold, catalog, source, counts in cases:
                policy = dict(catalog=catalog, rows=2, ranks=8, hidden=8, waves=2,
                              weights=actor.root.metal_weights(), compound=dict(
                                  joins=joins, tails=tails, wires=wires, batch=True,
                                  named_boundary=True, child=model['child']))
                with TemporaryDirectory(dir=tmp) as output:
                    dest = Path(output) / 'run'
                    execute(image/'device.json', args.exp/'rotary-axes-20261119/packed-1703/final.pt',
                            release/'ports-1703.pt', 2048, 2, dest, neural=policy,
                            serial_compile=compile_kernel, count_work=True, birth_audit=True)
                    verify(dest, gold, image)
                    result = measure(dest, source, counts)
                    totals.append([result['rust_visible'], result['issued']])
            return np.asarray(totals)

        baseline = rollout(center)
        if not baseline[:, 1].sum():
            raise ValueError("training reference issued zero proposals")
        rho = baseline[:, 0].sum() / baseline[:, 1].sum()
        best = center.copy()
        best_gain = 0.
        def utility(results):
            change = results - baseline
            return float(change[:,0].sum() - args.cost_weight * rho * change[:,1].sum())

        log = []
        for iteration in range(args.updates):
            # Both arms see exactly the same four workloads and compiler bank.
            direction = rng.standard_normal(center.shape).astype(center.dtype)
            trial = [center + sign * args.radius * direction for sign in (1, -1)]
            outcomes = [rollout(candidate) for candidate in trial]
            gains = [utility(outcome) for outcome in outcomes]
            for candidate, outcome, gain in zip(trial, outcomes, gains):
                enough = np.all(outcome[:,0] >= args.coverage_floor * baseline[:,0])
                within_budget = not args.tune_stop or outcome[:,1].sum() < baseline[:,1].sum()
                if enough and within_budget and gain > best_gain:
                    best, best_gain = candidate.copy(), gain
            log.append(dict(iteration=iteration, arms=[x.tolist() for x in outcomes], gains=gains,
                            best_gain=best_gain))
            # Antithetic score-function gradient for an isotropic Gaussian policy.
            center += args.rate * np.clip((gains[0]-gains[1])/(2*args.radius), -3, 3) * direction
            print(iteration, gains, best_gain, flush=True)
            install(best)
            model['roots'] = actor.root.metal_weights()
            (args.out/'policy.json').write_text(json.dumps(model,separators=(',',':'))+'\n')
            torch.save(actor.state_dict(),args.out/'actor.pt')
            (args.out/'training.json').write_text(json.dumps(dict(
                cases=model['train'],baseline=baseline.tolist(),rho=rho,seed=args.seed,
                radius=args.radius,rate=args.rate,cost_weight=args.cost_weight,
                coverage_floor=args.coverage_floor,tune_stop=args.tune_stop,updates=log),indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('exp','source','checkpoint','out'):
        parser.add_argument(arg,type=Path)
    parser.add_argument('--seed',type=int,default=1703)
    parser.add_argument('--updates',type=int,default=24)
    parser.add_argument('--radius',type=float,default=0.75)
    parser.add_argument('--rate',type=float,default=0.15)
    parser.add_argument('--cost-weight',type=float,default=1.)
    parser.add_argument('--tune-stop',action='store_true')
    parser.add_argument('--coverage-floor',type=float,default=1.)
    train(parser.parse_args())
