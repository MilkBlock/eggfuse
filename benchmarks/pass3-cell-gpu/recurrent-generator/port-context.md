# Ablation of a visible port read in the recurrent root actor

The opt-in PyTorch actor reuses the existing two proposal rows, eight hidden coordinates, set loss, action logits and emitted token layout. An attention query from each proposal row reads the visible export keys and values, then adds its result to the existing row state. The read does not emit tokens. ExportMemory applies caller-provided boundary replacements and retirements and caches the frozen projections by stable identity, version and content. It sorts live identities and packs a dense view at snapshot construction. This packing and all attention scores cost work. No runtime speed measurement is made here.

The diagnostic uses the compiled two-parent join. Two possible parent pairs are wired in advance in every arm. Each training step draws fresh synthetic initial ports, including distractors. Each pair has a disjoint small scalar domain and each side independently agrees or disagrees. The input encodes the table and finite scalar category; all out-of-domain distractor keys share a category. Four label combinations occur equally often in the 256 test cases. These are held-out draws from the same finite interaction family. An output may choose either fixed pair or abstain. Receiver validation names the physical input addresses and their initial versions. This setup isolates contextual selection; it does not evaluate neural parent discovery or cross-stage closure.

Both arms use identical initial weights, batches, optimizer, objective and proposal budget for each seed. Blind removes the context read in training and inference. Wrong-context uses the trained contextual actor but replaces its visible ports with the next evaluation case, whose correct output set differs. The native check compiles each of the first 32 held-out initial states, executes the issued packets in the named-only receiver and compares to an isolated exact run. Metrics distinguish exact proposal sets from reference-aligned graphs after rejections. In particular, blind issues both pairs in every case and can achieve full graph parity despite overproposing.

Both training and evaluation used single-threaded PyTorch on CPU. The receiver and reference are native Rust CPU processes. Neither the base Metal ABI nor the production generator loads this experimental checkpoint. External checkpoints can be loaded into PortContextActor for PyTorch inference. The experiment feeds the fixture's observable initial exports. The cache unit check covers later updates and retirement; a native cross-stage producer of these updates remains outside this experiment.

```sh
D=benchmarks/pass3-cell-gpu/recurrent-generator
python "$D/check_port_context.py"
python "$D/port_context_study.py" "$COMPILER" "$NAMED_VERIFIER" "$EXACT_REFERENCE" "$OUT"
```

The frozen results are in `port-context-results.json`. Scores count actual context score elements on unpadded single-case CPU inference. They are distinct from generic root action scores. The two seeds reached exact proposal sets on 112 and 152 of 256 cases, versus 64 for blind. Context added 3,060 scores per seed. Native parity was 27 and 32 of 32 cases versus 32 for blind. No aggregate acceleration or autonomous completion claim follows.
