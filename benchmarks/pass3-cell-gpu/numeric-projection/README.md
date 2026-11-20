# What a neural Cell proposal must supply for an integer min rule

A structural proposal names a compiler-certified route, pivot and physical anchor row. The proposal head sees the pending source epoch, row and cursor age, delta watermark, cursor depth, rule shape and producer identity. A logistic model selects candidate anchors before any suffix-table lookup or arithmetic. An exact typed candidate provider enumerates table/delta/Spine entries. Its cost remains part of the engine. This is a scoped neural component inside real Pass 3, with an ordinary exact residual. It does not autonomously discover every possible rule or row on the graph.

The compiler follows the RHS set value backward through copies, signed i64 literals and additions from either the LHS or the RHS. It admits unary-key i64 functions with a min merge and a single final set. The static program provides the argument slots, operand order and deterministic calculation. The trainable numeric head gets only the witnessed numeric operands and its learned coefficients. It never gets the correctly computed sum as a feature. The fits use actual winning operand/result pairs from the four training families. The structural head and per-rule thresholds are trained once per seed on prospective candidate features and post-Run winner labels. The thresholds use the tenth percentile of the training winners for their own rule. All arms for a given seed compare exactly the same multiset of (Run, rule, pivot, physical candidate) selected before suffix matching.

| Arm | Conditional activation and typed evaluation |
| --- | --- |
| Trace control | Same candidate and write observer with all structural selections disabled. This measures the shared tracing cost. |
| Exact engine | Existing GPU Pass 3 search and arithmetic without tracing this experiment. |
| Predicted value | A selected anchor produces inputs for a learned binary32 regression head. Round to signed i64, check against the compiled checked integer program, and use the proposed value only if it agrees. Declines and mismatches explicitly leave exact residual work. |
| Structural only | A selected anchor names structural inputs. The typed source evaluates the candidate word exactly. |
| Visible port | Keep the structural choices. An active previous attribute receipt can resolve the child operand directly to its current physical row and committed scalar. Missing entries use the ordinary point lookup. |
| Candidate as visible | Try to consume a previous candidate in the slot for a visible fact. If prior and post-merge values differ and the candidate lost `min`, reject this substitution and resolve the visible operand. |
| Forced wrong | Frozen structural selections with a deliberately corrupted numeric proposal. Count the exact recoveries. |

The receipt identifies the producing RHS ordinal, target key, physical row, version and table. It contains separate fields for old-value presence, previous value, candidate, merged visible value and write disposition. The direct directory is scoped by relation and canonical key. Any row touch clears its visible receipt, including rebuild updates; lookup also checks row identity, generation and subsumption. No-op sets may issue new proofs of an already visible binding. An independent audit checks the actual ordered effective-write record and verifies signed `visible=min(old,candidate)` for each previously occupied key. It checks inter-Run input-port source ordinals against actual physical rows and visible values.

Actual search and commit run on device in every arm. A diagnostic disables all unproposed/unverified numeric-domain matches at the entrance (including ordinary non-Spine matches), retaining unrelated exact source rules. It measures where the altered execution diverges. This control is distinct from disabling all residual execution for an autonomous whole Pass 3.

## Full Pass 3 outcomes

All four program/seed pairs and all assisted negative controls align through the source Run sequence, ordered RHS inputs, effective writes, Spine, unions, roots and final typed graph. The numeric-domain structural selector starts from the certified-table candidates and retains a small subset of rule 154. It receives no arithmetic answer. The rest of the original source matches remain charged to the exact engine.

| Case / seed | Numeric-domain admitted / all | Concat admitted / all | Writes among admitted Concat | Direct lookup hits / eligible probes | Exact / Trace / Predicted / Structural / Visible ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| sum-bits/1703 | 98 / 291 | 5 / 55 | 3 | 107 / 403 | 848 / 853 / 875 / 891 / 866 |
| sum-bits/1709 | 98 / 291 | 5 / 55 | 3 | 107 / 403 | 878 / 875 / 876 / 885 / 878 |
| dot-product/1703 | 186 / 928 | 6 / 197 | 5 | 97 / 311 | 902 / 911 / 928 / 923 / 923 |
| dot-product/1709 | 174 / 928 | 6 / 197 | 5 | 97 / 311 | 941 / 950 / 955 / 951 / 943 |

Each timing is the median of ten interleaved resident passes with identical stage and final-state audits outside the interval. Diagnostic arms retain the same recorders. The predicted-value policy happened to round to the mathematically exact value for every *admitted* binding in the real anchors; forced-wrong claims were all refused and recovered. These data provide no consistent whole-pass speed advantage for predicting the integer. The minimal typed proposal can omit this field without losing any real admitted RHS.

In sum-bits, rule 154 had 27 new keys, six decreasing writes, 15 larger losing candidates and seven equal candidates. Dot-product had 39 new keys, 122 decreases and 36 larger losing candidates. On sum-bits Run 110, neural binding #906 read visible numeric ports #739 and #740, each equal to 1; candidate 2 lost against the old value 1 and caused no write. Across the numeric rule family, 22 later admitted operand reads used a visible size that differed from its producer’s losing candidate. Three of these had both neural producer and neural consumer. An example is #3240 (Run 493, rule 153) → #7039 (Run 1220, rule 150). The earlier candidate was 4, the visible result was 1, and the consumer read 1. Dot-product had 66 such reads, 13 with both sides admitted. [Per-binding source facts](lineage.json) · [Paired results](results.json) · [Restricted-domain control](without-domain-residual.json)

## Independent source-compiled counterexamples

In the three-Run fixture, the same projected Concat candidate `4+7=11` addresses two occupied keys. With old 9 the source emits no write and the next selected consumer reads 9. With old 15 it writes 11 and the consumer reads 11. Forcing the candidate into a visible-value port triggers refusal for the losing value. A second compiled fixture uses 16,777,216 and 16,777,217. Both inputs have the same binary32 representation and produce the same numerical prediction. The i64 source program produces 16,777,223 and 16,777,224 respectively, and the verifier rejects the mismatches. The fixtures force structural activation to test these cases and independently compare GPU events and graph with the audited native CPU runtime. [Min conflicts](conflict.json) · [Precision](precision.json)

## Reproduction

```sh
dir=benchmarks/pass3-cell-gpu/numeric-projection
families="$EGGFUSE_ARTIFACT_ROOT/repair-bake-families-20261120"
ref="$EGGFUSE_ARTIFACT_ROOT/pass3-atlas-integration-20261120"
reader="$EGGFUSE_ARTIFACT_ROOT/rotary-axes-20261119/packed-1703/final.pt"
out="$EGGFUSE_ARTIFACT_ROOT/NEW-numeric"
export PYTORCH_ENABLE_MPS_FALLBACK=0
python "$dir/train.py" "$families" "$ref" "$reader" "$out"
python "$dir/study.py" "$families" "$ref" "$reader" "$out" "$out/paired"
python "$dir/lineage.py" "$out/paired" "$out/lineage.json"
python "$dir/independence.py" "$families" "$ref" "$reader" "$out" "$out/without-domain-residual"
target/release/eggfuse-cell-compiler compile --source "$dir/conflict.egg" --output "$out/conflict"
target/release/eggfuse-cell-compiler compile --source "$dir/precision.egg" --output "$out/precision"
# Build the CPU observers if an --audit-events enabled executable is not already available.
cargo build --release --locked -p eggfuse-cell-runtime --features slot-transfer-audit
audited_runtime="$CARGO_TARGET_DIR/release/eggfuse-cell-runtime"
python "$dir/fixture.py" "$out/conflict/program.json" "$reader" "$ref/ports-1703.pt" "$audited_runtime" "$out" "$out/conflict-check"
python "$dir/fixture.py" "$out/precision/program.json" "$reader" "$ref/ports-1703.pt" "$audited_runtime" "$out" "$out/precision-check" --precision
```
