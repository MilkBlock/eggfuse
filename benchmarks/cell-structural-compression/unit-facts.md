# Unit facts expose cross-stage closure edges, but do not compress instances yet

This measures the actual standalone Cell runtime on the saved sum-bits input,
not native egglog. All modes remain opt-in. The accepted baseline is unchanged.

## Opportunity and typed obligations

The old catalog kept Unit membership in function storage. These memberships can
be consumer Entries connecting stages, so a subsequent Bake iteration should
learn from their actual executions. The compiler now lowers eligible Unit,
merge-old tables to ordinary virtual facts, then recompiles the typed core.
It rejects initial membership, deletion, RHS reads, merge-expression reads and
non-Unit writes. A separate checker rederives the transformation from source.
The ownership experiment covers scalar-key Unit facts using existing shared
ports; it does not introduce another fact graph. Unit results are not Eq signals.

Migration maps an old Entry through its query atom, rather than copying its
ordinal: adding Unit coverage changes Entry numbering. Original Run boundaries,
residual enumeration, logical effect order, visibility and union-enabled matches
remain live obligations. Unit canonical-key boundary maintenance still exists.

## Saved execution evidence

| Configuration | Graph requested heap bytes | Change from accepted baseline |
|---|---:|---:|
| Accepted baseline | 2,617,317 | 0 |
| Generic Unit facts | 2,641,476 | +24,159 |
| Unit ownership, mapped Entries | 2,833,236 | +215,919 |
| Unit ownership, next Bake, four-frame limit | 2,756,564 | +139,247 |

Graph teardown allocation accounting is not RSS or a whole-process peak.
`unit-facts-results.json` also charges retained Program memory and execution peaks.
Generic conversion replaces function rows with Cell storage. Ownership adds
shared-port and component maintenance. Source cells created increase from 2,893
to 3,259; sharing symbols does not remove those instances.

One actual execution of the Unit-owning catalog yielded 1,787 fragment records,
298 containing a Unit Entry. Offline selection produced candidates with 4, 8 and
16 frame limits from that same trace. Eight and sixteen selected the same counts;
neither was executed. Candidate credits overlap and must not be summed as saved
work. The measured four-frame candidate saves 76,672 bytes against the new Unit
ownership representation, but still loses to the accepted baseline.

Generic and mapped-ownership candidates pass all 1,428 Run comparisons for graph,
RHS and ordered logical writes, with unchanged resume histories. Physical write
hashes differ in 265 Runs because virtual membership has no function-array index;
the original physical audit remains intact and the saved baseline hashes still
match. The new parallel audit includes virtual Unit insertions and excludes only
physical addresses. A negative test detects reordered writes even with equal
final graphs. Saved final states exactly equal the reviewed legacy export; the
existing semantic entrypoint returns pass (`unit-facts-semantic.json`). The learned
four-frame candidate has final-state equality only, not full Run admission.

Validation: seven specialization tests, three existing Entry specialization tests,
three matched-handoff tests, 154 runtime library tests, and example compilation.

## Reproduction

Use the local Cargo setup in README with `CARGO_INCREMENTAL=0` and the local target
directory. Examples declare their required feature sets in `tools/cell-compiler/Cargo.toml`.
The example interfaces are:

```
relower_entry_values SOURCE OUTPUT --unit-facts
relower_entry_values SOURCE OUTPUT --unit-ownership
train_unit_closures UNIT_OWNED_PROGRAM OUTPUT_DIRECTORY
bake_unit_closures UNIT_OWNED_PROGRAM PROFILE OUTPUT_DIRECTORY
```

Produce Run audits with `audit_matched_handoffs` and allocation reports with the
existing `runtime_storage_peak` harness. Summarize saved reports without rerunning:

```
python3 benchmarks/cell-structural-compression/summarize_unit_facts.py \
  out/cell-structural-compression \
  benchmarks/cell-structural-compression/unit-facts-results.json
```

## Structural next step

`Cells::transfer_completed` consolidates arrays but retains a `Frame` and original
`Metadata` for every source instance, plus its fact records and slot range. It does
not turn the component into a replacement executable Cell. The next takeover must
make proven membership/publication positions part of a composed layout, preserve
externally observable fact identities and stage activation, and retire covered
source storage. An owner merge alone is not that takeover. Do not enable these
experiments by default or claim the 30% memory target has been met.
