# Completed singleton facts inherit source state

The previous snapshot audit found 420/388/916/1,059 default fact lifecycles still
stored outside the completed-owner representation. The old admission required
at least two eligible source frames. This unnecessarily excluded singleton
components and multi-frame components with only one eligible source remaining.

Completed-owner admission now accepts one eligible frame using the same transfer,
fact storage, slot projection and restoration implementation. It still requires
a settled source Run boundary, a completed source with no unresolved parent,
owned facts, stable fields and unshared values. No new fact graph, consumer list,
shape or historical binding table is introduced. The existing physical owner
remains an optional storage path; this does not enable takeover in every ordinary
parallel configuration or skip additional RHS operations.

Default fact lifecycles inherit the source epoch. Actual results and scalar
values stay in authoritative storage; hide/delete and epoch exceptions remain
explicit. A source frame can restore independently or later join a larger owner.
The diagnostic `multi-owner-control` uses the same binary and transfer logic,
changing only the singleton admission predicate.

## Actual runtime evidence

Frozen seed catalogs are unchanged. The same binary runs both modes with
`--port-domains-only`; retained Program bytes are identical. These are full
Graph-owned heap teardown measurements, not a partial frame subtotal.

| case | Graph before | Graph after | saved | fact-record capacity before → after |
| --- | ---: | ---: | ---: | --- |
| fact | 705,175 | 667,423 | 5.35% | 49,608 → 19,848 |
| loopfact | 616,289 | 602,681 | 2.21% | 44,504 → 19,592 |
| sum-bits | 1,830,387 | 1,796,683 | 1.84% | 142,512 → 80,552 |
| dot-product | 1,798,019 | 1,746,507 | 2.86% | 139,520 → 70,288 |

All remaining eligible default lifecycles from the audit are now inherited:
878/818/2,311/2,466 in total. Ordinary source records fall to 1/2/3/14, but logical
fact counts and source identities are preserved. Completed owner/frame metadata
grows and offsets much of the fact-record saving: sum-bits owner records grow
145,408→282,624 bytes. **This is not evidence that independent source identities
have been eliminated or that the 30%-of-original target has been reached.**

Restoration remains source-sized. Sum-bits cumulative reconstructed array
capacity grows 4,320→7,656 bytes, with maximum event unchanged at 360 bytes. Other
cases' restoration totals are unchanged. Execution peak decreases in three
cases but increases by 1,289 bytes in loopfact. The report includes owner counts,
all Graph fields, restoration causes and temporary takeover peaks so these costs
cannot be hidden behind improved lifecycle counts. No speed claim is made.

The next larger storage issue is per-owner/per-frame metadata. Any sharing must
retain bounded restoration slices and account for dead ranges retained by live
siblings; pooling everything into a single lifetime is not acceptable.

## Validation

- 55 ownership integration tests pass, including union, deletion, scalar-provider
  loss, cross-stage reading, transferred parents and template-derived fields.
- Eight fact-state tests pass. The new singleton case tests transfer, lifecycle
  mutation, extension, source-only restoration and sibling retirement.
- All 2,652 saved Run graph/RHS/write comparisons and four terminal checks pass.
  This is same-source standalone Cell differential validation, not a new native
  egglog acceptance result.

Reproduce the control and candidate using one `runtime_storage_peak` binary on
`out/cell-bake-owner-merge/batch/CASE/candidate.json`, with modes
`multi-owner-control` and `inherited-owners`, respectively. Write results as
`CASE-multi.json` and `CASE-singleton.json` under `out/cell-singleton-owners`.
`binary.json` records the frozen binary digest. No catalog enlargement is needed.

```sh
python3 benchmarks/cell-bake-owner-merge/singleton_results.py out/cell-singleton-owners out/cell-bake-owner-merge/batch benchmarks/cell-bake-owner-merge/singleton-results.json
```

The paired binary includes the concurrent worker-result integration from this
shared worktree in both modes. The same-binary control isolates singleton
admission; those independent changes are not included or credited in this commit.

README smoke commands also pass with fresh `out/cell-singleton-owners/readme-*`
outputs: `cargo cell-compile --case sum-bits`, `cargo cell-run`, and
`cargo cell-bench --repeat 5`. These default-path smoke checks do not exercise
optional owner transfer and are not a speed comparison; the ownership tests and
paired storage/Run checks above exercise this change.
