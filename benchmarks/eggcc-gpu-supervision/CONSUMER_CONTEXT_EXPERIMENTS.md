# Consumer interpretation and shared-neighbor experiments: not adopted

This experiment reuses the five-program training set (129 real accepted Cells)
and exact-source GCD/LCM validation captures. It performs no new graph execution,
no gradient descent, no threshold search and no alpha sweep. All predictors use
ridge alpha 10; the same previously trained decoder and threshold 0.5 remain frozen.
It does not optimize or replace the CPU executor.

## Three implemented hypotheses

1. **Consumer-role gates.** Compile a fixed 32-dimensional projection of each
   semantic query port's role. Add boundary-message times consumer-gate columns
   during training. For a fixed template, fold their coefficients into the original
   boundary coefficients. The resulting runtime input width stays 2177; the fixed
   multiplication is eliminated, although a template-specific coefficient bank
   costs storage. Rule numbering and program metadata are not float features.
2. **Separate Cell matrices.** Fit a residual matrix per semantic Cell template
   from that template's training samples, using the same resident prior and alpha.
   Template dispatch supplies the matrix identity; no learned rule-ID embedding
   or new dynamic GPU branch is required. This is not executed in the resident path.
3. **Shared logical-neighbor messages.** The old boundary input pools each consumer
   port separately. It does not explicitly encode whether two ports connect to
   the same logical neighboring Cell. The new encoder forms a per-port/per-neighbor
   floating message, then a channel-wise Gram matrix across input ports, summed
   over logical neighbors. Pair counts normalize the products before tanh. These
   are products of actual dense token/role messages, not Boolean matrix arithmetic
   disguised as floating inference.

The shared-neighbor encoder uses the existing typed connectivity and owner-projected
snapshot. Shared physical payload ownership is not treated as logical co-occurrence.
Only current eligible neighbors contribute; imported IDs only determine connectivity.
Its 896 extra floating columns increase the model input from 2177 to 3073. It does
not add a runtime fact graph or producer consumer lists, and is not installed.

A nondegenerate test has identical per-port marginal messages but different joint
neighbor membership; the new encoder distinguishes those graphs. ID renaming leaves
it unchanged, and an ineligible NaN neighbor cannot poison its output.

## Fixed validation comparison

| Model | GCD exact | GCD closure false merges | GCD true dynamic positives | LCM exact | LCM closure false merges | LCM true dynamic positives |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Retained global boundary ridge | 35/41 | 0 | 8/18 | 82/99 | 13 | 16/37 |
| Consumer-role gates | 34/41 | 6 | 9/18 | 80/99 | 15 | 18/37 |
| Separate Cell matrices | 33/41 | 7 | 12/18 | 81/99 | 13 | 23/37 |
| Shared-neighbor messages | 35/41 | 0 | 9/18 | 77/99 | 21 | 16/37 |

All three candidates are rejected for replacing the retained model. More positive
predictions do not compensate for the new false merges. The shared-neighbor
representation contains useful structural information, but this particular fitted
model does not generalize better on LCM. Do not report it as an accuracy or speedup.
The full JSON includes every training case and direct/generated validation split.
These validation sets are used for development, not a final held-out acceptance.

## Numerical validation and costs

Static gate folding agrees with explicit conditioned inference within 1.35e-6.
GPU predictor matmuls agree with CPU within 3.84e-6. The first accepted real bridge
block from each program is replayed on the GPU; bridge features agree within
1.79e-7 and integer-valued neighbor counts agree exactly. This does not constitute
a full feedback replay of any candidate or authorize a learned Eq.

Storage is charged explicitly:

- separate Cell coefficient bank: 3,343,872 bytes;
- folded gates: 852,480 shared-prefix bytes plus 786,432 template-boundary bytes;
- bridge predictor coefficients: 1,573,376 bytes, plus 896 new floats per lane.

The bridge kernel additionally materializes per-port/per-logical-neighbor messages;
this scratch and connectivity cost is not eliminated by the model. No runtime
speed claim is made. Failed candidates do not justify further costly full GPU graph
benchmarks. Binary candidate weights stay on the external disk; reproducible sources
and text results are retained in Git.

## Provenance and interpretation

Every archive is hash-checked and keeps its original training or validation partition.
Programs cannot appear in both. Exact-source captures from a later coefficient model
are accepted only when its explicit supplied archive has exactly the same floating
feature map/encoding as the resident model. Predicted-source archives are excluded
from this controlled comparison. All original semantic Cell definitions must agree.

An additional read-only check found no unseen Get index values in validation: the
training programs cover indices 0 through 5; GCD uses 0 through 3 and LCM 0 through 4.
Gross boundary-vector saturation is not established either: nonzero components with
absolute value above .99 are about 1.0% (Pascals), 1.5% (Euclid), 2.0% (GCD) and
3.2% (LCM). Neither observation supports declaring an unseen-scalar or wholesale
saturation explanation for these failures.

The next structural question is the output representation: can Bake enumerate
legal local Eq states satisfying the template's static conditions and let ridge
select a coherent completion state, instead of independently decoding pairs that
may become nontransitive? Scalar values and external identities must retain their
actual slots; observed targets alone cannot define the complete set of legal states.
That next representation is not implemented or claimed correct by this experiment.

## Reproduction

Use `condition_boundary.py MODEL DECODER DECODER_REPORT OUTPUT` with the project
MLX Python, five repeated `--train` paths and two `--validation` paths. Add
`--capture-model` for the frozen five-program model used to obtain LCM's exact-source
capture. All artifacts are under `/Volumes/Extreme SSD/eggfuse-artifacts/21ee`:

- resident `class-history-neighborhood-input.npz`;
- decoder `five-program-boundary-decoder.npz/.json`;
- training `pascals-boundary-labeled.npz`, `euclid-boundary-labeled.npz`, and the
  three `.labeled.npz` paths in `boundary-training/manifest.json`;
- validation `gcd-boundary-labeled.npz`, `lcm-live-boundary-labeled.npz`;
- allowed later capture model `five-program-boundary-model.npz`.

The runner checks feature reconstruction, source partitions and numerical folding.
Its saved NPZ contains experimental coefficients only; no resident model is modified.
