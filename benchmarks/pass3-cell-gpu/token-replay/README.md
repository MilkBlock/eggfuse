# Native Cell certificate replay

This experiment runs the Rust Cell runtime in three fresh processes. The reference runs ordinary matching. Capture records each committed RHS binding and its ordered table witnesses. Exclusive replay checks only the named token/operation and observed version, evaluates the primitive guards, restores the ordered native RHS bindings and executes the ordinary effects and completion. It has no model or residual binding search. Input handles are scoped to one compiled program; the tape binds its program digest. The deterministic commit order is the source rule order and the ordinary sorted input keys within each rule.

A table witness can originate in the input, an earlier signed RHS, or native repair. The first two address components are the token and the original result instruction position. Nested Set-merge instructions have a static PC block after the original effects. Native repair issues a separate event for a collision producing addressable constructor results. The event records the merge table (the compiled merge template), ordered old/new parent references and observed versions, returned PCs and first visible Run. The parents are historical receipts for the colliding rows. Later consumers must pass a fresh type, binding, visibility, version and delta check. The receiver recreates the events from native execution. A recorded event cannot authorize a graph write. The event registration timer is separate from the whole native repair phase; it measures registering the event, not the full cost of collecting both inputs.

## Reproduce

```sh
cargo cell-compile --case sum-bits --output /tmp/token-sum
cargo cell-compile --source benchmarks/pass3-cell-gpu/token-replay/recursive-parents.egg --output /tmp/token-parents
cargo build --release --locked -p eggfuse-cell-runtime --features cell-token-replay,slot-transfer-audit --example cell_token_replay
bin=target/release/examples/cell_token_replay
dir=benchmarks/pass3-cell-gpu/token-replay
python3 "$dir/study.py" "$bin" /tmp/token-sum/program.json --output /tmp/sum-oracle.json
python3 "$dir/check_refs.py" "$bin" /tmp/token-parents/program.json
python3 "$dir/check_event.py" "$bin" /tmp/token-sum/program.json
```

### Controls and results

[The five oracle records](oracle-results.json) compare the ordered schedule, per-Run RHS, effective writes, resumes, event audit and final strict state hash to native reference. Times cover in-memory execution, exclude offline capture, JSON decoding and final export, and include verification and graph maintenance. Four alternating pairs per workload are recorded. [The delta diagnostic](../recurrent-generator/delta-coverage.json) separately measures the reachable anchor and lane ceilings of the old Actor.

On sum-bits, omitting runtime-owned results first prevented Run 818 from naming a constructor returned by the merge in Run 816. The fixed replay accepted all 7,265 committed requests across 1,428 source Runs, including two reads of that event. The reviewed sum-bits choice diagnosis also passed on this replay's exported state against the saved native references. On dot-product, replay accepted all 6,704 requests across 1,535 Runs, with 18 reads of eight events. These results establish certificate expressibility on these inputs. All proposals came from the offline teacher. Unknown learned-model coverage, saturation and EPT cannot be inferred from replay.
