# What the current Cell candidate search can establish

These are saved short sum-bits executions of the standalone Cell CPU runtime
at `15de6b94`, not native egglog and not throughput measurements. This extends
the [one-candidate check](../cell-history-admission/README.md) to the remaining
ranked candidates and then resumes the shipped catalog. No runtime code changes
or new workload executions are needed to collect the report.

The subsequent [independent-runtime check](../cell-completion-portability/README.md)
found and fixed a JSON-order-dependent type identity in completion artifacts.
These trials executed the runtime inside the compiler process. Their work
counts do not by themselves prove that the exported proof is portable to a
separately built runtime, or measure conversion from the shipped v1 program.

## Results and limits

| Starting catalog and backend | Executable trials | Equal-weight work scores | Outcome |
|---|---:|---|---|
| 32 base Cells, stable ports/local congruence | 4 | +2768, +2852, +2674, +2400 | 34 Cells selected |
| Resume those 34 Cells, same backend | 2 | -94, -333 | No candidate admitted |
| 32 base Cells, canonical keys/Entry publication | 4 | -2441, -2467, -2793, -2881 | No candidate admitted |
| Resume shipped 64 Cells, canonical, capacity 96 | **0** | **Not measured** | No changed executable candidate |

These scores add unlike work counters with equal weights. They are neither
elapsed time nor a reliable latency model. For example, the first candidate
removes 370 key lookups in both backends, but adds 369 history-owner allocations,
369 joint frames, 311 query captures and 428 witness checks. Stable-port root
and field traversal savings dominate its positive score there; the canonical
backend lacks those same savings. This is evidence that reuse has maintenance
cost, not that the egraph has many essential dependencies.

The best stable-port candidate contains two joins, including an already
observed route added by structural expansion. Its 34-Cell result must not be
described as a newly discovered equivalence between unrelated derivations.
The resumed experiment uses that exact selected artifact. All recorded graph,
schedule and ordered RHS/write/resume audits agree. These audits do not replace
the separate native sum-bits choice acceptance entrypoint.

The last row is particularly important: `iterate` reports `no_measured_gain`
even when its sole structural-expansion proposal produces no new joins and no
trial is replayed. This is **search exhaustion within current selection/proof
limits**, not a measured rejection of all possible Cell compositions. Increasing
the total capacity to 96 did not change those limits (depth 4, nodes 8).

Its saved local history contains 110 distinct contracts, 85 of which retain
`opaque-source-contract` normalization. The compiler cannot compare those by
normalized constructor structure. This is a statement about supported proof
coverage, not a density measurement. The bounded event trace also drops 380
events; neither these contracts nor the trace are a census of the whole graph.

Two additional comparison boundaries matter:

- Without `--resume-catalog`, `iterate` starts from base Cells, even when its
  input program already embeds 32 joins. The earlier isolated-candidate checks
  therefore did not measure expansion beyond the shipped 64-Cell catalog.
- The objective is compiled before the initial reference replay. The resumed
  result does not measure the cost of changing the shipped v1 result switch
  into the ripsat-completion objective. The original shipped program must be
  retained as a separate control for an eventual end-to-end comparison.

## What to investigate next

Do not use "more Cells" or a positive work score as the target. Use the last
catalog's actual applications to distinguish these questions:

1. Which repeated constructor queries or output deliveries are already implied
   by completed typed operations, and which still require external evidence?
2. For those repetitions, is the compiler missing a valid proof (including
   ordered pre/post-Union state), or is a proof present but expensive to carry?
3. Can a scheduled Cell switch delete the lookup **and** its intermediate
   history/publication work, while retaining only live boundary checks?

A sparse dependency graph can still cross every chosen Cell boundary. A small
local dependency set can also be expensive to discover or maintain. Conversely,
failure to find reusable work is not a proof of a dense graph. Determine the
cost of necessary boundary work relative to work actually removed before
expanding a composition. Actual returned witnesses, delta ownership, retirement,
source Run visibility and ordered effects remain live obligations. Do not
identify post-Union facts with pre-Union assumptions to increase coverage.

The next decision should come from a bounded audit of an observed hot path:
necessary reads versus repeat reads, the portion proved by the current template,
and the unproved boundary. Use saved history first. If necessary external reads
dominate, change the partition or optimization target; if already-proved reads
and transfers dominate, simplify execution. Neither branch presupposes sparsity
or promises a 2x speedup.

## Reproduction

Use the same prepared seed described in cell-history-admission and the README
compiled program retained by cell-execution-state. Generated programs are not
tracked. These commands reproduce the executions; they are not timing commands:

```sh
cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells -- iterate --program out/terminal-union-seed.json --output out/cell-candidate-sweep/full-round --objective ripsat-completion --score measured-work --rounds 1 --trial-limit 8 --local-congruence true
cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells -- iterate --program out/cell-candidate-sweep/full-round/program.json --resume-catalog out/cell-candidate-sweep/full-round/round-1/catalog.json --output out/cell-candidate-sweep/continued --objective ripsat-completion --score measured-work --rounds 4 --trial-limit 8 --local-congruence true
cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells -- iterate --program out/terminal-union-seed.json --output out/cell-candidate-sweep/canonical --objective ripsat-completion --score measured-work --rounds 1 --trial-limit 8 --repair-ports true --entry-publications true
python3 - <<'PY'
import json
from pathlib import Path
p = json.loads(Path('out/cell-execution-state/readme-program/program.json').read_text())
Path('out/cell-candidate-sweep/shipped-catalog.json').write_text(json.dumps(p['iterative_bake']))
PY
cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells -- iterate --program out/cell-execution-state/readme-program/program.json --resume-catalog out/cell-candidate-sweep/shipped-catalog.json --output out/cell-candidate-sweep/shipped-resume --objective ripsat-completion --score measured-work --rounds 2 --trial-limit 8 --max-units 96 --repair-ports true --entry-publications true
python3 benchmarks/cell-candidate-sweep/collect.py out/cell-candidate-sweep benchmarks/cell-candidate-sweep/results.json
```

The collector retains exact input/history/report hashes, selected work deltas,
all trial scores and trace coverage. It checks continuation identity and the
recorded execution digests, and launches no compiler, runtime or benchmark.
