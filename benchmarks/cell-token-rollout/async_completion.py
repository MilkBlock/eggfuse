"""Delayed CPU supervision and conservative replay of bounded Cell completion.

Only the SubTuple parameter contract is checked. Hidden channels are not a
proof of graph semantics. A generation invalidates all downstream speculation;
no per-token reverse dependency structure is maintained.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import time

import mlx.core as mx
import numpy as np

from device_stages import advance, initial


def expected(values, capacity):
    offset = np.arange(capacity, dtype=np.float32)[None, :]
    a = values[:, 0, None] + offset
    b = values[:, 1, None] - offset
    return np.stack([a, b, a + b], axis=-1), offset < values[:, 1, None]


def inspect(snapshot, values, readout, bias, gate):
    gate.wait()  # deterministic late-verdict control, not charged as CPU work
    started = time.perf_counter()
    token, live = snapshot
    truth, eligible = expected(values, live.shape[-1])
    decoded = token @ readout + bias
    wrong = live & (np.any(~np.isfinite(decoded), axis=-1) |
                    np.any(np.rint(decoded) != truth, axis=-1))
    missing = eligible & ~live
    unexpected = live & ~eligible
    repair = missing | wrong | unexpected
    marks = [dict(entrance=int(i), slot=int(j), reason=(
        'missing' if missing[i, j] else 'unexpected' if unexpected[i, j] else 'value'))
        for i, j in np.argwhere(repair)]
    return dict(repair=repair, truth=truth, eligible=eligible, marks=marks,
                seconds=time.perf_counter()-started)


def run(proposed, eligible, values, encoder, encoder_bias, readout, bias, *, fault, force_late=True):
    started = time.perf_counter()
    gr, gb = mx.array(readout), mx.array(bias)
    if fault == 'value':
        # A finite, silently wrong full token at each entrance's first slot.
        chosen = mx.arange(proposed.shape[1])[None, :, None] == 0
        proposed = mx.where(chosen, proposed + 100, proposed)
    first = mx.compile(lambda p, e: advance(p, e, gr, gb, initial(p, e, gr),
                                           ticks=2, suppress=fault == 'omission'))
    checkpoint, _ = first(proposed, eligible)
    later = mx.compile(lambda p, e, c: advance(p, e, gr, gb, c, ticks=4))
    speculative, _ = later(proposed, eligible, checkpoint)
    # Submit the downstream stage BEFORE transferring/validating its checkpoint.
    mx.async_eval(speculative)
    copy_started = time.perf_counter()
    snapshot = (np.array(checkpoint[0]), np.array(checkpoint[1]))
    checkpoint_copy_seconds = time.perf_counter()-copy_started
    gate = Event()
    generation = 0
    if not force_late:
        gate.set()
    with ThreadPoolExecutor(max_workers=1) as pool:
        verdict = pool.submit(inspect, snapshot, values, readout, bias, gate)
        try:
            # Force a late CPU verdict: the unverified dependent GPU stage
            # finishes first. This control does not measure natural overlap.
            mx.eval(speculative)
            before_verdict = not verdict.done()
        finally:
            gate.set()
        checked = verdict.result()
    if force_late:
        assert before_verdict
    stale_rejected = False
    repair_started = time.perf_counter()
    if checked['marks']:
        generation += 1
        token = snapshot[0].copy()
        repair = checked['repair']
        # CPU reconstructs ONLY marked tokens under the bounded scalar contract.
        scalar = checked['truth'][repair, :2] / 16
        token[repair] = np.concatenate([scalar, np.tanh(scalar @ encoder + encoder_bias)], axis=-1)
        live = checked['eligible']
        corrected = (mx.array(token), mx.array(live), mx.zeros_like(checkpoint[2]),
                     mx.zeros_like(checkpoint[3]), mx.array(1, dtype=mx.int32))
        stale_rejected = not admissible(0, generation, True)
        assert stale_rejected
        result, _ = later(proposed, eligible, corrected)
        mx.async_eval(result)
    else:
        result = speculative
    _, _, output, mask, stage = result
    output, mask, stage = np.array(output), np.array(mask), int(stage)
    correction_and_replay_seconds = time.perf_counter()-repair_started
    check_started = time.perf_counter()
    truth, expected_mask = expected(values, mask.shape[-1])
    final_ok = (stage == 2 and np.array_equal(mask, expected_mask) and
                np.all(np.isfinite(output[mask])) and
                np.array_equal(np.rint(output[mask]), truth[mask]))
    final_check_seconds = time.perf_counter()-check_started
    assert final_ok and admissible(generation, generation, final_ok)
    # No unverified generation, even one without discovered errors, is accepted.
    assert not admissible(generation, generation, False)
    return dict(fault=fault, forced_late_verdict=force_late, generation=generation, marks=checked['marks'],
                speculative_finished_before_cpu_verdict=before_verdict,
                stale_generation_rejected=stale_rejected, final_confirmed=final_ok,
                expected_tokens=int(expected_mask.sum()),
                checkpoint_bytes=sum(x.nbytes for x in snapshot),
                replayed_tokens=int(mask.sum()) if checked['marks'] else 0,
                cpu_check_seconds=checked['seconds']+final_check_seconds,
                checkpoint_copy_seconds=checkpoint_copy_seconds,
                correction_and_replay_seconds=correction_and_replay_seconds,
                wall_seconds=time.perf_counter()-started)


def admissible(result_generation, current_generation, cpu_confirmed):
    return result_generation == current_generation and cpu_confirmed
