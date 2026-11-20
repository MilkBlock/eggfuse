# Variable-width certificates on native CPU Pass 3

All inference is single-threaded Rust CPU. PyTorch trains the forest and shared port heads offline. The native 12,829-parameter forest forward selects the same actual static-root/consumer candidates for every arm. Before evaluating any source Run, a second shared head predicts local typed references within each selected one- or two-table-atom Cell. A reference addresses a logical member and column relative to the generated parent port. It is resolved to the actual Cell-runtime source dependency with the original Run's visibility. The compiled complete-key cohort has one free boundary reference. Bindings outside this grammar are covered by the authoritative exact path and reported separately.

| Layout | What crosses the model/verifier boundary |
| --- | --- |
| Fixed, sealed raw | Up to four or six separate member/column references and actual Rust typed values. The value head selects a value from a training-only typed vocabulary using source features and the generated root latent. The complete fixed record precedes Run 1. Exact values are compared with the live source at publication. |
| Fixed, value-copy | Every field has an independent value-copy address and provenance address. Their Rust typed values are hydrated when the witnessed row is visible, using a fixed-size value bank. This measures a deferred-copy representation of a discrete value. |
| All logical ports | The shared learned head emits one member/column reference per actual LHS field. References are packed contiguously with per-claim offsets. The verifier checks the identity of the exact matched member and column. |
| Boundary only | The original learned forest activation and source-port header are retained. A compiler projection supplies all local fields. There is no per-field reference or typed-value bank. |

The exact same Rust checker carries each source event, performs necessary point checks, and preserves original ordered publication. If a payload fails after an exact-key check has established the native source binding, the assisted engine can commit it as exact work; the rejected token gets no neural credit. Disabling residual completion forbids that rescue. The base forest assembles candidate root/effect pairs from the compiled source; its neural component activates children using the generated root state. This experiment holds that choice fixed so that losses measure the output representation.

## What changes on the full source programs

| Pass 3, seed 1703 | Boundary/full-reference/6-field copy child RHS | 4-field copy | 6-field presealed raw values | All source RHS |
| --- | ---: | ---: | ---: | ---: |
| sum-bits | 91 | 82 | 1 | 7,265 |
| dot-product | 195 | 169 | 1 | 6,704 |
| GEMM-bias-ReLU | 207 | 189 | 1 | 15,462 |
| stable-argmax | 128 | 114 | 5 | 8,190 |

Seed 1709 gives 92, 195, 207 and 128 valid children for the boundary-only arm. The four-field records lose 9, 26, 18 and 14 valid bindings for each seed; all those losses are explained by source width. For example, sum-bits seed 1703 generates 314 extra references in the all-ports arm, 376 fixed slots plus an independent copy address per slot in the four-field arm, and no extra local references in the boundary arm. A single source boundary reference remains in all layouts.

Fully sealing the actual values before inspecting source rows is a much harder task. In sum-bits seed 1703 the six-field vocabulary can express all ground-truth fields of 46 out of 91 possible children. The trained model supplies all correct values for one binding. In dot-product the vocabulary reaches 89/195 complete field sets and the model supplies one binding. The fixed copy arm avoids predicting raw numeric/class identities because its learned selection names a typed source field. These are materially different outputs. Neither eliminating four-field overflow nor making the local port head perfect addresses the approximately 98% of full source bindings still outside this **particular selected forest** on sum-bits. [Ordered full-source results and strata](results.json) · [Raw-value ceilings, field accuracy and eight paired samples](sealed-values.json)

**Runtime.** Original state, ordered RHS, writes, Spine and event logs match on every assisted run. In sum-bits seed 1703 the paired resident medians were 27.34 ms for boundary, 27.95 ms for all fields, 28.76 ms for four copies and 26.52 ms for six copies. Boundary projection reduced local-head work (around 0.012 ms vs 0.054 ms for the all-port head in this case); whole-pass timing was not consistently faster across seeds and source families. All source and carrier costs are reported with raw samples. Cold CLI includes process startup, parsing and audited export. Resident warm trials exclude graph setup and post-run graph hash checks. The actual Rust vector capacities for reference storage, typed values, offsets and diagnostic counters are reported separately; typed value size is platform-dependent, and heap payloads owned by a value and process RSS are outside the Vec-capacity totals. [Allocation audit](allocation.json)

**Generality and falsification.** Four training families supply real published instances. The logical schema includes table identity, typed arguments, repeated variables and execution-pivot order; complete shape hashes are held out, and cold templates and actual width/slot counts are reported independently. The small port head has 466 parameters and trains for 400 updates per seed. The raw-value head also uses four training families only and reports a per-sort vocabulary ceiling. The trained policy always runs in Rust, and the emitted root/child header and all local port choices are cross-checked with the independently executed PyTorch forward. Fresh counterfactuals reverse only the reference or only the value logits, which produces **validly typed, in-range** substitutes; null/out-of-layout controls are separate. The verifier rejects different provenance even when a different value source would happen to supply equal data. [Counterfactuals](adversarial.json)

## Reproduction

The experiment builds an isolated copy of the current native runtime to add optional instrumentation and the variable-width payload. The regular native CLI and original forest policy remain in charge of matching and scheduling. The reproducible source hook is at the native validated-binding boundary and the forward hook appends the typed payload after the real root latent has been produced. [Native Rust port model and checks](variable_ports.rs) · [Build hook](build_native.py) · [Paired native service](port_session.rs)

```sh
dir=benchmarks/pass3-cell-gpu/variable-certificates
exp=/Volumes/EggFuseWorkspace/experiments
families="$exp/repair-bake-families-20261120"
ref="$exp/pass3-atlas-integration-20261120"
forest="$exp/whole-pass-generation-20261120"
head="$exp/NEW-port-head"
build="$exp/NEW-port-runtime"
gold="$exp/native-forest-20261120/paired"
a="$exp/NEW-ports-anchors"
h="$exp/NEW-ports-heldout"
python "$dir/port_model.py" "$families" "$exp/recurrent-compositions-train-20261120" "$forest" "$head"
python "$dir/build_native.py" "$build"
python "$dir/native_study.py" "$families" "$ref" "$forest" "$head" "$build" "$gold" "$a" --cases sum-bits dot-product
python "$dir/native_study.py" "$families" "$ref" "$forest" "$head" "$build" "$gold" "$h" --cases gemm-bias-relu stable-argmax
python "$dir/faults.py" "$families" "$ref" "$build" "$gold" "$a" "$h" "$exp/NEW-correct-sort-faults"
python "$dir/byte_audit.py" "$families" "$ref" "$build" "$gold" "$a" "$h" "$exp/NEW-port-allocations"
python "$dir/raw_values.py" "$families" "$ref" "$forest" "$head" "$build" "$gold" "$a" "$h" "$exp/NEW-presealed-values"
```
