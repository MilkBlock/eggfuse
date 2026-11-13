# Source-slot continuation through numerical token admission

`device_entry_transition.step` connects the existing recipe-derived single-source
Entry matcher to input encoding, trained ridge and token admission. It consumes
resident source state, not saved consumer bindings. Within one compiled call:

1. The checked Entry projects actual source slots and current Eq roots once.
2. Consumer query-slot validity and scalar availability gate input encoding.
3. Shared ordinary/neighborhood roles generate seed and query features on GPU.
4. Compiled source/consumer port-role coefficients pool the current source token.
5. Ridge generates the candidate token, and existing admission performs exact
   key deduplication, generation/visibility checks and allocation.

The square test transform is bypassed. No intermediate host feature vector is
produced. Actual returned identities remain distinct from their current Eq roots.
Changing a current root changes the floating input state without replacing the
actual result identity. Missing results or dirty source tokens block admission.

Optional numeric/category columns project through exactly the same slot addresses
as ordinary values and are carried into the admitted instance. They are not a
parallel binding table. `commit` rejects an update that would lose scalar columns
already present in state. This still does not implement scalar RHS operations or
categorical-code generation. Effect outputs without known scalar features cannot
be consumed as if their features existed.

The compiler builds coefficients for this one-source interface directly from
source and consumer roles. Each projected Eq input is a source message, with the
same four-channel feature dimensions as the frozen neighborhood-input model.
This is not a claim that its provider distribution is identical to the model's
observed multi-provider training distribution; accuracy must be evaluated.

## Evidence and limits

62 mechanism tests pass. The integrated compiled test creates a successor from
an actual foreign result identity, preserves separate roots, then suppresses the
same successor on a second round. Missing result, stale floating state and wrong
stage cases do not admit. Scalar column projection is checked independently.
No ownership transfer bit is granted by these fixtures.

`audit_device_entry_transition.py` uses the actual dot-product recipe and frozen
trained neighborhood-input ridge weights. From 157 lowered single-source Entries,
44 have a complete captured source example. All 44 produce a finite candidate
and admit its exact projected key without a CPU consumer match list. The other
113 are untested, not successful. Source identities are locally relabeled while
preserving exact identity/partition relationships. Sources are CPU captures;
there is no autonomous initial-graph bootstrap in this probe.

This checks projection and pipeline execution, not whether ridge predicts the
correct completed semantic state. Pending effects remain pending, all actual
transfer coverage flags remain false, and no new stage-closure authorization is
introduced. Multi-source/late/union-enabled matches, visibility across original
Runs, ownership takeover and autonomous stage iteration remain required.

Reference Bake tip remains `96b92111`: keep the original whole-workload objective
and denominator authoritative. Forty-four source probes do not stand in for full
Eggcc execution. No native runtime or full-workload speed claim is made.

Reproduce: `audit_device_entry_transition.py TRACE MODEL OUTPUT`; evidence is in
`device-entry-transition-results.json` with trace/model hashes and per-Entry data.
