# Device encoding of live consumer inputs

`device_input_features` fills a gap between device-resident slots and trained
ridge: dynamic seed and neighborhood features previously arrived as CPU-built
request arrays. The new encoder consumes projected input roots, slot validity,
numeric values and available scalar codes. `infer_from_slots` feeds its output
directly into live-source ridge without host feature materialization. It does
not perform the query match that establishes those input slots.

`compile_inputs` derives required query slots, typed roles, two-round operand
neighborhood roles and static request vectors from the existing Cell rule. It
uses no observed completion labels. Ordinary and neighborhood role columns share
one Eq partition mask and matrix aggregation. The resulting moments are split
back into the exact existing 128-wide seed and 256-wide augmented query feature.
This does not change the frozen target or retrain ridge.

Finite supported f32 numbers generate `tanh(sign(x)*log1p(abs(x))*numeric_role)`
on device. Integer identities stay integer; numeric features neither replace
exact scalar storage nor implement scalar RHS effects. The audit accepts a raw
numeric input only if it is exactly representable in f32, preserving the original
feature input value. Categorical and other numeric inputs need an available
resident code; an unavailable code leaves the request pending. Runtime creation
of new categorical codes remains an obligation. Required missing slots, invalid
Eq roots and nonfinite numeric inputs cannot authorize continuation.

## Evidence

The dot-product audit reads successful query inputs, never RHS post-states as
features. Across 5,935 inputs and 154 templates, maximum difference from existing
training encoding is 2.38419e-7, with zero components exceeding 2e-5 and no blocked
inputs. 6,385 numeric scalar occurrences are encoded on GPU; 374 occurrences use
CPU-prepared resident fallback codes. Typed equality classes and source slots
are still CPU-provided oracle inputs in this audit. This is not GPU matching.

198 audit batches take 0.873 s including compilation, excluding packing, upload,
readback and matching. This is no throughput or accuracy improvement claim.
59 mechanism tests pass, including a compiled input-slot-to-ridge invocation
without intermediate host features, missing scalar rejection, and CPU/GPU
agreement. The integration test uses synthetic ridge weights; the real input
encoding audit checks the feature representation independently.

## Reference and remaining obligations

Bake reference tip `96b92111` restores the original whole-workload denominator
rather than substituting a smaller recent artifact. Likewise these local tests
are not the full objective: CPU-generated successful matches, unknown effects,
full ownership transfer, Run closure and original stage progression remain
unfinished. No native runtime code was modified. The next structural integration
must project consumer inputs from device matches and pass their existing validity
and generation evidence into this encoder, without building a second binding
representation. Scalar values produced by GPU effects must update the same input
columns; reconstructing them from saved traces is not an implementation.

Reproduce: `audit_device_input_features.py TRACE OUTPUT`. Results are recorded in
`device-input-feature-results.json`, including trace identity and limitations.
