# Prepared workers read the compiled Cell witness catalog

The last catalog execution at `aef89181` extended worker prefixes but bypassed
the ownership witness routes used by source RHS execution. On the unchanged
learned sum-bits artifact this raised generic lookups from 14,506 to 14,962 and
allocated additional result buffers. Ordinary inputs have no such catalog and
cannot establish coverage of this path. Another catalog-learning pass cannot
remove this execution-interface gap.

The worker's existing Run read view now borrows the authoritative composition
frames/components, static route groups and actual fact lifecycles. A Cell's
matched query witnesses select the same compiled `(shape, source position, code,
operation)` routes as source execution. A stack-local group selection can serve
several prefix operations within that instance. It never crosses a read view or
Graph, owns no values, and maintains no producer/consumer dependencies.

When the existing compiler proves a key from matched query ports, copies and
repeated-variable equalities, the worker reads the actual result without
constructing that key or probing the global index. Other candidates compare
their actual fields against one lazily constructed key; a fallback reuses that
same key. An uncovered route still performs the ordinary constructor query.
Rules with no witness catalog go directly to their original key/query path.

Both canonical decoded fields and stable-port projections are supported. The
reader checks current ownership, visibility, forwarding, component identity,
code and operator. It is borrowed only from the existing settled source-Run
view. Static key proof does not authorize a dead or hidden fact. The result
continues through the existing `Found` or shared prefix-result layout; no
`KeyEvidence::Compared` object crosses a mutation boundary. Source admission
still checks the original union generation, table readiness and lifecycle,
preserving the original Run/effect/error boundaries and residual execution.

The removed work is actual key/index lookup within accepted coverage, not a new
catalog, counter or repeated preliminary search followed by the same query.
The added route probes, candidate checks and lifecycle reads are charged in
constructor preparation v9. Key construction, canonical field/result reads and
stable-port work retain their existing counters. Hits, proved hits and selection
reuse are outcomes and receive no duplicate savings credit. The read view,
compiled rule selector and worker aggregate counters add fixed metadata; the
instance's binding/result payload is unchanged. Timing includes these costs.

Short tests cover one/four workers and canonical/stable storage. With proven
keys plus an explicitly unproved local hint, generic lookups fall 578→434.
Changing the computed key causes 46 hints to fail exact comparison and falls
back correctly (578→481 lookups). Exact exports, ordered bindings, Run snapshots,
constructor requests and fact creation agree with the no-witness control.
Existing hide/delete/union tests now also execute through worker preparation.
The deliberately offered hint is test coverage of rejection, not observed
production proof or permission to skip its comparison.

Job 293 passes 132 integration tests, six work-credit tests, 215 runtime tests
and no-default compilation. Job 294 checks the subsequent catalog-free fast
path with 97 integration tests and all 215 runtime tests. Workload measurements
are recorded below after freezing the candidate. These are actual standalone Cell CPU executions, not native egglog
runtime speed measurements. The baseline is the previous candidate `aef89181`;
its executable is reused only after checking commit, binary and input identity.

```sh
eggfuse-job run --kind compute -- python3 benchmarks/cell-bake-owner-merge/owner_workers.py ACCEPTED TARGET CONTROL_CHECKOUT OUTPUT --learned-program SAVED_CATALOG --reuse-candidate PRIOR_ARTIFACTS
eggfuse-job run --kind timing -- python3 benchmarks/cell-bake-owner-merge/prepared_timing.py OUTPUT SAVED_CATALOG OUTPUT/timing --include-ordinary
```

One timing job completes all control sum-bits/Raytrace/learned groups before any
candidate group. Five, three and seven samples respectively, each with one
warmup. The reviewed native contract applies only to ordinary sum-bits; the
unchanged learned catalog and Raytrace use their stated differential checks.
