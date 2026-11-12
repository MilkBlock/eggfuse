# Cell acceptance inside Unit table registration

This is the actual standalone Cell CPU, not native egglog performance. The
control is `230bbe60`, with the same frozen programs, catalog, release features
and flags. This is implementation three after timing checkpoint `2166a3fb`.
There is no new timing campaign or claim that the two-workload speed gate passes.

## Opportunity and remaining obligations

The preceding Raytrace execution registered 102,399 Unit candidates in 1,003
regions. Stable candidate slots had removed the internal cross-table numbering
pass, but source acceptance still waited for every table owner to return.

The existing terminal Cell proof supplies the scope: no intervening mutable
read, union, fallible suffix or other Function producer; old/new Unit merge;
sealed Eq inputs and no earlier pending repair. The actual returned witness,
original source/error order, retirement and original Run visibility remain
mandatory. The existing catalog repeatedly executes these terminal Cell shapes;
its compiled effect sites and Shared Entry projections remain the cross-Run
interface. This change discharges their registration handoff, not additional
queries, and introduces no separate learning catalog. Small, single-table and unproved regions retain ordinary validation.

Every Cell from the same rule normally uses the same Unit tables. Merely
returning whole-table completion events would therefore still make its first
Cell wait for the last Cell's registration. Table owners now emit bounded
fragments of at most 32 exact decisions while continuing to use their original
key index. Stable candidate addresses permit the source to adopt an earlier
fragment while a later one is still being classified.

## Connected ownership and deleted wait

The source transfers the actual constructor directories, membership, changes,
reverse incidences, parent directory and Function-slot storage to independent
owners. These are moves of the original containers, not cloned graph snapshots.
Constructor row headers move into one flat buffer, shared by the row owner and
subscription owner. Their field allocations and Cell values remain shared.
The existing typed constructor footprint is now held by `Arc` so both owners
can use the compiler's original proof without cloning its columns.

Constructor installation, subscriptions and the Unit table owners are sibling
tasks in one pool scope. They do not nest a `rayon::join`: a nested join could
steal a slow table task and delay its own completion notification. The handshake
test exposed this in an intermediate implementation; that version is not the
final implementation.

Once both constructor owners and reserved slots have returned, the source can
consume its earliest Cell whose Unit decisions have arrived. It attaches that
Cell's original instance, adopts the exact winners, finishes its continuation
and seals its original results while other table owners may continue. The old
`plan_unit_registration` whole-region join is gone from production callers.
The two RHS queue callers share this one event consumer.

Source acceptance still preserves order. A source error stops adopting Cells,
but the event receiver continues collecting all leased owners. Final cleanup
then removes only the unadopted suffix using the existing exact keys and Cell
completed-prefix positions. Duplicate private rows are still invalidated; Bloom
or hashes never establish equality. No per-producer consumer list or extra
binding/fact graph is introduced.

This removes the all-table prerequisite for source Cell acceptance. The scope
still joins before it returns to ordinary execution, constructor owners still
cover the whole ready region, and source lifecycle/RHS completion is still
ordered. It does not make the whole graph concurrently writable or advance
another source Run early.

## Costs and actual coverage

| Raytrace work observation | Control | Candidate |
| --- | ---: | ---: |
| Registration candidates | 102,399 | 103,106 |
| Registration regions / pool scopes | 1,003 | 1,026 |
| Source Cells adopted through registration | not counted | 34,704 |
| Cells finished while registration work remains | 0 (whole-region join) | 32 |
| Ready source prefixes | not counted | 1,080 |
| Decision fragments | 0 | 4,184 |
| Unit registration metadata, cumulative bytes | 5,134,480 | 9,317,088 |
| Constructor registration metadata, cumulative bytes | 3,936,256 | 7,172,552 |
| Decision buffer capacity, cumulative bytes | 0 | 3,299,392 |
| Event buffer capacity, cumulative bytes | 0 | 2,016,000 |
| Extra shared Unit-field handles | 0 | 103,106 |

Only 32 of 34,704 accepted Cells (about 0.09%) finished while registration work
remained. This is **limited coverage with additional storage and dispatch cost**,
not an accepted speedup. Differences in region counts and adopted rows depend on
completion arrival and are not counts of saved waits. Every global query,
logical effect, maintenance operation, Sieve operation and iterative Bake
observation remains equal to the control. Reserved-slot holes remain a cost of
the preceding implementation; they have not been eliminated here.

See [results.json](results.json) for the final frozen counts, state hashes,
ordered Run summaries, logical effects and validation commands. New costs are
reported separately: shared Unit-field handles, flat constructor row/group
metadata, decision fragments, event buffers and event receive waits. Capacity
sums are neither peak memory nor a complete allocation trace. Receive wait
spans are diagnostic observations, not an isolated synchronization benchmark.
The diagnostic registration span now contains source adoption as well as worker
work; it must not be added to source-adoption time or treated as pure pool wait.

An early Cell is counted only after its source completion and while another
owner has not finished registration. An owner is marked finished **before**
queuing its final event; a delayed task epilogue cannot manufacture overlap.
This count is not CPU utilization or elapsed time saved.

The first connected observation released 48 Cells early, but also increased
constructor registration metadata from 3,936,256 to 10,526,368 cumulative bytes.
The final implementation replaces per-Cell inline row capacity and temporary
Group vectors with actual flat row headers and group ranges. It also removes
the nested joins and tightens the overlap counter. These intermediate records
are saved under `out/cell-registration-events/initial` and `before-accounting`;
they are not timing samples or an isolated comparison of those refinements.

Sum-bits has no eligible Unit registration region. This change provides no
coverage there and does not resolve its existing four-worker regression.
Limited early-release coverage remains evidence that whole-region constructor
ownership is too coarse; more registration events alone are not a speed result.

## Validation

167 runtime tests and 87 integration tests pass. The new handshake blocks a
later fragment of a table used by **every** Cell until the source has processed
the first 32 Cells. It also fails the source at several prefix positions and
checks that late owners restore exact indexes, visibility, changes and later
allocation. Forced hash/Bloom collisions pass, including 20 repeated handshakes
after the nested-join fix. One-worker, empty-stream and worker-panic tests cover
the event transport. Existing integration fixtures retain full Run snapshots,
ordered effects, late union, deletion/recreation and actual result aliases.

All-feature, sparse-only and legacy builds pass. The README compile/run/one-
repeat bench smoke commands pass. Frozen final exports, ordered Run summaries,
logical effects and maintenance are compared with the control. Native sum-bits
acceptance remains the unmodified `choice_diagnosis.py` contract, linked to this
execution's CPU state hash. Raytrace remains exact differential validation,
not a new native proof; Run summaries are not full intermediate graph snapshots.

Release features: `cell-absorption,view-ports,parallel-publication`.

```text
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```

Use the frozen commands and hashes in `out/cell-registration-events/manifest.json`
and fresh output locations for new runs:

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic out/cell-registration-events/semantic-acceptance.json
python3 benchmarks/cell-registration-events/check.py out/cell-unit-reservations out/cell-registration-events benchmarks/cell-registration-events/results.json
cargo cell-compile --case sum-bits --output out/cell-registration-events/readme-program
cargo cell-run --program out/cell-registration-events/readme-program/program.json --output out/cell-registration-events/readme-run
cargo cell-bench --program out/cell-registration-events/readme-program/program.json --repeat 1
```
