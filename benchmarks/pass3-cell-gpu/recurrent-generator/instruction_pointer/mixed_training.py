"""Issue-level supervision from randomized and M0 native snapshots, without storing a graph per Run."""
import random
from dataclasses import replace

from history import stream


def groups(targets, lanes, rng):
    if len(targets)<=lanes:
        yield targets
        return
    order=list(targets)
    rng.shuffle(order)
    for i in range(0,len(order),lanes):
        group=order[i:i+lanes]
        # More legal requests exist on this snapshot. A short tail must not
        # teach a lane to Stop. Use distinct legal peers already in this epoch.
        group+=rng.sample(order[:i],lanes-len(group))
        yield group


def batches(root,manifest,lanes,seed):
    rng=random.Random(seed)
    records=[r for r in manifest if r['split']=='train']
    synthetic=[r for r in records if r['origin']=='random']
    native=[r for r in records if r['origin']=='eggcc']
    if not native or not synthetic:
        raise ValueError('mixed training needs native and synthetic training programs')
    def source(cases):
        for r in cases:
            for cat,frame in stream(root/r['directory'],rng.getrandbits(62)):
                for batch in groups(frame.targets,lanes,rng):
                    yield r,cat,replace(frame,targets=batch),len(frame.targets)
    while True:
        rng.shuffle(synthetic)
        streams=[source(synthetic),*(source([r]) for r in native)]
        # Interleave actual programs. Exhaust every Run and every labeled tuple
        # once or more before opening another epoch or renaming the handles.
        while streams:
            for it in list(streams):
                item=next(it,None)
                if item is None:
                    streams.remove(it)
                else:
                    yield item
