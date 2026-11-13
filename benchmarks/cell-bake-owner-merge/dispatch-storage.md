# Full heap cost of grouped witness dispatch

This compares frozen standalone Cell CPU runtimes on the same four `prefix-all`
artifacts, using `inherited-owners --port-domains-only`. Control is `15fc6d39`;
candidate is `4205ca2e`, including the immutable groups from `a5d19f35`.
The JSON records full commit and executable digests.

| case | old witness table | growing groups (rejected layout) | frozen groups | final delta |
| --- | ---: | ---: | ---: | ---: |
| fact | 89,168 | 112,656 | 87,416 | -1,752 |
| loopfact | 86,448 | 112,400 | 88,160 | +1,712 |
| sum-bits | 210,240 | 282,512 | 201,352 | -8,888 |
| dot-product | 192,096 | 266,200 | 187,560 | -4,536 |

Graph-owned heap is unchanged: 658,935 / 585,105 / 1,773,131 / 1,720,731 bytes.
The only changed retained Program field is `ownership.witnesses`. Total retained
Program is about 158–162 MB; that runtime footprint must not be omitted merely
because its data was prepared at compile time. Execution peak changes by the
Program delta plus two bytes; this is process requested heap including Program,
Executor and diagnostic buffers, not Graph-exclusive peak or RSS. Stack size and
allocator metadata are outside the accounting.

The memory run checks program identity, final state, Run count and witness
search/acceptance/reuse counts against the saved reports whose 2,652 Run checks
and four terminal checks passed. It does not rerun native semantic acceptance
or independently compare every intermediate state. All 59 ownership integration
tests passed for the frozen-group source change. No timing claim is made.

## Why the first measurement was invalid

A shared Cargo target reused local runtime artifacts across worktrees. Different
example executable hashes were insufficient to prove different linked runtimes:
the supposed candidate lacked the new dispatch counters. Those outputs were
quarantined under `out/cell-dispatch-storage-invalid-shared-target` and are not
used here. Each lane now cleans the three local workspace packages, rebuilds,
freezes its executable, checks counter presence and compares actual work with
the audited implementation. Tracked engine/compiler source must remain clean
against the recorded commit before and after building. Dependencies remain cached.

The corrected growing-group run showed increased retained tables; freezing each
immutable operation vector removes its spare capacity and reduces group headers.
The control-to-final comparison retains the saved dispatch reductions, while
charging the remaining small loopfact regression. This closes the memory audit
of dispatch grouping; it does not achieve structural egraph compression.

## Reproduce

```sh
~/.local/bin/eggfuse-job run --kind compute -- python3 benchmarks/cell-bake-owner-merge/dispatch_storage.py /private/tmp/cell-dispatch-storage-15fc out/cell-bake-owner-merge/batch out/cell-dispatch-storage benchmarks/cell-bake-owner-merge/dispatch-storage.json
python3 benchmarks/cell-bake-owner-merge/dispatch_storage.py --collect-only out/cell-dispatch-storage benchmarks/cell-bake-owner-merge/dispatch-storage.json
```

The next structural unit remains template-owned fact membership and actual-result
projection across Runs. Completed arrays already share storage, but source fact
identities, composition addresses and constructor indexes remain live. Any
replacement must remove these existing per-application records within proven
coverage, preserve foreign returned results and boundary readers, and restore
only the affected source after unexpected union or retirement. Another directory
fusion or table capacity reduction cannot be counted as that takeover.
