# Resident whole-state token feedback

The bounded completion-state representation now runs at actual GPU token birth,
and subsequent Cell queries and boundary aggregation consume the reconstructed
floating token. This is an opt-in standalone Eggcc selected-family experiment,
not a complete native Eggcc runtime or authoritative learned completion.

## Execution and ownership

The existing query path obtains live owner-projected bindings and source tokens.
Ridge emits its 128-dimensional prediction. The frozen decoder then scores local
Eq pairs. Bake supplies the complete static-compatible state matrix and current
query-Eq projection. A dense score matmul, fixed mask and argmax select a whole
state. Its baked first/second moments combine with actual dynamic scalar codes to
produce the same 128-dimensional token format.

`device_join_transition.proposals` hands this token directly to existing admission.
It retains the same exact slots, witnesses, generations and takeover descriptors.
The selected state does not write roots, authorize union, or create a second set
of runtime bindings. Invalid scalar sources and nonfinite predictions block
admission and mark the missing evidence. Scalar results not available from current
query slots are rejected at compilation; they are not fabricated from a state ID.

Generated templates retain the reconstructed birth token through effect completion;
imported Cells retain their exact encoding. Subsequent matching uses original exact
GPU facts, while floating inference consumes the reconstructed tokens. Existing
query-owner takeover still performs physical payload transfer/release. The new
path introduces no producer consumer list or CPU-side future match information.

Runtime selection uses fixed operations and static template specialization, not
GPU data-dependent traversal. It is an additional output constraint on existing
learned dense floating computation, not a claim that binary state selection itself
is a neural-speed implementation of the egraph.

The CLI requires `--predicted-source-feedback`, `--experimental-boundary-model`,
`--boundary-context`, `--completion-decoder`, and `--completion-decoder-report`.
The decoder hash, parent model, alpha selection and semantic family are checked.
No retraining, gradient descent, threshold tuning or validation-label feedback is
performed. The normal path remains unchanged when these options are absent.

## Audits

Captures preserve the raw ridge prediction, selected state, mandatory current Eq,
actual scalar codes and reconstructed token. Labeling independently reconstructs
the input floating feature map, frozen decoder computation and state choice, and
checks scalar codes against original input scalar identities. CPU saturation is
used only afterward to derive labels and compare effects.

The feedback comparison checks identical shared integer/boolean arrays, identical
CPU targets and nonzero changes in generated-source floating inputs. Unlike an
unconstrained prediction, a correctly reconstructed token can equal its exact
source token; therefore this mode requires observed changed generated consumers
and reports their count, rather than requiring every consumer to change. The
older unconstrained experiment retains its stronger every-consumer check.

The final readout audit reports both selected-state accuracy and decoding accuracy
of the reconstructed token, including any disagreement between them. Neither
constitutes permission to commit a predicted equality.

## Results and costs

See `gcd-state-feedback-*` and `lcm-state-feedback-*` text reports. These are fixed
validation programs, not final held-out acceptance. Every Run graph, per-rule
match count, full final selected-family graph and query witness must pass the
independent original-rule CPU interpretation. GPU diagnostic times include compile,
execution, captures and fixed flushes; they are not throughput comparisons.

The GCD run starts at original snapshot 437, uses rules 283/290/293, and completes
3 Runs, 41 generated Cells, 15 generated-source consumers and 30 physical owner
releases. All 454 shared symbolic arrays match the exact-source capture; all 15
generated consumers and one direct consumer with generated ambient neighbors have
changed floating inputs. Exact predicted partitions remain 35/41, false merges
remain zero, expanded misses fall from 16 to 10, and quotient recall improves
from 8/18 to 11/18. Direct-source accuracy remains 23/26.

The run took 31.220 s including diagnostic setup/execution versus 0.165 s for the
CPU reference plus audit. These costs explicitly do not support a GPU speedup.
Decoder feature expansion, readout and output projection add work; they do not
remove dense exact query/completion costs. Baked token moments and small state
matrices were counted in `COMPLETION_STATES.md`; decoder matrices and per-candidate
feature scratch also remain live.

LCM starts at snapshot 514 and completes 3 Runs, 99 generated Cells,
21 generated-source consumers and 25 physical owner releases. All Run graphs,
per-rule counts, final graph and 454 shared symbolic arrays pass. Twenty of 21
generated consumers have changed input features, as does one direct consumer
through ambient context. All CPU targets are unchanged.

| Metric | Unconstrained feedback | Whole-state feedback |
| --- | ---: | ---: |
| GCD complete partitions | 35/41 | 35/41 |
| GCD quotient true positives | 8/18 | 11/18 |
| GCD closure false merges | 0 | 0 |
| LCM complete partitions | 82/99 | 83/99 |
| LCM quotient true positives | 16/37 | 23/37 |
| LCM quotient false positives | 4 | 3 |
| LCM expanded closure false merges | 13 | 7 |
| LCM expanded missed equalities | 35 | 21 |

LCM direct-source accuracy remains 71/78; generated-source accuracy increases
from 11/21 to 12/21. Both workloads have zero discrepancies between selected Eq
states and the readout of reconstructed tokens. Full live CPU/GPU floating
reconstruction error is at most 2.93e-6. This preserves the offline consistency
benefit under actual feedback; it does not establish improved direct-source
features or correctness of all predicted states.

LCM diagnostic GPU time is 258.244 s, CPU reference plus audit 0.236 s. No speed
claim follows from this single instrumented run. Twenty-six relevant tests pass,
covering optional-path isolation, unchanged exact slots/admission, live token
replacement, GPU parity, scalar readiness, nonfinite rejection and existing owner
transfer/effect behavior. No CPU executor is modified in this change.

## Unresolved scope

- Direct-source information loss remains; existing training examples already
  contain the target-state classes involved in GCD's direct failures.
- Reconstructed birth tokens are not re-predicted after later external unions.
- Selection is over type-compatible states, not a proof of reachable completion.
- New scalar effects, broad primitive/mutable/deletion semantics, all original
  Eggcc stages, learned authoritative completion and CPU correction integration
  remain unfinished.
- Result-witness owner joins from the CPU Bake branch are still separate work.

Latest inspected Bake is `codex/cell-parallel-admission` at `2b12f110`. Its conditional
native-address layout requires an actual bound result and survives relocation only
with revalidation or fallback. We preserve the same obligation by reading current
owner-projected inputs and retaining exact lifecycle metadata. A selected floating
state is never treated as an actual constructor result address.

## Reproduce

Artifacts are under `/Volumes/Extreme SSD/eggfuse-artifacts/21ee`. Use the project
MLX Python and the commands in `LIVE_PREDICTION_FEEDBACK.md`, adding:

```
--predicted-source-feedback \
--completion-decoder ROOT/five-program-boundary-decoder.npz \
--completion-decoder-report ROOT/five-program-boundary-decoder.json
```

Use GCD snapshot 437 / 12 ticks or LCM snapshot 514 / 16 ticks, writing
`*-state-feedback-witnesses.npz`. Label with `label_composed_witnesses.py` plus
`--completion-decoder ROOT/five-program-boundary-decoder.npz`; then run
`audit_device_match_readout.py` and `audit_prediction_feedback.py` against the
matching saved exact-source capture. Binary captures stay on the external disk.
