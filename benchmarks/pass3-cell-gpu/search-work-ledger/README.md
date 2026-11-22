# Native independent-parent search audit

The experiment instruments the Rust Cell runtime used by the historical joint-witness harness. It measures concrete parent inspections on that CPU path. It does not measure GPU execution or end-to-end speed. Build and run in the EggFuse experiment environment with the same joint-native-full bundle for every arm.

```sh
D=benchmarks/pass3-cell-gpu/search-work-ledger
python "$D/build.py" "$OUT"
python "$D/train_pages.py" "$OUT/model.json" --device cpu --seed 1703
python "$D/study.py" "$OUT/session" "$BUNDLE" "$OUT/sum-bits.json" --model "$OUT/model.json"
python "$D/historical_gate.py" "$OUT" --arm learned-4
```

The committed model came from generated random equality joins and synthetic epoch/freshness examples. Real workloads were used for evaluation. The Apple GPU compiler failed in the training environment, so this checkpoint is CPU-trained. Page selection ranks fixed eight-row pages. The secondary ranker reads membership and distinct-count summaries. Joint routing also ranks root pages. Each selected page can still require multiple row inspections per prefix. Budgeting pages does not bound the number of prefixes or the cost of scoring all headers.

The discovery total includes proposer traversal, shortlist row inspections, receiver-side enumeration, exact fallback traversal and concrete index filtering. Repeated visits count each time. Direct named parent checks, point reads, primitive checks, index builds, header scores and direct sibling probes are recorded separately. The counters measure operations with different costs. They do not measure elapsed time. The relocation arm moves the whole single-parent scan into the receiver and must preserve the discovery charge. The empty arm with residual search must retain source semantics while scoring zero provider wins.

For each arm the harness compares ordered per-Run RHS digests, schedules, writes, resumes, union trace and final state hash against native exact execution. Provider coverage uses unique committed RHS ordinals. FEPT credits visible constructor references whose observed birth belongs to a winning ordinal, divided by paid single, multi and child proposals. It excludes initial facts, retired constructors and births without a credited source ordinal. It is not a count of e-classes. Site-level counters are reconciled with the global totals. Unassisted alignment is a separate replay. The sum-bits choice diagnosis was run on the saved reviewed exports, independently of these native runtime checks.

`four-page-results.json` is the six-case gate applied to four available workload reports for the same frozen policy. At least 98 percent of source RHS must be supplied and at most one fiftieth of native discovery visits may remain on each workload. Failed cases exit 1. Incomplete evidence without a known failure exits 2. `control-results.json` includes the matched residual-enabled ownership controls. Four-workload results predate the direct sibling arm and the stronger individual endpoint-birth comparison, which was rerun on the sum-bits controls.

On sum-bits this grammar needs 7,120 distinct RHS ordinals. Giving all 2,677 single wins free leaves at least 4,443 multi wins. In the enumerating grammar each successful last independent extension supplies at most one such ordinal. With only 995 visits available, at least 3,448 ordinals need another mechanism even with free roots and perfect ranking. This bound assumes the current plan partition and does not apply to a directly addressed parent or a block that proves multiple distinct RHS.

The ownership experiment compiles sibling operation projections from template wiring and addresses the second parent through the first parent's physical owner. This produces a candidate with a real live version. Ordinary checks and residual enumeration retain responsibility for aliases, remote results and alternative matches. Against the matched assisted arm it saved 95,345 discovery visits, incurred 12,452 direct probes and lost 206 provider winners. Its unassisted trace diverged. A larger block would need independent imports and externally consumed exports, plus credit for the actual distinct RHS it supplies. These routing results cannot be added to results from the separate block-verifier executable.
