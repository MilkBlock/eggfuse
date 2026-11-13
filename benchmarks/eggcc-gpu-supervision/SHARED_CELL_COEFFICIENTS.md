# Exact coefficient sharing: tested, not selected as the default

This experiment checks whether repeated Cell aggregation coefficients can be
shared without a device-side lookup table. Results preserve all recovered
states, but do not justify replacing the two-group baseline: meaningful byte
savings require more aggregation groups; keeping group count fixed saves only
23,760 bytes on the current trace.

The model and observed routing are frozen. Source token indices remain private
to each instance. Exact float32 base/route coefficient bytes determine sharing;
shape, template name or equal outputs alone do not. This is numeric constant
sharing, not a proof that two Cells or their effects are semantically equivalent.

## Two implementations

**Extract one shared layout per layer.** Consider exact coefficient layouts
used by at least eight instances, choose at most one per layer by nominal byte
savings, and leave the remainder in at most two degree groups. Adopt the split
only if the actual resulting coefficient arrays are smaller. This is a storage
admission test, not a speed predictor. The selected group keeps its N×E source
index array but broadcasts a 1×E×128 base and 1×E×4 route tensor. Identical static
matrices can also be interned across layers.

**Broadcast within existing groups.** Do not split or reorder groups. A base or
route tensor with identical rows is replaced by a copied single-row tensor.
The copy avoids retaining the original expanded array through a NumPy view.
Exact repeated matrices are interned independently of source indices.

GPU setup uploads each shared matrix once and reuses its array reference.
Interning occurs on the host during preparation; no GPU hash table, dynamic
owner lookup or per-token branch is introduced. Shared arrays are broadcast by
the existing floating matrix operations. Both paths remain optional prototype
plans; the native Cell executor is untouched.

## Actual dot-product result

| Plan | Unique coefficient bytes | Aggregation groups | Rows with broadcast coefficients |
|---|---:|---:|---:|
| Two-group baseline | 14,694,768 | 59 | 0 |
| Extract shared layout | 13,045,824 | 75 | 316 |
| Broadcast existing groups | 14,671,008 | 59 | 35 |

The extracted plan has 16 shared groups. Logical referenced coefficient bytes
are 13,050,048; cross-layer interning reduces actual distinct matrix storage to
13,045,824. Existing-group broadcast affects six groups and saves about 0.16%
of baseline coefficient storage. All plans still perform 31 ridge readouts.
Model weights, source states and unknown-state coverage are unchanged.

Both sharing variants and the original replay recover **3,647 / 3,855** covered
states. All CPU/GPU, original/new-plan and reused-plan checks pass. Maximum
absolute difference versus original is about 1.61e-6, inside the unchanged
atol=0.002 / rtol=0.004. Unseen states and templates remain explicitly outside
the training dictionary. There is no native semantic acceptance or new model
accuracy claim.

## Why neither is the new default

In the final diagnostic, baseline / extracted / existing-group preparation
costs were 19.60 / 57.22 / 24.68 ms. Their second GPU calls were 5.11 / 4.93 /
5.32 ms. An earlier implementation check had extracted sharing slower than
baseline (6.98 versus 4.93 ms); the direction did not persist. These are short
reuse diagnostics, affected by compilation caches and execution order, not a
throughput campaign. They do not establish a stable speed benefit.

The extracted plan's approximately 11.2% coefficient savings come with 16 extra
aggregation groups and substantially more preparation. The no-split plan avoids
extra groups but saves too little. Keep the two-group baseline and record these
negative tradeoffs rather than treating smaller arrays as sufficient success.
Complete-row equality is a conservative numerical condition; this result does
not establish that egraph inference lacks locality or that deeper template
factorization is impossible.

## Reproduction and verification

The `packed_cell_replay.py` command from `PACKED_CELL_REPLAY.md` now also runs
`shared` and `broadcast` variants. The frozen model, input traces and training
hashes are checked. `shared-cell-coefficients-results.json` records all costs,
recovery counts and numerical checks from the final diagnostic. Raw data and
models stay on the external SSD.

Tests verify that different source indices share only constants; different
weights cannot be merged merely by shape; exact constants are reused across
layers; and existing-group broadcasting keeps group count, owns its compact
storage and preserves output. The related suite passes 88 tests. No gradient
descent or additional ridge fitting occurs.
