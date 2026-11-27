"""Physical tensor storage by owner; controlled interface cost, no correctness labels."""

import gc
import sys
from collections import Counter
from dataclasses import fields, is_dataclass
from time import perf_counter

import numpy as np
import torch

from binding_packets import public_view
from first_parent import records
from foundation_completion import Completion, Decision
from foundation_diagnostics import Fixture
from head_joint_index import prepare, draw
from partner_index import noise
from partner_index_worlds import args, frozen
from selective_replication import AllocationTrace
from selective_trials import inputs
from shared_posting import SparseCompletion


def leaves(x):
    if isinstance(x, dict):
        return x.values()
    if isinstance(x, (list, tuple)):
        return x
    if is_dataclass(x):
        return [getattr(x, f.name) for f in fields(x)]
    return ()


def storage(x, seen):
    if torch.is_tensor(x):
        st = x.untyped_storage()
        k = st._cdata
        if k in seen:
            return 0
        seen.add(k)
        return st.nbytes()
    return sum(storage(v, seen) for v in leaves(x))


def host(x, seen):
    if id(x) in seen:
        return 0
    seen.add(id(x))
    if torch.is_tensor(x):
        return sys.getsizeof(x)
    vals = list(leaves(x))
    if isinstance(x, dict):
        vals += list(x.keys())
    return sys.getsizeof(x) + sum(host(v, seen) for v in vals)


def fixture(n, w, c, arity):
    m = Fixture(n, w, c)
    m.rows = {0: list(m.keys)}
    m.last = None
    if arity == 3:
        for r, rule in enumerate(m.prog["recipe"]["rules"]):
            m.roles[r] = (0,) * 3
            m.enc.cat.inputs["generated", r] = [r, r + 1, r + 1]
            rule["interface"]["rows"] = [
                {"columns": [{"slot": s} for s in slots]}
                for slots in ([0, 10, 11, 12], [0, 1, 13, 14], [1, 15, 16, 17])
            ]
    return m


def timed(fn):
    torch.mps.synchronize()
    start = perf_counter()
    val = fn()
    torch.mps.synchronize()
    return val, 1000 * (perf_counter() - start)


@torch.no_grad()
def run(a):
    mdl = frozen(a, a.seeds[0])
    out = []
    for n, w, c, k in (
        [(n, 4, 16, 2) for n in (32, 256, 1024, 4096)]
        + [(256, w, 16, 2) for w in (1, 8, 16)]
        + [(256, 4, c, 2) for c in (1, 64, 256)]
        + [(256, 4, 16, 3)]
    ):
        m = fixture(n, w, c, k)
        frame = dict(retired=[], updates=m.up)
        for arm in ("A", "B", "Bcompact", "C"):
            dec = SparseCompletion(mdl) if arm == "C" else Completion(mdl, "rule")
            if arm == "Bcompact":
                dec.mem.compact = True
            stats = Counter()
            if arm == "A":

                def build():
                    z = public_view(m, m.prog, key=(0, False))
                    data = inputs(z, False)
                    return z, data, prepare(mdl, data)
            else:

                def build():
                    dec.publish(m, m.prog, frame, stats)

            # Inspect allocations separately so tracing is outside the timed build.
            with AllocationTrace() as build_trace:
                probe = build()
            torch.mps.synchronize()
            high = build_trace.peak - build_trace.initial
            transient = max(
                0,
                build_trace.peak
                - max(build_trace.initial, torch.mps.current_allocated_memory()),
            )
            del probe
            if arm != "A":
                dec = SparseCompletion(mdl) if arm == "C" else Completion(mdl, "rule")
                if arm == "Bcompact":
                    dec.mem.compact = True
            result, build_ms = timed(build)
            if arm == "A":
                z, data, (root, edges) = result

                def read_rows():
                    return (
                        draw(
                            data, (root, edges), noise(np.random.default_rng(419), 8, k)
                        )
                        .cpu()
                        .tolist()
                    )

                feats = data[0][3]
                index = [e.index for e in edges]
                cache = [root, [(e.mass, e.start, e.count) for e in edges]]
                recipe = (data[1], data[0][:3])
                host_extra = z
            else:

                def read_rows():
                    rng = np.random.default_rng(419)
                    if arm == "C":
                        return dec.bind(0, 8, rng, stats)
                    return [
                        dec.finish(
                            Decision(dec.net, rng, stats), fixed_rule=0, stats=stats
                        )
                        for _ in range(8)
                    ]

                if arm == "C":
                    b = dec.mem.banks[0]
                    feats = (b.lo, b.frac, b.keys)
                    index = (b.offsets, b.starts, b.ends, b.owners)
                    cache = []
                    host_extra = (dec.mem.loc, b.refs, b.widths)
                else:
                    pages = list(dec.mem.pages.values())
                    feats = [(p.keys, p.fields) for p in pages] + [
                        (v[2], v[3]) for v in dec.mem.rows.values()
                    ]
                    index = [p.mean for p in pages]
                    host_extra = (
                        dec.mem.rows,
                        dec.mem.by_table,
                        dec.mem.segments,
                        [p.refs for p in pages],
                    )
                recipe = (dec.schemas, dec.rkeys, dec.ctx)
            timed(read_rows)
            with AllocationTrace() as trace:
                read_rows()
            torch.mps.synchronize()
            read_temp = trace.peak - trace.initial
            read_ms = [timed(read_rows)[1] for _ in range(3)]
            if arm.startswith("B"):
                cache = dec.coarse
            seen = set()
            sizes = {
                name: storage(v, seen)
                for name, v in (
                    ("feature_B", feats),
                    ("index_B", index),
                    ("cache_B", cache),
                    ("recipe_device_B", recipe),
                )
            }
            # Physical fixture's original public hashes and named rows on host, plus
            # its common upstream row embedding storage. Excludes process overhead.
            hseen = set()
            raw_host = host(m.pub.live, hseen)
            extra = host(host_extra, hseen)
            additional = 0
            if arm != "A":
                before = stats["fields_encoded"]
                dec.publish(m, m.prog, dict(updates=[], retired=[]), stats)
                assert before == stats["fields_encoded"]
                _, update_ms = timed(
                    lambda: dec.publish(
                        m, m.prog, dict(updates=m.up[:1], retired=[]), stats
                    )
                )
                additional = stats["fields_encoded"] - before
            else:
                # A materializes the selected edge anew in the actual sampling path.
                _, update_ms = timed(build)
            out.append(
                dict(
                    rows=n,
                    fields=w,
                    recipes=c,
                    arity=k,
                    arm=arm,
                    raw_host_B=raw_host,
                    publication_payload_B=n * 6 * 8 + n * w * 8,
                    common_upstream_graph_B=storage(m.vec, set()),
                    common_model_B=storage(mdl.state_dict(), set()),
                    build_device_highwater_delta_B=high,
                    build_transient_above_endpoints_B=transient,
                    common_host_key_B=storage(m.keys, set()),
                    index_and_view_host_B=extra,
                    recipe_ir_host_B=host(m.prog, set()),
                    recipe_static_host_B=0
                    if arm == "A"
                    else host((dec.wiring, dec.schedule), set()),
                    **sizes,
                    read_transient_observed_B=read_temp,
                    build_ms=build_ms,
                    read_ms=float(np.median(read_ms)),
                    update_1row_ms=update_ms,
                    changed_fields_encoded=additional if arm != "A" else "",
                    index_rebuild_on_read=arm == "A",
                )
            )
        records(a.out / "cost.csv", out)
        print(n, w, c, k, flush=True)
        gc.collect()


@torch.no_grad()
def dispatch(a):
    # Hold the posting algorithm and eight complete draws fixed while changing
    # only the number of launches. Ragged fixtures additionally stress row offsets.
    model=frozen(a,a.seeds[0])
    rows=[]
    for ragged in (False,True):
        m=fixture(1024,4,16,2)
        if ragged:
            for i,(_,r) in enumerate(m.up):
                r["hashes"]=r["hashes"][:i%5]
        dec=SparseCompletion(model)
        dec.publish(m,m.prog,dict(updates=m.up,retired=[]),Counter())
        for block in range(5):
            for batch in ((1,8) if block%2==0 else (8,1)):
                rng=np.random.default_rng(419+block)
                def sample():
                    return [dec.bind(0,batch,rng,Counter()) for _ in range(8//batch)]
                _,ms=timed(sample)
                rows.append(dict(rows=1024,fields=sum(len(r["hashes"]) for _,r in m.up),ragged=ragged,
                                 batch=batch,block=block,resident_feature_and_index_B=dec.mem.bytes(),eight_tokens_ms=ms))
    records(a.out/"dispatch.csv",rows)


if __name__ == "__main__":
    torch.set_num_threads(1)
    a=args()
    {"cost": run, "evaluate": dispatch}[a.task](a)
