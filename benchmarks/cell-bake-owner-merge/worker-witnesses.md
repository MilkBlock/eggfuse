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

## Workload result: performance gate failed

The implementation is `b8a113c8`. Job 297 freezes it and validates exact final
exports, source Run summaries and logical effects for ordinary sum-bits (1,428
Runs), Raytrace (16,883) and the unchanged learned catalog (882). Native sum-bits
choice diagnosis passes and binds to the fresh ordinary export. Neither the
learned workload nor Raytrace gains a new native acceptance claim.

On the learned catalog, generic lookups fall **14,962→14,404**, exactly the 558
accepted worker witnesses. Prefix work, buffer moves/capacity and 1,099 baked
composition hits are unchanged. Only 35 accepted witnesses have static key
proofs; key construction decreases only 13,005→12,988 fields. Additional work:

| worker witness work | count |
|---|---:|
| operation attempts | 5,162 |
| anchor reads | 5,029 |
| route-map probes | 4,676 |
| selection reuse | 353 |
| selected-group operation checks | 1,411 |
| target candidates | 1,335 |
| lifecycle checks | 1,370 |
| accepted witnesses | 558 |

All 5,029 anchor reads reach a map probe or selection reuse. Only 1,411 obtain
a group; the other 3,618 signatures are absent from the current compiled route
map. This does not identify which key dimension (shape, source position, code
or operation) caused each miss, nor prove that they are all future-stage shapes.
The absent group and candidate checks are new paid work, not savings.

Ordinary sum-bits and Raytrace execute zero new witness attempts. Their generic
lookups remain 14,653 and 4,332,972 and the recorded preparation/buffer/ownership
counters are unchanged. Those workloads therefore diagnose common execution
overhead; they cannot establish witness-route coverage.

Job 298 completes all three control groups before any candidate group. All 84
process-boundary guards are clear. Short grouped inference medians:

| workload | previous candidate `aef89181` | experiment `b8a113c8` | change |
|---|---:|---:|---:|
| ordinary sum-bits | 21.056 ms | 24.101 ms | +14.47% |
| Raytrace | 4.753641 s | 4.855154 s | +2.14% |
| learned sum-bits | 20.908 ms | 21.414 ms | +2.42% |

**This is not an accepted speedup.** The implementation and measurements stay
on the experimental branch; the performance baseline remains `aef89181`.
Sample values and provenance are retained in `worker-witness-results.json`.
The ordinary regression cannot be attributed to failed witness probes because
those inputs execute none. Common preparation changes and grouped-run drift
remain separate possibilities; no causal profiling result is claimed.

The next work is to select applicable continuation code at the Cell/Entry
boundary rather than retry its route map at each constructor, and to retain the
catalog-free preparation path without unnecessary common dispatch. Expanding
this catalog or counting the 558 successes again would not discharge either
cost. Large parallel speedup and saturated-Cell replacement remain unfinished.

## Next experiment: reuse selection across a worker chunk

The prior actual learned execution paid 4,676 route-map probes for 558 accepted
witnesses. Relearning that catalog cannot remove repeated lookup of an identical
compiled `(rule, Entry, shape, position, code, operation)` selection. Adjacent
instances in the existing worker chunk may reuse that selection, including an
absent route. This eliminates only the repeated static map search. It does not
cache a returned value or a component address; each instance resolves its own
anchor/component and validates the actual target as before. Exact comparisons,
forwarding/liveness checks and source union-generation admission remain live.

Selection scratch is now created at chunk entry and destroyed with that chunk,
including on error. Point queries, owned Entry ranges, residual expansions and
already matched groups all use the same rule. No selection survives in a
thread-local frame across Runs or programs. Memory is a single inline selection
per active chunk, with no heap allocation, new Instance field or dependency list.
The prefix also chooses its catalog/ordinary variant once before execution;
the ordinary variant has no per-operation witness branch or lazy-key cache.
These changes do not extend the saturation proof or alter Run visibility.

The prior performance gate failed, so fewer probes alone will not establish
acceptance. Validation must retain actual hits, final exports, source ordering
and native ordinary sum-bits acceptance, then measure complete sequential lanes
against both the failed experiment and the prior performance baseline. Results
are pending; broad saturated Cell completion and parallel ownership are still
unfinished.

Job 310 passes 113 compiler integration tests, 215 runtime unit tests and the
no-default runtime compile. The witness fixture now compares grains 1 and 16,
one/four workers and both canonical/stable storage. With the changed-key hint,
route probes fall 48→3 while the 97 actual witness hits and 481 generic lookups
are unchanged. Exact Run snapshots, ordered bindings and exports agree with the
ordinary-query control. This tests template sharing across distinct instances,
including targets which must fail exact key comparison. It is not workload
speed evidence.
