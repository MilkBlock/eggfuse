# Complete consumer effects from a settled producer Cell

This extends the actual compiler-to-GPU entry path. The prior isolated consumer
proof covered zero complete RHSs in dot-product. `compile_context` now uses the
producer's completed template facts and the verified consumer input mapping.
Constructor reuse is found in that shared static context, without a dynamic
query or per-instance consumer list. No execution trace selects the proof.

The compiler symbolically processes consumer effects in order. An existing
constructor maps to its source symbol; copies preserve that mapping; union is
discharged only when source completion already proves both symbols identical.
New construction, new equality and mutable/scalar effects remain boundaries.
Final consumer symbols map to actual source input or returned-result slots.
Source slots overwritten after their original definition are rejected. Literal
slot writes remain unsupported. Query and result slot sorts must agree.

The optional `--context-completion` lowering adds these static projections to the
same device entry plan. GPU checks availability of **all** required completion
slots, not just query inputs. It fills final consumer slots directly from source
values and marks the consumer settled only for a fully covered proof. A missing
result produces a `missing_witness` mark and blocks the candidate. Unsupported
consumers continue to enter as unsettled work, with no partial RHS side effects.

The floating successor transform still executes on GPU. It is not the proof that
these effects are complete. Exact projected slots carry the actual witnesses;
the float state remains the numerical model's state. The test uses a fixed
matrix, not an integrated newly trained ridge completion adapter.

## Recipe-level results

On the unchanged dot-product recipe, 157 same-ruleset, source-slot entries are
lowered. Of these, **two** now have fully covered effects; 155 remain pending:
91 need new constructors or witnesses outside this producer, 64 hit mutable set.
These are static entry counts, not observed matching frequency or runtime speed.

- Source template 139 to consumer 145 (`always-run`) reuses three constructor
  results (`Get`, `Single`, `SubTuple`), including an equality established by the
  source's completion. Current values come from actual slots, not operation IDs.
- Template 413 to 413 (`mem-simple`) completes a `NoAlias` symmetry continuation
  through an existing source result and query witness.

Template numbers are local to this exact recipe, whose hash is in
`device-context-lowering-results.json`. This does not authorize source Run
crossing, whole-stage closure, or ownership transfer. Transfer coverage stays
false: even redundant consumer effects do not prove that all future source
responsibilities move into the consumer.

## GPU evidence and limits

The integration fixture has a producer witnessing `G(a)` and constructing
`F(G(a))`. Its consumer query only sees `G(a)` and cannot prove its own `F` RHS
redundant. With the producer context, the compiler projects the actual `F` result
into the consumer, and GPU creates a settled token with that value. Removing the
source result slot prevents admission. Tests also reject a new union and a source
result slot overwritten later in the source program. No intermediate GPU result
is read by CPU in the compiled entry/commit call.

26 related tests pass. The real recipe coverage is compiled only; no real Eggcc
multi-stage GPU execution or semantic acceptance is claimed. Source input and
witness liveness still require the runtime's frozen snapshot/visibility contract;
slot presence alone cannot replace forwarding or retirement checks. The global
396-slot padding, retained keys, masks and pairwise dedup costs remain unchanged.
A source slot cannot be reclaimed while a live reader still depends on it.

## Reference branch update

Reference branch now ends at `f6b66cde`, following `b3322f9f`. The new native fix
clears retired source payloads in a shared owner while preserving live sibling
ranges and addresses; only the last source releases the backing arrays. For GPU
ownership, distinguish retiring a logical source, releasing its payload, and
reclaiming the shared allocation. Clearing an active bit is none of those proofs
by itself. No native branch code was merged here.

## Next execution work

Context reuse is now wired rather than merely counted, but the 155 pending
entries establish that it cannot replace general result generation. Next compile
new constructor fragments as Cell-owned result slots, with device-side novelty,
actual returned identities and collision obligations. Do not fall back to claiming
that a learned float prediction is a committed constructor or union. Mutable and
scalar effects, multi-source matching, lifetime-safe ownership transfer and the
cross-stage fixed-point controller remain required by the active goal.

Reproduce:

```
PYTHONPATH=benchmarks/eggcc-gpu-supervision $PYTHON -m unittest \
  test_context_effect_projection test_device_alias_completion \
  test_lower_device_entries test_device_token_commit \
  test_continuation_contract test_cell_token_successors
$PYTHON benchmarks/eggcc-gpu-supervision/lower_device_entries.py TRACE OUTPUT.json \
  --source-slots --context-completion
```
