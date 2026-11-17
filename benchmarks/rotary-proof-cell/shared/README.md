# Structure preservation and shared relation/pointer heads

This standalone GPU prototype replaces the flat 128-float recurrent MLP with a
279-float structured state. All old observations and source requests are copied
inside GPU-generated tokens. A shared relation MLP, a shared pointer MLP and a
shared activation MLP produce dynamic state. There is no CPU reconstruction or
inference fallback. The source egglog runtime is unchanged.

The exact ABI is in `abi.py`: 64 relation probabilities, 72 pointer probabilities,
139 protected source-input floats, three phase flags and one activation score.
Cell rotation acts on the first 64 lanes; port rotation is in transient reference
keys. Each transition takes the previous generated token plus schedule/address
metadata. Static input retention is a fixed copy operation, not a learned success.
The state is 1,116 bytes, versus 512 previously; no compression claim is made.

`PROTOCOL.md` records the first frozen experiment, including 16 fresh structures.
All three end-to-end-only runs are retained under `results/end-to-end`. Seed 1721
passes every original and fresh panel; 1703 fails to fit the pointer composition
even on training replay, and 1709 also fails to fit union. These failures are not
reclassified as correct. The result demonstrates representational capacity but
unstable fitting, rather than robust acceptance across initializations.

Six unit/contract tests pass. The model has no separate learned classifier per
endpoint pair. Ordinary GPU matrix features, state copies, source scheduling and
proof-template instantiation remain outside the learned heads. CPU verification
decodes actual saved token bytes and uses the existing independent source checker.

## Follow-up: local supervision and a new final holdout

The end-to-end-only failure was diagnosed on training-domain examples. The
follow-up adds offline primitive-rule labels for relation updates, individual
swaps, insertion and activation. These labels are manually derived from this
example's source rules; no implemented Bake compiler is being claimed. Runtime
inference still calls learned heads, never the label generator. This changes both
the representation and the training supervision compared with the old flat model.

The first 16 fresh shapes became development diagnostics after inspection.
`LOCAL_PROTOCOL.md` freezes another 16 shapes, disjoint from the 10 original and
16 inspected shapes, before the follow-up fitting. All three seeds again use the
same 32,768 original training cases and the final step-6000 checkpoint. No final
holdout chooses weights or extends training.

See [exact token layout](LAYOUT.md), `results/local/summary.json`, the full reports
in `results/local`, and the independently recorded CPU audit. These are bounded
fixed-size tests; they establish neither arbitrary-size graph generalization nor
a compression/speed advantage over direct GPU execution of the same rules.

## Final recorded results

Every panel below contains 2,048 complete three-Run traces per seed. The final
shared model includes offline local supervision; static input copying is not
counted as a learned ability.

| Panel | Old flat model: seeds 1703 / 1709 / 1721 | Shared + local supervision: all seeds |
| --- | --- | --- |
| Seen factors | 2048 / 2048 / 2048 | 2048 / 2048 |
| Held-out complete shape | 1 / 4 / 0 | 2048 / 2048 |
| Held-out union pair | 982 / 982 / 982 | 2048 / 2048 |
| Held-out composed map | 580 / 112 / 0 | 2048 / 2048 |
| All old held-out factors | 0 / 0 / 0 | 2048 / 2048 |
| Final unseen shapes, seen remaining factors | 0 / 0 / 0 | 2048 / 2048 |
| Final unseen shapes, held-out remaining factors | 0 / 0 / 0 | 2048 / 2048 |

The 16 final unseen shapes are different from both the original 10 shapes and the
16 inspected development shapes. The two final panels have 2,048 distinct cases
each, not 4,096 distinct graph topologies. All three predetermined seeds pass.

The original 1,066 enabled-union cases now have correct equality, and the 370
required transfers in the mapping holdout now have correct complete aliases, for
each seed. In final acceptance, the 398 and 404 required transfers are all correct,
with zero false or missed transfers. Every Run's structure, equality, certificate,
pending work and old-reference reads pass the unchanged source checker.

Nine unit/contract tests pass. The separate NumPy-only CPU audit reproduces
2,048/2,048 final-joint traces without importing MLX. Each model also matches all
256 binary local relation truth-table entries, all 56 primitive swap rows and all
8 insertion rows. This finite binary check is not a proof for every soft recurrent
state or an arbitrary egraph.

All generated-token recurrence checks are bitwise equal. Protected input lanes
are preserved exactly. Erasing only the preceding generated relation matrix
changes 20/128 probed transfer decisions while retaining the complete input plan.
Poisoning retired payloads with NaNs does not change reads. Disabling the learned
relation head leaves only 125/256 ablation cases valid; disabling the pointer head
leaves 205/256 valid. Non-triggered cases can still pass. Neither ablation invokes
a reference fallback.

The useful conclusion is bounded compositional execution with shared learned
local functions and explicit structural preservation. It is not discovery of new
rule semantics, fully implicit lossless latent compression, or evidence that a
neural executor is cheaper than direct GPU implementation of the same rules.

## Reproduce

Use the parent `requirements.txt` with Metal. Keep binary artifacts outside Git.
The original structural artifacts include the fixed inputs, positions and baseline
checkpoints; their hashes are recorded in every report. On the shared machine:

```sh
# Repeat with seeds 1709 and 1721 and distinct output directories.
~/.local/bin/eggfuse-job submit --kind compute -- env PYTHONDONTWRITEBYTECODE=1 \
  /path/to/venv/bin/python benchmarks/rotary-proof-cell/shared/experiment.py \
  /path/to/local-results/seed-1703 --seed 1703 --local-supervision \
  --old-root /path/to/rotary-proof-structure-20261117

# Omit --local-supervision to reproduce the end-to-end-only ablation.
# Independent audit requires NumPy only; it does not import MLX:
~/.local/bin/eggfuse-job submit --kind compute -- env PYTHONDONTWRITEBYTECODE=1 \
  /path/to/venv/bin/python benchmarks/rotary-proof-cell/shared/audit_saved.py \
  /path/to/local-results/seed-1703/final_joint-checkpoints.npz

~/.local/bin/eggfuse-job submit --kind compute -- env PYTHONDONTWRITEBYTECODE=1 \
  /path/to/venv/bin/python benchmarks/rotary-proof-cell/shared/inspect_heads.py \
  /path/to/local-results/seed-1703/model.safetensors

~/.local/bin/eggfuse-job submit --kind compute -- env PYTHONDONTWRITEBYTECODE=1 \
  /path/to/venv/bin/python benchmarks/rotary-proof-cell/shared/collect_results.py \
  /path/to/local-results /path/to/text-results
```

`test_shared.py`, `test_contract.py` and `test_local.py` are standalone test entry
points to run through the same queue. Semantic failures exit 1 and remain failures
in the reports. All seeds and both objectives are retained, including failed fits.
