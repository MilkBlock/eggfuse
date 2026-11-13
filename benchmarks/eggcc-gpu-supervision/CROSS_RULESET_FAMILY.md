# Actual cross-ruleset Cell continuation

The GPU family runner now accepts an explicit original-control subtree, selected
rules and an audited source Run snapshot. This extends the previous one-ruleset
family without pretending that two pieces of the same ruleset are two stages.

## Real source and preserved scope

The training workload is `024-pascals-row`. Its final snapshot has lost temporary
TermSubst facts, so reconstructing visibility from RHS history was inappropriate.
The existing CPU RHS observer now accepts `--snapshot-runs=438,456`. It stores only
those actual exported boundaries, reusing the graph already compared with an
unobserved reference at each Run. Default snapshot storage remains empty.

`run-snapshot-capture.json` verifies all 631 Run graph comparisons and preserves
the old capture's recipe, final graph and Run control/effect-count sequence. The
reference execution took about 0.085 seconds. These are standalone Cell runtime
observer checks, not a native egglog equivalence claim or performance campaign.
The working tree's unrelated kernel edits were not modified or committed here.

At Run 438, the visible snapshot has a TermSubst whose expression is an existing
Concat. The selected original rules are:

- 488, type-analysis: `Concat(a,b) -> lhs` and `HasArgType(a,ty)` establish
  `HasArgType(lhs,ty)`.
- 452, term-subst: `TermSubst(ctx,e,term) -> lhs` and `HasArgType(e,ty)` establish
  `HasArgType(lhs,ty)`.

The JSON family specification withholds the HasArgType row for the TermSubst's
input/output expression, using typed relations in the snapshot rather than fixed
instance IDs. One existing row is removed. Other facts remain available.

The schedule comes from the actual repeat body's control subtree at
`[1,"sequence",1,"body","sequence",1,"body"]`. Projection preserves order and
nested saturation, omitting unselected stages. This is **not** a resume of the
entire original schedule: omitted rules, type helpers, union stages and other
effects are outside the coverage contract. The initial state is an explicitly
modified exported snapshot, not original program initialization.

## GPU execution and CPU acceptance

| Item | Result |
|---|---:|
| Imported seed facts | 98 |
| New Cell instances | 26 |
| New constructor facts / IDs | 2 |
| Final logical Cell instances | 124 |
| Final constructor facts | 100 |
| Physically released owner rows | 47 |
| Transfers rejected by existing guards | 4 |
| Pending Cells / failed Run | 0 / false |

Actual completed Runs are:

```
type-analysis:  1 new fact, 25 new Cell instances
type-analysis:  0 new facts, 0 new Cell instances
term-subst:     1 new fact, 1 new Cell instance
term-subst:     0 new facts, 0 new Cell instances
```

The second stage consumes the first stage's generated Cell. There are no
intermediate device-state readbacks. The same source token/owner interfaces and
transfer guards remain active. Rejected transfers retain valid old storage;
they are not ignored repair failures or claimed storage savings.

The independent CPU interpreter now understands sequence, nested saturation and
repeat. Each Run matches all of its selected rules on one frozen snapshot before
executing any effects. Acceptance checks exact constructor closure, identity
sharing, fresh-ID explanations, per-Run fact counts and the stage sequence.
A regression reverses producer/consumer stages and confirms the consumer does
not execute early. Original four-rule type-analysis behavior still gives
`[3,2,2,0]` new facts and nine released owner rows.

## Real inputs and labels, without accuracy inflation

The capture contains 26 accepted samples, one consuming a generated Cell from a
prior stage, and 52 observed matches including duplicates in fixed-point Runs.
Source row/port/generation and physical ownership evidence pass CPU checks.
There are 18 relocated witness observations, not 18 additional transfers.

Capture schema v2 additionally stores CPU-derived `target_eq_classes` alongside
floating targets. Unused slots are -1. This supports exact Eq readout auditing
without reconstructing truth from the model's own output. Existing scalar-target
coverage is not extended here: this family has Eq slots only.

The frozen decoder reads all 26 predicted-token partitions correctly, as it does
for the CPU target tokens. However, the 102 dynamic quotient queries have **zero
positive equalities**, and there are only two distinct rule partitions. Therefore
this is not a 100% general accuracy result or evidence of a new learned Eq
capability. No fitting, backpropagation or model replacement occurred.

This negative-label concentration changes the next collection priority: actual
union-enabled continuation and nontrivial positive Eq targets, plus additional
families and workloads. Full Eggcc ruleset/primitive/mutable coverage is still
missing. Exact GPU completion currently establishes facts and refreshes completed
tokens; ridge alone has not established semantic completion or fast execution.

## Costs and checks

The final cached run took about 1.02 seconds including GPU compilation/upload;
a prior cold compilation took about 8 seconds. Neither is a throughput claim.
CPU closure checking took about 0.012 seconds and capture audit/preparation about
0.018 seconds, excluding archive compression/writes. CPU readout audit timing is
reported separately. About 25.4 MB of padded logical capture arrays remain during
the fixed launch budget; exported arrays total about 1.26 MB before compression.
These are summed array sizes, not peak RSS or distinct allocator bytes.

Validation: Cargo build and the example's snapshot-selector test pass; 23 Python
tests cover source projection, typed withholding, frozen-Run ordering, label
consistency, query lifecycle and ownership. Both the new cross-ruleset example
and the existing four-rule family pass their independent CPU checks. No native
sum-bits proof rules or exclusions were changed. Latest reviewed Bake remains
81188496; observation keeps actual takeover behavior enabled.

## Reproduction

```
cargo build --locked --no-default-features -p eggfuse-cell-runtime --example capture_rhs_results
cargo test --locked --no-default-features -p eggfuse-cell-runtime --example capture_rhs_results
capture_rhs_results PROGRAM.json BOUNDARIES.json --snapshot-runs=438,456
```

From `benchmarks/eggcc-gpu-supervision`, with the experiment Python environment:

```
python audit_type_family.py BOUNDARIES.json MODEL.npz RESULT.json --family concat-term-subst-family.json --ticks 48 --capture CAPTURE.npz --corpus-manifest CORPUS_MANIFEST.json
python audit_device_match_readout.py CAPTURE.npz DECODER.npz DECODER_REPORT.json READOUT.json
python -m unittest test_cell_family_plan test_device_match_readout test_reference_cell_closure test_device_schedule test_device_scheduled_runtime test_device_match_capture test_device_matched_takeover
```

Raw boundaries and binary captures remain on the external drive under
`/Volumes/Extreme SSD/eggfuse-artifacts/21ee/`. Text reports contain source,
configuration, model, decoder and capture hashes. Native capture uses the
standalone CPU runtime only to establish input snapshots and reference labels;
the selected family's matching, completion and transfer execute on GPU.
