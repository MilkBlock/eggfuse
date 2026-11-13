# Device-generated constructor results in Cell slots

This adds genuine allocation/reuse of exact constructor-result identities to the
bounded GPU prototype. Previously the effect path could only reuse already
present values. `device_constructor_results.py` now resolves existing witnesses,
shares a new identity across same-key candidates, and writes returned identities
into the requesting Cell's existing result slots. No persistent per-node object,
consumer list, hash table or second fact graph is created by this primitive.

## Exact result operation

The caller supplies ephemeral constructor keys projected from template fields,
and a live witness view from the same frozen Eq snapshot. Keys include table
identity and exact argument identities; float token similarity is not a key.
Existing result identity and current result root are separate: two forwarded
identities with the same current root may be reused; unequal current roots for
one constructor key leave a conflict mark. No arbitrary winner is committed in
that case, and no union is silently executed.

New same-key candidates share one allocation from a reserved global identity
range. Allocation limits and per-call quota are checked on device; rejected
candidates retain pending work. An overlapping visible identity namespace is
rejected. The caller must additionally reserve above identities outside the
supplied witness view. Integer-overflow avoidance is tested at the signed int32
upper bound. Dead/inactive lanes cannot claim a result. No stable identity is
encoded by rounding a learned float vector.

`execute_site` batches a compiled constructor operation across Cell instances.
It checks the template and source effect position, argument availability, activity
and visibility. Successful results fill destination slots and advance effect
position; only the last source effect can settle the Cell. The token commit path
initializes the effect position when admitting a new instance. Static site order
is unrolled into a GPU graph, not selected using intermediate CPU readbacks.
This is not a general new scheduler or a proof of effect independence.

## Integrated GPU test

A compiler-built source Cell matching `Input(a)` executes `F(a)` and `G(F(a))`.
Starting with identity 7 and reserved IDs at 100, GPU fills its slots with
`[7,100,101]`, then the actual lowered successor query consumes these results and
creates a consumer key `[consumer,100,101]`. The source effects, query projection,
float successor transform, and admission all execute inside one compiled call.
Only the final audit reads CPU values. The initial source match is a fixture,
not autonomous Eggcc bootstrap or full-program semantic acceptance.

Other tests cover competing candidates sharing fresh IDs, foreign existing
results, root conflicts versus forwarded aliases, capacity, namespace overlap,
int32 bounds, masked witnesses, and repeated ordered fragments. The float token
transform remains a test matrix; the learned ridge adapter is not yet integrated
into this constructor execution. This exact witness machinery is distinct from
the high-throughput learned Cell state computation requested by the overall goal.

33 related tests pass, including Metal execution. No speedup is claimed.

## Recipe lowering

`compile_constructor_sites.py` compiles actual recipe constructor positions and
preserves source effect order. Other operations and literal arguments remain
explicit boundaries. For dot-product's 548 rules:

- 901 constructor sites have slot-only arguments and can be lowered.
- 143 lie in an initially reachable constructor prefix across 79 rules.
- 72 rules have an entirely constructor-only, slot-argument RHS.

These are structural counts. They do not establish those rules' runtime match
coverage, existing witness availability, valid scalar encodings or legal Run
execution. Sites after unsupported operations cannot execute early: effect_pc
prevents bypassing those obligations. The report records exact source provenance.

## Remaining costs and obligations

The resolver uses candidate x witness and candidate x candidate exact comparisons.
It is a bounded correctness implementation, not the desired efficient large-Eggcc
GPU architecture. Witness preparation/projection costs are not eliminated or timed.
The integration fixture has no live F/G witness, so its masked empty view is
complete for that fixture; passing an incomplete view for real graphs could create
incorrect duplicates. A real compiler/runtime adapter must provide the full
relevant visible view or a proof that a restricted view is complete.

The new IDs are stored in Cell slots, but existing-witness views are not yet
maintained automatically across arbitrary runtime updates. Roots must be current;
pending union, mutable/scalar effects, constructor forwarding, deletion and reused
generations remain outside this resolver. Any missing prerequisite blocks semantic
commit/closure. New local result identities do not prove a stage is saturated.
Shared-result liveness must eventually move with authoritative owners, not with
whichever candidate happened to allocate first. All compiled real ownership
transfer flags remain conservative.

Reference branch now ends at `e014272b`. Its successful repeated-variable anchor
can provide conditional port equality premises, following Copy aliases while
rejecting overwritten bindings. Those premises are valid for that matched anchor,
not global template aliases. This is relevant to reducing future witness key
checks; current GPU exact comparisons do not yet exploit that proof expansion.
No native code was merged.

Reproduce with the NumPy/MLX environment:

```
PYTHONPATH=benchmarks/eggcc-gpu-supervision $PYTHON -m unittest \
  test_device_constructor_results test_context_effect_projection \
  test_device_alias_completion test_lower_device_entries test_device_token_commit \
  test_continuation_contract test_cell_token_successors
$PYTHON benchmarks/eggcc-gpu-supervision/compile_constructor_sites.py TRACE OUTPUT.json
```

Next integrate complete witness views from the same Cell storage and compile
larger effect fragments, followed by union/scalar/mutable obligations and the
original Run controller. Full multi-source matching, ownership transfer and
GPU-driven cross-stage fixed points remain unfinished.
