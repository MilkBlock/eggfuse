"""Compare an issued three-step token with its pair prefix on the same trajectory."""
import argparse
import ctypes
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

import numpy as np
import torch

from capture import execute, inputs, load_catalog, read, verify
from compound_model import compiled_actions


# The diagnostic invokes only independent grid lanes or single-lane kernels.
# A threadgroup kernel cannot be serialized using this adapter.
GRID_KERNELS = set("inject seed_keys seed_index next_run neural_snapshot_anchors neural_features neural_propose "
                   "compound_child neural_verify compound_resume search commit export_rows "
                   "frozen_compound_wave".split())
CPU_HEADER = """#include <algorithm>
#include <cmath>
#include <cstdint>
#include <climits>
#include <cstdlib>
using namespace std;
namespace metal {}
using uint=unsigned; using ulong=unsigned long;
#define device
#define constant const
#define thread
#define kernel
#define atomic_int int
#define memory_order_relaxed 0
#define atomic_fetch_add_explicit(p,v,o) __atomic_fetch_add(p,v,__ATOMIC_RELAXED)
#define atomic_store_explicit(p,v,o) __atomic_store_n(p,v,__ATOMIC_RELAXED)
#define atomic_load_explicit(p,o) __atomic_load_n(p,__ATOMIC_RELAXED)
#define atomic_compare_exchange_weak_explicit(p,e,v,a,b) __atomic_compare_exchange_n(p,e,v,false,__ATOMIC_RELAXED,__ATOMIC_RELAXED)
#define ctz __builtin_ctzll
#define popcount __builtin_popcountll
#define threadgroup_barrier(x) ((void)0)
"""


def serial_compiler(directory):
    def compile_shader(source):
        wrappers = []
        for name, signature in re.findall(r"kernel void (\w+)\(([^)]*)\)", source, re.S):
            if name not in GRID_KERNELS:
                continue
            if name=="neural_snapshot_anchors" and "#define NEURAL_EDGES 1\n" not in source:
                continue
            args = signature.split(",")
            if "thread_position_in_grid" not in args[-1]:
                raise ValueError(f"unsupported dispatch for {name}")
            casts = []
            for i, arg in enumerate(args[:-1]):
                if "*" in arg:
                    typ = arg[:arg.index("*")+1].replace("device", "").strip()
                    casts.append(f"({typ})p[{i}]")
                elif "constant int &" in arg:
                    casts.append(f"int((intptr_t)p[{i}])")
                else:
                    raise ValueError(f"unsupported kernel argument {arg}")
            call = ", ".join([*casts, "i"])
            wrappers.append(f'extern "C" void wrap_{name}(void** p,int n) '
                            f'{{for(unsigned i=0;i<n;++i){name}({call});}}')
        src = directory / "grid.cpp"
        lib = directory / "grid.dylib"
        src.write_text(CPU_HEADER + source.replace("#include <metal_stdlib>", "") +
                       "\n" + "\n".join(wrappers))
        subprocess.run(["clang++", "-std=c++17", "-Wno-unknown-attributes", "-O2",
                        "-dynamiclib", str(src), "-o", str(lib)], check=True)
        library = ctypes.CDLL(str(lib))

        class Dispatch:
            def __getattr__(self, name):
                if name not in GRID_KERNELS:
                    raise ValueError(f"unsupported serial kernel {name}")
                kernel = getattr(library, "wrap_" + name)
                kernel.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_int]
                kernel.restype = None

                def dispatch(*args, threads, arg_casts=None):
                    pointers = (ctypes.c_void_p * len(args))(*[
                        a.data_ptr() if isinstance(a, torch.Tensor) else a for a in args])
                    kernel(pointers, threads)
                return dispatch
        return Dispatch()
    return compile_shader


def check(args):
    image, program, gold = inputs(args.corpus, args.ref, args.case)
    donor = args.ref / "sum-bits/program.json"
    policy = read(args.checkpoint)
    joins, tails, wires = compiled_actions(read(donor), policy["three_step"])
    if [list(j) for j in joins] != policy["joins"] or tails != policy["tails"] or wires != policy["wires"]:
        raise ValueError("policy differs from compiled donor")
    cfg = dict(catalog=load_catalog(image, program, donor), rows=2, hidden=8, ranks=8,
               waves=2, weights=policy["roots"], compound=dict(named_boundary=policy.get("named_boundary",False),joins=joins,tails=tails,
               wires=wires,batch=True,child=policy["child"]))
    args.out.mkdir(parents=True, exist_ok=False)
    def run(arm):
        dest = args.out / arm
        with TemporaryDirectory() as tmp:
            execute(image/"device.json", args.reader, args.ref/"ports-1703.pt", 2048, 2, dest,
                    neural=cfg, count_work=True,
                    serial_compile=serial_compiler(Path(tmp)) if args.serial_cpu else None)
        verify(dest, gold, image)
        return dest
    full = run("full")
    with np.load(full/"compound-output.npz") as z, np.load(full/"neural-output.npz") as n:
        claims, terminal = z["claims"], z["tails"]
        winners = terminal[:,:,7]
        if not np.any(winners):
            raise ValueError("no third RHS committed from a generated token")
        t, lane = np.argwhere(winners>0)[0]
        raw = n["raw"].copy()
        action = claims[t,lane,1]
        assert raw[t,2+lane,10] == wires[action]+1 and tails[action]>=0
        assert terminal[t,lane,2] == claims[t,lane,7] > 0
        prefix_index=next(i for i,j in enumerate(joins) if j[1:]==joins[action][1:] and tails[i]<0)
        raw[t,2+lane,10] = wires[prefix_index]+1
        later={k:z[k][:,:,7].copy() for k in z if k.startswith("hop_")}
    cfg["compound"]["replay"] = raw
    prefix = run("prefix")
    with np.load(prefix/"compound-output.npz") as z:
        expected = winners.copy()
        expected[t,lane] = 0
        np.testing.assert_array_equal(z["tails"][:,:,7], expected)
        np.testing.assert_array_equal(z["claims"][:,:,7], claims[:,:,7])
        removed=1
        for key,after in later.items():
            removed+=int(after[t,lane]>0)
            after[t,lane]=0
            np.testing.assert_array_equal(z[key][:,:,7],after)
    with np.load(prefix/"neural-output.npz") as p, np.load(full/"neural-output.npz") as f:
        np.testing.assert_array_equal(p["raw"], raw)
        np.testing.assert_array_equal(p["rhs_ordinal"], f["rhs_ordinal"])
    roles = [read(path/"run.json")["execution_roles"] for path in (full,prefix)]
    residual = [r["rhs_inputs_from_exact_search"] for r in roles]
    assert residual[1] == residual[0]+removed
    # Each arm contains only evidence available before the consumer Run.
    # Keep oracle attribution in a separate target, outside observation.
    examples=[]
    with np.load(full/"neural-output.npz") as f, np.load(full/"output.npz") as graph:
        terminal_ordinal=int(winners[t,lane])
        target_rhs=graph["rhs"][terminal_ordinal-1]
        decision_run=int(target_rhs[0])
        assert t+1 < claims[t,lane,5] < decision_run
        sibling_ordinals=(np.flatnonzero(graph["rhs"][:,0]==decision_run)+1).tolist()
        sibling_ordinals.remove(terminal_ordinal)
        for name,stream,owed in (("full",f["raw"],False),("prefix",raw,True)):
            observation=dict(issue_run=int(t+1), issued_rows=stream[t,:,8:].tolist(),
                             middle_run=int(claims[t,lane,5]),middle_winner=int(claims[t,lane,7]),
                             candidate=dict(rule=int(target_rhs[1]),row=int(terminal[t,lane,3])))
            examples.append(dict(arm=name,observation=observation,decision_run=decision_run,
                                 label=dict(requires_independent_route=owed,ordinal=terminal_ordinal,
                                            preserved_sibling_ordinals=sibling_ordinals)))
    (args.out/"decision-pair.json").write_text(json.dumps(examples,indent=2)+"\n")
    report = dict(case=args.case, backend="serial CPU" if args.serial_cpu else "Metal",
                  runs=len(claims), baked_unit=int(joins[action][0]), issue_run=int(t+1),
                  root_middle_terminal=[int(claims[t,lane,2]),int(claims[t,lane,7]),int(winners[t,lane])],
                  root_rhs=roles[0]["root_rhs"], middle_rhs=int((claims[:,:,7]>0).sum()),
                  terminal_rhs=int((winners>0).sum()), residual_rhs_full_prefix=residual)
    (args.out/"comparison.json").write_text(json.dumps(report,indent=2)+"\n")
    print(report)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("corpus","ref","reader","checkpoint","out"):
        p.add_argument(key,type=Path)
    p.add_argument("--case",default="sum-bits")
    p.add_argument("--serial-cpu",action="store_true")
    torch.set_num_threads(1)
    check(p.parse_args())
