# Stage lifecycle sharing: reject as the main compression path

The last actual Unit-owning catalog produced reusable cross-stage fragments but
still retained source frames and facts. Before changing representation, this
experiment asks how much existing fact lifecycle state a scheduled transition
could share. It adds a post-execution snapshot, not a runtime fact graph or cache.

## Measurement

Actual standalone Cell runtime, sum-bits, four-frame learned catalog
`df49f0d486eff920d32aa2c78e39cdd40aadde342926ac37958e0ab5a03f5416`:

- 1,428 Runs; 3,734 live facts; 671 multi-frame owners with live facts.
- 2,644 distinct lifecycle cohorts within existing ownership groups.
- Sharing the two epoch fields could save at most 17,440 bytes (0.633% of the
  2,756,564-byte Graph), before cohort IDs, exceptions or mutation costs.
- Cross-frame grouping contributes only 1,792 of those bytes; do not add it again.
- 628 facts have an update epoch different from their birth epoch.
- 86 frames have mixed update epochs; none has mixed birth epochs.

These are final snapshot observations, not evidence that a Cell is saturated.
In particular, a single stage epoch cannot replace the per-fact update epochs of
those 86 frames without exceptions. Source inspection confirms that stable-port
publication, canonical repair and hide/collision handling update individual facts.
A whole-owner clock would incorrectly make unaffected facts appear newly changed.

The analyzer groups by update epoch, birth epoch, hidden state and both ownership
flags. It neither drops Entry witnesses nor assumes hashes/identities are equal.
Frames without an ownership group remain independent. Incomplete frames are
counted separately from completed opportunities. Tests cover visibility/birth
splits and prevent merging unrelated frames or double-counting cross-frame credit.

## Checks and reproduction

The runtime example compiles; three analyzer tests pass. Compared with the saved
same-catalog run, program digest, Run count, final-state digest, Graph heap and
retained Program heap are identical. This change only observes state after
execution. It does not newly admit the four-frame catalog's scheduling semantics
or claim a speedup. The existing full-Run caveat in `unit-facts.md` still applies.

```
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo build \
  -p eggfuse-cell-compiler --example runtime_storage_peak \
  --features iterative-bake,sparse-cells,storage-metrics

target/debug/examples/runtime_storage_peak \
  out/cell-structural-compression/unit-owned-bake/frames4/program.json \
  out/cell-structural-compression/stage-lifecycle-heap.json \
  inherited-owners --port-domains-only

python3 benchmarks/cell-structural-compression/analyze_stage_lifecycle.py \
  out/cell-structural-compression/stage-lifecycle-heap.json \
  benchmarks/cell-structural-compression/stage-lifecycle-results.json
python3 -m unittest discover -s benchmarks/cell-structural-compression \
  -p test_stage_lifecycle.py
```

## Decision

Do not implement lifecycle-cohort packing as the structural compression solution.
Even its uncharged upper bound is small. A useful stage representation must instead
replace the independent materialization and indexing of internal facts using a
proved Cell layout. It must still expose distinct fact identities, exact delta
visibility, union-enabled matches, and any external Entry witnesses. The current
trace now makes lifecycle exceptions visible for evaluating that larger change.
