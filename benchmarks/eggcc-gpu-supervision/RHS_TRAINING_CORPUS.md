# Real multi-entry training evidence

`collect_rhs_training.py` extends actual RHS capture and input linking to the
existing **training** partition. It never reassigns a validation/test workload.
Selection is deterministic: smallest observed binding counts among complete
training cases under the configured binding limit, with case name as tie-break.
The original saved reference execution must be at most one second. Neither
model accuracy nor observed successor counts enter selection.

The collector verifies original trace hashes and recipe identity, captures a
fresh actual RHS trace with per-Run and final reference graph equality, then
links output identities to later successful inputs. Each case stores original
program identity, trace/link hashes, CPU capture coverage and link counts.
Missing reads remain missing. Timeouts and failures remain explicit; they are
not successful captures. Fresh output directories prevent stale artifact reuse.

```sh
python3 benchmarks/eggcc-gpu-supervision/collect_rhs_training.py \
  "$ROOT/observed-corpus-20261113/manifest.json" \
  target/debug/examples/capture_rhs_results \
  "$ROOT/rhs-training-20261114" --max-cases 3 --max-bindings 2000
```

Here ROOT is `/Volumes/Extreme SSD/eggfuse-artifacts/21ee`. Raw programs, traces
and links remain on the external drive. The committed `rhs-training-results.json`
contains hashes, per-case coverage, timings and aggregate counts. The capture
binary fingerprint is retained; this uses the default debug runtime build.

## Results

All three selected cases completed and passed their reference graph audits:

| Training workload | Actual RHS applications | Linked consumers | Cross-ruleset consumers | Multiple providers needed |
|---|---:|---:|---:|---:|
| fitsinside | 1,031 | 567 | 119 | 240 |
| loopfact | 1,239 | 776 | 103 | 321 |
| recfact | 1,487 | 984 | 70 | 443 |
| Total | 3,757 | 2,327 | 292 | 1,004 |

The eligible producer windows provide 5,252 captured constructor results, all
available. There are 4,774 linked consumer Eq slots among 15,611 examined slots;
4,677 have an identical captured provider identity, and 97 only share a typed
root. Of the 2,327 linked consumers, 1,840 still require external Eq inputs and
487 have no external Eq classes relative to the provider groups. This does not
make the latter fully executable: scalar inputs, query predicates, lifetime,
visibility and effect order remain obligations.

Observed CPU execution including capture was 0.142 / 0.147 / 0.167 seconds;
reference execution was 0.039 / 0.045 / 0.049 seconds. Per-Run full graph exports
and equality checks added 5.664 / 6.416 / 6.339 seconds. These diagnostic costs
are reported separately, not used as performance evidence. No native egglog
semantic acceptance or GPU speedup is claimed.

The result establishes that real multi-provider and cross-ruleset input
structure also exists in the training partition. It does not prove unique
producer ownership or that a provider caused a consumer match. No ridge fit,
neural training or GPU inference occurred in this collection. Dot-product
remains in the test partition and is absent from fitting data.

The next model experiment should consume several producer states plus the
explicit external interface, and evaluate a changed consumer request. Training
must not use future consumer observations as if they were already available
producer features. Replay using gold producer states and replay using predicted
producer states must be reported separately; the latter is the needed closed
loop test. Existing native capture supplies labels and audit evidence, not the
intended final execution path.

Validation: deterministic selection tests exclude test/validation, failed and
over-budget cases and check input-order invariance. The related Python suite
passes 71 tests. Runtime execution was unchanged in this commit.
