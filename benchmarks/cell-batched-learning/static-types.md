# Shared layout type dispatch

The closure-storage audit found that static dispatch still depended on source
instance code. The compiler now intersects concrete operator identities for
every operation of each shared port layout. A table is known only if **every**
template using that layout agrees. Different constructors with identical wiring
remain ambiguous. This proof uses the complete compiled program, not observed
roots, values, or the subset of templates present in the training trace.

Both coordinator candidate enumeration and the borrowed constructor reader use
this table before looking up an instance's concrete code. Proven positions remove
that directory read; ambiguous positions retain it. Candidate liveness, visibility,
table identity and key/Eq checks remain authoritative. Shared shape IDs and catalog
formats do not change. No per-instance flags, bindings, or consumer lists are added.

| case | static type guards / all candidate type guards | Program array bytes |
|---|---:|---:|
| fact | 19002 / 20125 | 21592 |
| loopfact | 14027 / 14916 | 21184 |
| sum-bits | 146712 / 155670 | 21976 |
| dot-product | 81523 / 87162 | 23432 |

These are executed work counts in the actual standalone Cell runtime. A static
guard replaces one instance-directory read for operator dispatch, not a constructor
lookup or a live fact read. There is an additional shared array access and branch,
including on ambiguous sites. No timing benefit is claimed. All final Graph heap
fields and fact lifecycle snapshots equal the atomic-completion seed; the extra
array belongs to retained Program storage. The directory is not yet removed.

## Correction to the directory-removal prerequisite

Static type information is not the only reason a dead source has a directory
entry. `Graph::native_port` also decodes `(source Cell, slot)` from an Eq identity
and uses the composition directory to find its current component and symbolic port.
That identity can remain a live root after its original source facts disappear.
Removing the directory based only on source retirement can lose union dispatch.
The next storage replacement must preserve this address mapping as well as external
Entry reads; introducing a second alias directory would need to be charged against
the removed storage. Do not claim that compiling operator types alone licenses GC.

Validation: 53 ownership tests pass, including explicit ambiguity between same-layout
constructors, existing unions/deletions/cross-stage reads and worker configurations.
The default runtime compiles. Memory comparison reuses unchanged source/catalogs.

Reproduce with `runtime_storage_peak PROGRAM OUTPUT inherited-owners
--port-domains-only`, saving `candidate-static-types-heap.json` for each case, then:

```
python3 benchmarks/cell-batched-learning/static_type_results.py out/cell-batched-learning benchmarks/cell-batched-learning/static-type-results.json
```

The rebuilt batch checker passes all 2,652 saved source Run checks and all four
terminal checks against the stage-inherited seed selection. Marked sum-bits retains
2,222,254 Graph bytes and the reviewed final-state digest; saved-export choice
 diagnosis passes with exit 0 after that actual execution digest check.
