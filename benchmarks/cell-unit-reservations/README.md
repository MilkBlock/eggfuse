# Unit table owners assign witnesses without a cross-table identity scan

This is the actual standalone Cell CPU. The control is `2279396f`, with the same
programs, catalogs, release features and flags. This is implementation two after
timing checkpoint `2166a3fb`; no new timing campaign has been run. It does not
establish native egglog speed, saturated workers or a two-workload speedup.

## Opportunity and compiler obligations

The preceding Raytrace execution classified 102,916 Unit candidates in 1,044
registration regions. Each table first looked up keys and maintained a temporary
`seen` map. All tables then joined so one worker could gather a `Choice` array,
scan it in source order and assign compact Function IDs. Only after that global
pass could the tables start their second, index-installation pass.

The existing Cell Unit-tail proof already says that the results are Unit, their
merge is `old` or `new`, and the complete region has no intervening read, union,
fallible suffix or additional Function producer. Eq keys are sealed for this
epoch; pending repair and unsupported storage remain excluded. A Function ID is
an internal `Dependency` address, not a rule operand or a newly produced Eq value.
These facts make compact numbering unnecessary inside this region.

No new Bake catalog or runtime fact graph is introduced. The same Cell slots,
actual result references and compiled Entry projections continue across Runs.
Original source effects, actual same-key winners, error prefixes and visibility
remain live obligations. Constructor/Eq identities are unchanged.

## Connected change

Each candidate now has the stable slot `region_start + source_ordinal`, known
before any table starts. Each table owner performs one pass over its original
rows: query its authoritative key index, keep an existing witness or install
the candidate's reserved slot, and record membership/publication entries. A later
duplicate finds the earlier row in that same index. There is no temporary `seen`
map, `Choice` vector, cross-table compact-ID scan or second table pass.

The existing worker region initializes the reserved Function/decoded slots in
parallel with table work. Slots start non-live, with no decoded row, origin or
subscriptions. Source acceptance writes the actual candidate allocation into
the winning slot. Duplicate candidates retain their actual earlier witness and
drop their private row. They do not become logical updates.

The successful Function addresses are a strictly increasing renaming of the
old addresses: source order is preserved across tables and across later ordinary
allocations. Therefore sorted witness enumeration retains the same encounter
order. No live row moves or requires a forwarding map.

On source failure, the same owner restores only the accepted prefix, removes
unaccepted keys/memberships/changes and releases their row allocations. Unused
trailing slots are trimmed. Invalid slots between live winners remain occupied
as non-live headers; no reader or subscription points to those slots. Subsequent
allocation cannot reinterpret one of those holes as an old live witness.

The outer pool join still precedes source Cell acceptance. This change removes
the **internal classification → global numbering → installation dependency**;
it does not yet release source Cells individually while other registration
owners run. That remaining ownership/visibility boundary is not claimed solved.

## Work and costs

| Raytrace observation | Control | Candidate |
| --- | ---: | ---: |
| Registration candidates | 102,916 | 102,399 |
| Registration regions / pool calls | 1,044 | 1,003 |
| Adopted Unit rows through registration | 67,957 | 67,632 |
| Temporary registration capacity, cumulative bytes | 11,296,904 | 5,134,480 |
| Reserved slot initializations | 0 | 102,399 |
| Initialized Function + decoded-slot bytes, cumulative | 0 | 9,830,304 |
| Unused suffix slots trimmed | 0 | 54 |
| Retained invalid interior slots | 0 | 34,713 |
| Retained invalid slot payload, bytes | 0 | 3,332,448 |

Each reserved slot is 96 bytes in this normal build. Reservation happened within
existing vector capacities in this observation (`capacity_growth_bytes = 0`).
That does not imply zero memory cost: the slots are initialized/touched, holes
remain, and later ordinary allocations may grow sooner. Temporary cumulative
capacity and persistent invalid-slot payload have different lifetimes and must
not be subtracted to claim a net memory improvement.

Arrival order changes ready-prefix sizes and coverage; pool-call differences
are not a saved-barrier count. The code has one table pass where it previously
had two and no global compact-ID pass. Every candidate still needs exact key
classification, and live rows still need index/subscription/publication work.
No extra pool invocation is added. Sum-bits has no eligible registration region
and acquires no reserved slots, so its earlier regression is not resolved here.

Both executions have identical total local births/reuses, Unit candidates,
inserts/invalidations, global query counts, logical effects and maintenance work.
Complete observations and hashes are in [results.json](results.json).

## Semantic checks

165 runtime tests, the new audit test and 87 integration tests pass. The 37
execution/owner tests and the two registration tests also pass with forced
hash/Bloom collisions. All-feature, sparse-only and legacy builds pass, as do
the README compile/run/single-repeat bench smoke commands.

Registration tests now verify an injective, order-preserving old/new witness
mapping, exact duplicate aliases, original allocation identity, partial failure
cleanup and subsequent allocation. They verify that invalid slots have no live
row, origin, decoded payload or reverse dependency. Interleaved publication and
small-fixture Run snapshots still use their original checks.

The old index-bearing write audit remains unchanged and available as a strict
address diagnostic. An opt-in logical write digest separately records every
epoch, source ordinal/rule, table, key and old/new value in order. Only the Unit
registration fixture uses that digest for its changed addresses; other existing
strict write tests remain strict. A dedicated test proves that the strict audit
distinguishes address renaming while the logical audit still rejects reordered
effects. This is not a change to native semantic acceptance or its proof rules.

Frozen final exports and all 1,428 / 16,883 ordered Run summaries match the
control exactly, including its Eq values and row order. Run summaries are not
full intermediate graphs; the integration fixtures check those boundaries.
Native sum-bits acceptance is `pass`, linked to this run by the CPU export hash.
Raytrace remains exact differential validation, not an extended native proof.

## Reproduction

Release features: `cell-absorption,view-ports,parallel-publication`.

```text
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```

`out/cell-unit-reservations/manifest.json` records binary/program paths and hashes.
Use fresh output directories for the Cargo commands:

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic out/cell-unit-reservations/semantic-acceptance.json
python3 benchmarks/cell-unit-reservations/check.py out/cell-constructor-registry out/cell-unit-reservations benchmarks/cell-unit-reservations/results.json
cargo cell-compile --case sum-bits --output out/cell-unit-reservations/readme-program
cargo cell-run --program out/cell-unit-reservations/readme-program/program.json --output out/cell-unit-reservations/readme-run
cargo cell-bench --program out/cell-unit-reservations/readme-program/program.json --repeat 1
```
