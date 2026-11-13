"""Device-controlled completion stages for a bounded, stable-slot Cell family.

Each stage emits its complete proposal into compiler-assigned slots. This
protocol is valid only for immutable slot values; general Eq/update deltas need
their own compiled merge. No numerical convergence test establishes saturation.
"""
import mlx.core as mx


def complete(proposed, eligible, readout, bias, *, ticks=6, suppress=False):
    state = mx.zeros_like(proposed)
    live = mx.zeros_like(eligible)
    result = mx.zeros((*eligible.shape, readout.shape[-1]), dtype=proposed.dtype)
    exported = mx.zeros_like(eligible)
    stage = mx.array(0, dtype=mx.int32)
    transitions = []
    for _ in range(ticks):
        # Both expressions have static wiring. Device masks select the stage;
        # no host reads of stage, counts or intermediate tokens occur here.
        offered = eligible
        if suppress:  # fault injection: silently omit every entrance's last slot
            last = mx.sum(eligible, axis=-1, keepdims=True) - 1
            offered = offered & (mx.arange(eligible.shape[-1])[None, :] != last)
        fresh = (stage == 0) & offered & ~live
        state = mx.where(fresh[..., None], proposed, state)
        live = live | fresh
        outgoing = (stage == 1) & live & ~exported
        result = mx.where(outgoing[..., None], state @ readout + bias, result)
        exported = exported | outgoing
        changed = mx.any(fresh) | mx.any(outgoing)
        stage = mx.where((stage < 2) & ~changed, stage + 1, stage)
        transitions.append(mx.stack([stage, mx.sum(fresh), mx.sum(outgoing)]))
    # Exhaustion is distinct from quiescence. Neither means CPU-confirmed.
    return result, exported, stage, mx.stack(transitions), stage < 2
