"""Offline supervised fitting; one GPU rollout followed by independent CPU audit."""
import argparse, hashlib, json, time, sys, platform
from importlib.metadata import version
from pathlib import Path
import numpy as np
import mlx.core as mx
import mlx.optimizers as optim
import mlx.nn as nn
from schema import SPECS, OFFSETS
from model import CellNet, loss, discrete
from contract import batch, seed_inputs, verify, headers_at, decoded_host, audit_result


def corpus(tags):
    return np.array([(equal, same, slot, int(tag)) for equal in range(2) for same in range(2)
                     for slot in range(5) for tag in tags], np.int32)


def positions(n, rng, heldout=False):
    start = rng.integers(1024 if heldout else 0, 4000 if heldout else 64, n)
    gaps = rng.integers(9 if heldout else 1, 40 if heldout else 9, (n, 2))
    return np.column_stack((start, start + gaps[:, 0], start + gaps.sum(axis=1))).astype(np.int32)


def as_host(result):
    mx.eval(result)
    return {k: np.array(v) for k, v in result.items()}



def main():
    p = argparse.ArgumentParser()
    p.add_argument('output', type=Path); p.add_argument('--steps', type=int, default=3000)
    p.add_argument('--weights', type=Path); a = p.parse_args()
    if not mx.metal.is_available(): raise RuntimeError('Metal GPU is required; no CPU fallback')
    mx.set_default_device(mx.gpu); mx.random.seed(1703)
    a.output.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(1703)
    tags = rng.permutation(256)
    # Keep the illustrated annotation 0xA5 out of training.
    index = int(np.flatnonzero(tags == 165)[0]); tags[index], tags[-1] = tags[-1], tags[index]
    train = corpus(tags[:192]); heldout = corpus(tags[192:])
    x, y = batch(train); tx = seed_inputs(heldout)
    validation_pos = positions(len(train), np.random.default_rng(991), True)
    test_pos = positions(len(heldout), np.random.default_rng(993), True)
    model = CellNet(); training = []
    if a.weights:
        model.load_weights(str(a.weights))
    else:
        opt = optim.Adam(learning_rate=2e-3)
        value_grad = nn.value_and_grad(model, loss)
        start = time.perf_counter()
        for step in range(a.steps):
            ix = rng.integers(0, len(train), 128)
            value, gradients = value_grad(model, mx.array(x[ix]), mx.array(positions(len(ix), rng)),
                                         {k: mx.array(v[:, ix]) for k, v in y.items()})
            opt.update(model, gradients); mx.eval(value, model.parameters(), opt.state)
            if step % 250 == 0 or step == a.steps - 1:
                record = dict(step=step + 1, loss=float(value), seconds=time.perf_counter() - start)
                training.append(record); print(json.dumps(record), flush=True)
        model.save_weights(str(a.output / 'model.safetensors'))
    # No reference labels, proofs, layouts or decoded states are inputs to this function.
    run = mx.compile(lambda seed, pos: model.rollout(seed, pos))
    val = as_host(run(mx.array(x), mx.array(validation_pos)))
    predicted_device = run(mx.array(tx), mx.array(test_pos))
    prediction = as_host(predicted_device)
    main_case = np.array([[0, 1, 2, 165]], np.int32)
    main_seed = seed_inputs(main_case); main_pos = np.array([[0, 5, 9]], np.int32)
    illustrated = as_host(run(mx.array(main_seed), mx.array(main_pos)))
    # Runtime interventions finish on GPU before the CPU sees results.
    interventions = {}
    transferred = (heldout[:, 0] | heldout[:, 1]).astype(bool)
    for mode in ['zero', 'random', 'nan']:
        f = mx.compile(lambda seed, pos: model.rollout(seed, pos, mode))
        poisoned = as_host(f(mx.array(tx), mx.array(test_pos)))
        keys = ['read_roles', 'read_ports', 'read_payload', 'read_eq', 'read_valid']
        interventions[mode] = dict(
            checked_cases=int(transferred.sum()),
            unchanged=all(np.array_equal(prediction[k][transferred], poisoned[k][transferred]) for k in keys),
            old_active=int(poisoned['active_bank'][transferred, 0].sum()),
            old_visible_values=int(np.count_nonzero(poisoned['active_bank_contents'][transferred, 0])),
        )
    query_order = [3, 0, 2, 1]
    query = mx.broadcast_to(mx.array(query_order), (len(heldout), 4))
    # This read uses generated checkpoints only; no original seed is supplied.
    permuted = as_host(model.read_old(predicted_device['tokens'][2], predicted_device['locations'][2],
        predicted_device['owners'][2], predicted_device['tokens'][1], mx.array(test_pos), 'nan', query))
    permutation_read = dict(checked_cases=int(transferred.sum()), order=query_order,
        roles_follow_query=bool(np.all(permuted['read_roles'][transferred] == np.array(query_order))),
        ports_follow_query=bool(np.array_equal(permuted['read_ports'][transferred], prediction['read_ports'][transferred][:, query_order])),
        all_valid=bool(permuted['read_valid'][transferred].all()))
    # CPU verification begins here; it never returns a replacement state to the GPU.
    decoder_weight, decoder_bias = np.array(model.decoder.weight), np.array(model.decoder.bias)
    def audit(cases, pos, result):
        return audit_result(cases, pos, result, decoder_weight, decoder_bias)
    validation = audit(train, validation_pos, val)
    result = audit(heldout, test_pos, prediction)
    main_check = audit(main_case, main_pos, illustrated)
    header = decoded_host(illustrated['logits'])
    # Tampering must be rejected by the independent semantic checker.
    from copy import deepcopy
    h = headers_at(header, 0)
    forged = {}
    def reject(name, mutate):
        v = deepcopy(h); mutate(v); forged[name] = bool(verify(main_case[0], v))
    reject('wrong_premise', lambda v: v[1]['premises'].__setitem__(0, 0))
    reject('false_union', lambda v: v[1]['eq'].__setitem__(1, 1))
    reject('early_publication', lambda v: v[0]['layout'].__setitem__(4, 4))
    reject('wrong_projection', lambda v: v[2]['alias'].__setitem__(2, 2))
    reject('lost_old_information', lambda v: v[2]['payload'].__setitem__(0, 1 - v[2]['payload'][0]))
    negative = np.array([[0, 0, 2, 165]], np.int32)
    neg_seed = seed_inputs(negative)
    neg_run = as_host(run(mx.array(neg_seed), mx.array(main_pos)))
    neg_h = headers_at(decoded_host(neg_run['logits']), 0)
    neg_h[2]['pending'][1] = 0
    forged['lost_pending_obligation'] = bool(verify(negative[0], neg_h))
    forged_record = {k: v.copy() for k, v in illustrated.items()}
    lo, hi = OFFSETS['premises']
    forged_record['logits'][1, 0, lo:hi] = 0
    forged['advertised_proof_not_in_latent'] = not audit(main_case, main_pos, forged_record)['accepted']
    forged_record = {k: v.copy() for k, v in illustrated.items()}
    forged_record['locations'][2, 0] += 1
    forged['wrong_rotary_owner_position'] = not audit(main_case, main_pos, forged_record)['accepted']
    # Actual forward causality: no detached teacher first/second token can satisfy these probes.
    seed = mx.array(main_seed); pos = mx.array(main_pos)
    gradient = mx.grad(lambda inp: mx.sum(model.rollout(inp, pos)['logits'][2] ** 2))(seed)
    mx.eval(gradient)
    corrupted = mx.zeros_like(mx.array(illustrated['tokens'][1]))
    _, _, corrupted_logits, _ = model.advance(corrupted, mx.array(illustrated['locations'][1]), 2, pos)
    mx.eval(corrupted_logits)
    corrupted_h = deepcopy(h); d = discrete(corrupted_logits)
    corrupted_h[2] = {k: np.array(v)[0].tolist() for k, v in d.items()}
    lineage = dict(third_loss_gradient_to_initial_seed=float(mx.max(mx.abs(gradient))),
                   corrupt_second_latent_rejected=bool(verify(main_case[0], corrupted_h)))
    successful = (result['accepted'] and validation['accepted'] and main_check['accepted'] and all(x['unchanged'] and x['old_active'] == 0 and x['old_visible_values'] == 0 for x in interventions.values())
                  and all(forged.values()) and lineage['third_loss_gradient_to_initial_seed'] > 0
                  and lineage['corrupt_second_latent_rejected'] and permutation_read['roles_follow_query']
                  and permutation_read['ports_follow_query'] and permutation_read['all_valid'])
    weight_path = a.weights or a.output / 'model.safetensors'
    evidence = dict(scope='bounded learned Seed/F/G latent/proof prototype, not full eggcc or general egraph',
        status='pass' if successful else 'difference', device=str(mx.default_device()),
        environment=dict(platform=platform.platform(), python=platform.python_version(), mlx=version('mlx'), numpy=version('numpy')),
        training_cases=len(train), heldout_cases=len(heldout), training_tags=tags[:192].tolist(), heldout_tags=tags[192:].tolist(),
        split_scope='all 20 semantic/layout patterns occur in training; held-out annotation combinations and positions only',
        validation=validation, heldout=result, example=dict(case=main_case[0].tolist(), positions=main_pos[0].tolist(), headers=h, reads=illustrated['read_roles'][0].tolist()),
        retired_payload_interventions=interventions, reordered_reference_reads=permutation_read, tampering_rejected=forged, lineage=lineage,
        source_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob('*.py'))},
        checkpoint_sha256=hashlib.sha256(weight_path.read_bytes()).hexdigest(), training=training,
        cpu_corrections=0, teacher_latents_used_in_rollout=False, input_seed_encodings_per_rollout=1,
        model_origin=str(weight_path),
        active_transfer_scope='old A removed from the read bank after neural retirement; audit checkpoints remain separately retained',
        limitations=['No arbitrary operator/ruleset, external constructor collision, mutable function or scalar arithmetic coverage',
                     'Initial a,b are symbolic handles and carry no learned numeric ID',
                     'Fixed three-Run schedule; no learned global stopping or dynamic candidate enumeration',
                     'Model accuracy is empirically verified on a finite domain, not universally proved',
                     'Rotation coordinates change token bytes; no bitwise equality across positions or permutation-invariance claim',
                     'Static GPU routing, argmax, masking and rotary operations remain outside the learned transition',
                     'No online Bake or automatically discovered proof vocabulary in this prototype',
                     'Audit checkpoint storage and host transfers are retained; no compression or speedup claim'])
    (a.output / 'result.json').write_text(json.dumps(evidence, indent=2) + '\n')
    np.savez_compressed(a.output / 'audit-checkpoints.npz', cases=heldout, positions=test_pos,
                        decoder_weight=decoder_weight, decoder_bias=decoder_bias, **prediction)
    print(json.dumps(dict(status=evidence['status'], validation=validation['passed'], heldout=result['passed'], total=result['cases'],
                         interventions=interventions, tampering=forged, lineage=lineage)), flush=True)
    if not successful: sys.exit(1)

if __name__ == '__main__': main()
