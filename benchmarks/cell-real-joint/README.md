# Joint real-valued encoder, transition and decoder

Standalone finite-teacher experiment; no GPU, native runtime takeover or speed claim.
Imports the unchanged `cell-real-state/study.py` teacher and structural split.
Only variable observables are initial inputs. Their 32-dimensional dense signed
real code is jointly learned with a 128-unit tanh transition and linear-logit
decoder. Events use fixed dense 16-dimensional random codes. The decoder is
used for loss and reporting, never fed back into execution. No nearest-state
lookup, symbolic repair or intermediate true encoding is used.

Reproduce with the existing NumPy environment:

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=2 out/cell-real-state/venv/bin/python benchmarks/cell-real-joint/study.py --output out/cell-real-joint/new --iterations 8000
```

The model has 12,902 trained scalar parameters (fixed event codes additional).
Encoder, transition and decoder all receive gradients through three autonomous
steps. Loss includes reconstruction and each predicted step's observable binary
cross entropy. All 8,192 training sequences stay strictly inside training states.
The initial budget was 3,000 steps; training-edge accuracy was only 71.7% and
validation continued improving, motivating a fixed 8,000-step extension.
Checkpoints every 500 steps are selected by validation whole-trace correctness,
then single-step correctness and reconstruction. Held-out test scores never
select a checkpoint. The extended run selected step 8,000.

Results: training-edge accuracy 86.38%; held-out initial reconstruction 99.36%;
held-out single-step complete-state accuracy 63.88% (real changes 57.24%, no-ops
81.75%). Whole 12-step traces are correct in 51/624 cases (8.17%). A second event
seed gives 46/624 (7.37%). Quantizing weights to FP16 while retaining FP32
arithmetic gives the same 51/624 on the original seed. This last check does not
quantize every activation and is not a Metal hardware validation.

These results improve whole-trace behavior over this predecessor study's fixed
PCA/random-feature nonlinear models, but remain far below correctness needed
for execution. Training is still imperfect, and rollout drift remains. Initial
reconstruction has also lost one held-out state versus the fixed PCA decoder;
joint training is not automatically a universal improvement.

`Model.load(path, half=False)` loads the generated NPZ. `encode(full_facts)`,
`step(latents, integer_event_ids)`, and `decode(latents)` expose autonomous
execution for independent evaluation. `evaluate` accepts any event seed.
Generated model arrays stay under ignored `out/`; committed results bind source
and teacher hashes. Timings in the JSON are research-run wall time, not inference
performance. No code outside this experiment was changed.
