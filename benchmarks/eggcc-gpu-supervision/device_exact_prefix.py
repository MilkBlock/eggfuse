"""Exact bounded Entry prefix selection on device.

The compiler supplies equal-slot constraints. Pools must already encode table,
visibility and type admission. Scalar guards remain downstream obligations.
Overflow blocks completeness, including overflow at intermediate depths.
"""


def expand_exact(pools, required, atoms, ports, capacity, xp):
    if capacity < 1 or not 0 < len(pools) <= atoms:
        raise ValueError("invalid prefix capacity/depth")
    if required.shape != (atoms * ports, atoms * ports):
        raise ValueError("invalid compiler equality plan")
    required = required.reshape(atoms, ports, atoms, ports) != 0
    previous = xp.full((capacity, atoms, ports), -1, xp.int32)
    entries = xp.full((capacity, atoms, 2), -1, xp.int32)
    live = xp.arange(capacity) == 0
    overflow = xp.array(False)
    evaluated = xp.array(0, xp.int32)
    rejected = xp.array(0, xp.int32)
    scheduled = 0
    for depth, pool in enumerate(pools):
        roots = pool["roots"]
        count = len(roots)
        if count < 1 or roots.shape[1] != ports:
            raise ValueError("pools require padded rows with the compiled width")
        eligible = live[:, None] & pool["live"][None, :]
        # Repeated variables within this atom, including live-field validity.
        same = (roots[:, :, None] == roots[:, None, :]) & (roots[:, :, None] >= 0)
        within = xp.all(~required[depth, :, depth, :] | same, axis=(1, 2))
        # Only prior atoms are available at this prefix depth.
        linked = (previous[:, None, :, :, None] == roots[None, :, None, None, :])
        linked = linked & (roots[None, :, None, None, :] >= 0)
        needed = required[:, :, depth, :] & (xp.arange(atoms)[:, None, None] < depth)
        compatible = xp.all(~needed[None, None, :, :, :] | linked, axis=(2, 3, 4))
        chosen = eligible & within[None, :] & compatible
        evaluated = evaluated + xp.sum(eligible.astype(xp.int32))
        rejected = rejected + xp.sum((eligible & ~chosen).astype(xp.int32))
        scheduled += capacity * count
        overflow = overflow | (xp.sum(chosen.astype(xp.int32)) > capacity)
        order = xp.sort(xp.where(chosen.reshape(-1), xp.arange(capacity * count), capacity * count))[:capacity]
        live = order < capacity * count
        safe = xp.clip(order, 0, capacity * count - 1)
        parent, child = safe // count, safe % count
        slot = xp.arange(atoms) == depth
        previous = xp.where(slot[None, :, None], roots[child, None, :], previous[parent])
        entries = xp.where(slot[None, :, None], pool["entries"][child, None, :], entries[parent])
    return dict(entries=entries, live=live, complete=~overflow, overflow=overflow,
                active_choices=evaluated, rejected_choices=rejected,
                scheduled_choices=xp.array(scheduled, xp.int32))
