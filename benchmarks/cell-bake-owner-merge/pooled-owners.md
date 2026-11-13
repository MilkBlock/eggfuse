# Bounded physical owners preserve source restoration

The singleton audit exposed duplicated array-owner headers after more facts began
inheriting their source state. This change shares backing arrays among a bounded
set of eligible new singleton sources while retaining every source's independent
metadata, slot/fact ranges and logical identity. It does not infer equality or
saturation from physical sharing and does not create a nested executable Cell.

Packing admits at most 16 singleton sources per new group and uses a 4,096-byte
estimated payload threshold. The estimate excludes allocator overhead and owned
Value payloads; an individually large source is retained as its own group. This
is not a hard bound on all owner allocations or a promise that every future
source restoration is small. Existing composed groups keep their original policy.

If a logical component subsequently grows while its physical owner also contains
unrelated sources, flattening is refused. The existing segment-extension path
then moves only the new suffix. Sibling frames retain their original backing
allocation. Source-sized unsealing and all current liveness/epoch checks remain.
The shared template wiring, source Run boundaries and actual returned results
remain authoritative; no new producer subscription or binding copy is introduced.

## Accounted result

Both modes use one frozen runtime binary and identical installed catalogs,
with port domains enabled. `unpooled-owner-control` retains singleton admission
but disables packing. `inherited-owners` enables it. Program bytes and final
states are identical between the modes.

| case | Graph bytes before | after | reduction | old fact entries moved before → after |
| --- | ---: | ---: | ---: | --- |
| fact | 667,423 | 658,935 | 1.27% | 530 → 3 |
| loopfact | 602,681 | 585,105 | 2.92% | 449 → 4 |
| sum-bits | 1,796,683 | 1,773,131 | 1.31% | 2,017 → 34 |
| dot-product | 1,746,507 | 1,720,731 | 1.48% | 2,399 → 17 |

Source frame and fact identities are not eliminated. Physical owner counts fall
492→292, 464→246, 1,344→907 and 1,308→850. Fewer headers and suffix-only growth
supply the saving. The recorded movement counts are actual copies of existing
entries, not avoided RHS computations. No speed or repair-stall improvement is
claimed from these counts.

Restoration event/container totals are unchanged across all four cases. However,
packing retains more dead array ranges: sum-bits retired slot entries increase
121→430 and retired fact entries 230→446. Full Graph accounting includes that
cost. Execution peaks still decrease in the final implementation by approximately
8.5/17.6/23.7/25.8 KB respectively. Dot-product's maximum *temporary takeover*
allocation increases by 80 bytes even though its whole execution peak decreases.
Do not sum snapshot counts with cumulative movement or restoration bytes.

The first implementation kept both the original group Vec and its packed
replacement alive during collection. Its same-binary results are preserved in
`pooled-first-results.json`: sum-bits and dot-product temporary takeover peaks
rose by about 49 KB. Single-pass collection removes that second container;
`pooled-results.json` measures the final implementation. The earlier data is
not used to claim peak improvement.

This extends the optional completed-owner path. It does not enable that path in
all ordinary parallel runs, create a saturation certificate, or reach the goal
of a runtime egraph at 30% of original size.

## Validation

All 55 ownership tests pass. Nine fact-state tests pass, including a new partial
physical-owner test: a source grows through an existing segment while an unrelated
sibling's fact-array address stays unchanged, and restoring/retiring one source
does not remove the others. The final candidate is replayed against saved graph,
RHS and write checks at all 2,652 source Runs plus four terminal checks. These are
standalone Cell differential checks, not a new native egglog acceptance result.

Research examples compile with
`iterative-bake,sparse-cells,storage-metrics,eggfuse-cell-runtime/slot-transfer-audit`.
The changed runtime modules are storage-metrics gated; default-path README smoke
commands were already checked in the immediately preceding singleton commit.
No additional timing campaign is part of this experiment.

For reproduction, copy unchanged seed candidate/selection inputs to the
`pooled-audit` variant, then use:

```sh
target/debug/examples/batch_cell_learning check-passive out/cell-bake-owner-merge/batch pooled-audit
```

Run one frozen `runtime_storage_peak` binary on each seed candidate with
`unpooled-owner-control --port-domains-only` and
`inherited-owners --port-domains-only`, writing `CASE-unpooled.json` and
`CASE-pooled.json` under `out/cell-pooled-owners-final`. Record its SHA-256 in
`binary.json`; then:

```sh
python3 benchmarks/cell-bake-owner-merge/singleton_results.py out/cell-pooled-owners-final out/cell-bake-owner-merge/batch benchmarks/cell-bake-owner-merge/pooled-results.json pooled
```

`two-pass-pooling.patch` reconstructs the earlier duplicate-container strategy
on top of this implementation for reproducing its rejected peak behavior; it
passes `git apply --check` and is not applied to the final runtime.

## Newly completed short compositions

The original-workload composition experiment found a storage penalty when
singletons became short logical compositions. The initial policy above admitted
only singletons into shared physical batches. New two/three-frame components
allocated independent arrays even if all their sources satisfied the same
transfer contract. Pooling now admits newly completed components of up to 16
sources into the same bounded batches. A batch still has at most 16 sources and
uses the same 4,096-byte estimated threshold; an individually oversized component
remains a separate batch. Existing transferred prefixes follow the original
extension path and are not copied into these batches.

Static component wiring, source IDs, fact identities, per-source layouts and
restoration slices remain authoritative. The new regression constructs several
composed components, requires fewer physical owners than multi-frame components,
then performs union, deletion and regeneration. Every Run's exports, snapshots
and binding audit agree with the unpooled control. All 67 ownership tests pass
(jobs 295–296).

Actual standalone runtime measurements use the unchanged round-one and round-two
Programs from `original-composition.md`, with the same completed-owner,
port-domain and Cell-field configuration:

| Catalog | Graph before | Graph after | Saving |
| --- | ---: | ---: | ---: |
| Round one | 1,952,405 | 1,941,209 | 11,196 |
| Round two | 1,949,501 | 1,949,485 | 16 |

Both run 1,428 Runs. Final exports are byte-identical to the prior candidates;
logical ownership structure and ownership-query counters are unchanged. This
does not repeat a full-workload per-Run proof. The round-two maximum temporary
takeover allocation rises from 15,732 to 16,580 bytes; whole-process high-water
does not rise. The report includes that cost rather than treating final heap as
a peak measurement. See `composed-slabs.json` for exact hashes and charges.

The negligible round-two saving rules out new short-component batching as the
main remaining compression mechanism. Deeper completion predominantly extends
already-transferred prefixes, which this change deliberately leaves intact.
Further work must examine suffix ownership and retained source state, not keep
tuning this batch threshold. No timing or large-compression claim is made, and
the 30% Graph target remains unmet.
