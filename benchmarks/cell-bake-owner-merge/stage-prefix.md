# Rejected stage-prefix witness trial

The trial patch is preserved for reproduction; **it is not active in the shared
runtime**. It applies to the runtime at `2582a7bb`. The recorded revision plus
patch digest and frozen binary digests identify the executed candidate. The
control is the saved shared-membership runtime on identical `prefix-all` inputs.

## What was changed

The ordinary constructor path consults baked witness routes. The temporary
`SourcePrefix` executor previously bypassed them. Also, a live stage cursor
excluded that prefix executor, whose receipt policy ordinarily did not keep
cross-stage results. The trial allowed constructor-only source prefixes with
stage cursors, kept needed outputs in the existing Effects slots, and consulted
the same witness plan against the temporary source frame. It added no per-instance
fact graph or binding copy.

Pending older tails kept their existing dependency probe. Existing selected
history results excluded this new path: an initial version ignored those results
and failed `matched_handoffs::residual_matches_inherit_results_after_guards_and_late_inputs`
because it lost previously saved queries. The corrected version retained the
original handoff consumer whenever selected transfer results existed.

The final candidate passed 59 ownership, 14 Entry publication, three closed-alias
and three matched-handoff tests, plus the runtime no-default-features check. The
ownership fixture explicitly required temporary-prefix route acceptance. All
2,652 saved source Run checks and four terminal checks passed. These are
standalone Cell CPU checks, not fresh native egglog acceptance.

## Measured work, not a speedup

| case | generic queries before → after | net queries saved | extra route-map searches | prefix route acceptances |
| --- | ---: | ---: | ---: | ---: |
| fact | 2,697 → 2,648 | 49 | 230 | 102 |
| loopfact | 2,116 → 2,094 | 22 | 71 | 57 |
| sum-bits | 11,965 → 11,846 | 119 | 944 | 314 |
| dot-product | 9,202 → 9,151 | 51 | 257 | 294 |

Prefix acceptances are not net saved lookups: some moved from the existing
ordinary path. Sum-bits also adds 448 alternative-candidate field checks and
293 prepared-witness field comparisons. The full changed work counters are in
the JSON. Constructor request counts and `rhs_frames_avoided` do not change.

Graph-owned bytes remain exactly 654,127 / 579,953 / 1,741,931 / 1,689,019.
Retained Program is unchanged. The process execution peak differs by only ten
bytes per case; that is not evidence of structural compression. No latency
measurement was performed, so this does not prove a slowdown either.

## Decision and next gate

Do not ship an extra generic witness attempt as saturated-stage takeover. The
trial saved 241 queries but added 1,502 address-map searches and more candidate
checks, with no reduction in resident Graph or avoided frames. It is insufficient
for the user's objective. The code was removed from the working runtime after
checking that its entire diff exactly matched the frozen measured patch.

A useful stage transition needs the current Entry to supply a selected completion
program and actual result references, while preserving selected history results.
Its acceptance must remove old query/receipt/publication work rather than count
route migration as saved work. A fully reused constructor RHS alone also does
not imply removable persistent state: this trial's previous ordinary path already
left no extra final Graph storage. Compression must target the live source and
fact/address obligations identified in the region census, not ephemeral frames
already discarded by normal completion.

## Reproduce

Use a separate checkout at `2582a7bb`, apply `stage-prefix-trial.patch`, then run
`stage_prefix.py ROOT CONTROL OUTPUT RESULT` through the shared compute queue.
ROOT is the saved batch root and CONTROL is the previous `out/cell-shared-membership`
directory. Use absolute paths when executing from another checkout. The script
builds and freezes its executables, repeats the exact saved Run checks, and records
complete Graph/Program heap plus work deltas. `--reuse-frozen` repeats only memory
runs; `--collect-only` rechecks saved results. Both require the measured source
patch to match the checkout, avoiding accidental attribution to reverted code.
