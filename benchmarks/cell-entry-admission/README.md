# Shared Entry admission: measure reuse before building another cache

Control: `ac850f2c`. Scope: **standalone Cell CPU**, not native egglog. This
iteration observes actual scheduled Cell Entries and removes unused Bloom
maintenance. It does not establish a speedup, a general sparsity theorem or 2x.

## Opportunity and the rejected cache

The last normal-binary profile located matching/Entry admission and publication
as substantial remaining work. Full Raytrace performs 10,916,139 Sieve probes
and 5,516,162 Free Join admission probes. Existing Sieve expressions are already
interned by typed query wiring; a large probe count does not prove identical
consumer work. The earlier [semijoin study](../../docs/SEMIJOIN.md) also found
that constructing a shared first-projection frontier could cost more than it
saved. Repeating that design without actual reuse evidence would be unjustified.

The optional `entry-admission-audit` build records a batch identity only after
the normal route actually reaches it: source Run epoch, Shared Entry node,
consumer watermark, and the complete ordered Sieve guard list derived from its
Cell query. Guards retain child-expression and receiving-column identity.
Only full raw-delta enumerations count toward exact batch reuse; existing
inverted/restricted frontiers are counted separately. Repeated batches assert
identical row, probe and rejection counts. No row bindings or runtime fact graph
are copied. All observation code and storage are absent from ordinary builds.

| Actual observations | sum-bits | Raytrace first 1,280 Runs | Complete Raytrace |
|---|---:|---:|---:|
| Full raw-delta batches with nonempty guards | 2,105 | 7,053 | 52,986 |
| Guard probes in these batches | 10,968 | 540,409 | 10,259,500 |
| Repeated batches with the same complete conditions | 9 | 200 | 625 |
| Repeated guard probes | 18 | 5,644 | 26,759 |
| Rejected rows within repeated batches | 3 | 1,434 | 16,823 |

Both programs compile 978 ordered guard classes, only 66 of which have multiple
static consumers. Complete Raytrace has at most 48 recorded identities live in
one Run. Its 26,759 repeated probes are approximately **0.245%** of all Sieve
probes, before charging cache lookup, materialization and retirement. This
does not justify an exact full-batch cache here. The census excludes partial
condition sharing, different watermarks, cross-Run reuse and other partitions;
it is not a negative result about every possible Cell composition.

## Containment of conditions

An additional offline analysis checks implications in the existing acyclic
condition graph. A strong projection entails a weak one only when table and
output-column order agree and each weak child condition is implied by a strong
child at the same receiving columns. Cell-entry conditions additionally require
the same driver table. This is a sufficient structural rule, not complete
normalization of all equivalent queries or general Ripsat Cell states.

If an earlier weak condition rejects every row of a batch, a later stronger
condition over that same Run/node/watermark may reuse the empty result. The
observer records at most 65,536 scalar batch events; the collector refuses
dropped evidence. The complete Raytrace record contains 52,986 events, no drops.

The opportunity is still small: **312 batches / 2,791 probes** on complete
Raytrace; only 109 batches / 1,021 probes come from nonidentical condition
classes. Sum-bits has four batches / five probes. Each proposed batch is also
fully rejected by the ordinary observed filter. No operation has been skipped
by this analysis, and no Bake credit is assigned. The existing full-query,
source Run, visibility and delta-ownership obligations remain authoritative.
Three positive/negative tests check implication direction, projection/table/port
identity, Run/watermark/node boundaries and rejection of dropped/cyclic evidence.

## Implemented takeover: remove a representation that is never read

The shared typed projection width determines the support representation:
zero columns use Unit; one/two columns use fixed-width exact fingerprint sets;
wider projections use the existing Bloom filter on lookup. Previously, cold
construction and every fresh support insertion maintained Bloom arrays for
**all** widths, including those that never read them.

`Spec::needs_bloom()` now gates cold construction and incremental insertion using
that same compiled width. This removes unused hashing, Bloom growth/repopulation
and bit writes for narrow projections, without adding a plan, cache, subscriber
or persistent field. Exact fingerprint sets remain necessary and unchanged;
fingerprint equality is still only candidate evidence for the ordinary exact
query. Wider filters and the legacy non-sparse representation retain their
previous Bloom behavior. There is no scheduled block switch in this change.

| Final live Bloom-array bytes | Before | After |
|---|---:|---:|
| sum-bits | 20,976 | 328 |
| Raytrace first 1,280 Runs | 791,600 | 0 |
| Complete Raytrace | 3,263,648 | 50,184 |

These are exact final array payload bytes, not allocator totals, peak RSS or
elapsed-time savings. Exact support keys and the empty Bloom headers remain.
Ordinary probe/rejection counts, support additions, dependency propagation and
actual graph effects remain identical. The runtime removes maintenance within
its proven representation coverage; this is not another claimed skipped match.

## Validation and next decision

- Observed controls reproduce the saved Kernel control's states, complete ordered
  Run signatures, graph operations, Sieve, Free Join and Entry work. The later
  Run-local accounting change does not alter these values.
- Before/after sum-bits, Raytrace prefix and complete Raytrace states, ordered
  logical/executed Runs, actual effects and admission counts are exact. The
  additional dominance observer has the same states/work/Run signatures too.
- Forced zero-bit query fingerprints on sum-bits preserve before/after state,
  ordered Runs and work. Wide Bloom collisions still propagate each fresh key;
  unit tests also exercise narrow exact support and invalidation.
- 98 runtime unit tests, 30 selected compiler integration tests and the two
  legacy Sieve tests pass. Integration fixtures cover source-Run visibility,
  workers, late inputs, union and deletion/recreation. The `query_receipts` target
  is feature-disabled in this invocation and contributes **zero** tests.
- The original native sum-bits choice validator returns `pass` / exit 0 on the
  candidate export. Raytrace evidence is relative, not an independent native
  proof. No new 14-window capture is claimed.
- No-default-feature compilation and fresh README compile/run/bench (repeat 1)
  pass. These runs are not a new throughput checkpoint.

The next candidate should change **which Entries are visited**, rather than
cache nearly identical consumer filters. Sieve already maintains joined support
keys. When that set is much smaller than a delta batch and a current reverse
column index already exists, those keys may directly select a bounded candidate
domain. Such an experiment must charge key enumeration, candidate references,
ordering and fallback; preserve consumer predicates/watermarks; and avoid
building another persistent membership index. This is a proposed experiment,
not an implemented optimization or a promised speedup.

## Reproduction

Use the frozen `cell-fixed-reads` programs and new output directories. Freeze
each observer before building another configuration:

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,entry-admission-audit --example query_prefix
OBSERVER SUM_PROGRAM FRESH_SUM 2000 4 64 canonical --repair-ports --entry-publications --cell-absorption
OBSERVER RAY_PROGRAM FRESH_PREFIX 1280 4 64 canonical --repair-ports --entry-publications --cell-absorption
OBSERVER RAY_PROGRAM FRESH_RAY 20000 4 64 canonical --repair-ports --entry-publications --cell-absorption
python3 -m unittest discover -s benchmarks/cell-entry-admission -p 'test_*.py'
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-entry-admission/collect.py ROOT benchmarks/cell-entry-admission/results.json
```

`control.patch`, applied only in a separate checkout, restores always-maintained
Bloom arrays for a reproducible control build. Its narrow-array-removal unit
assertion is expected to fail; use it only to build the comparison observer.
The initially frozen before/after observers predate the additional event-report
fields, but have identical ordinary behavior and aggregate batch observations;
the third observer records the implication evidence. Reproductions can use the
newer observation fields on both sides. Raw graphs, event reports and binaries
remain ignored in `out/cell-entry-admission`; `results.json` binds their hashes
and the original accepted controls. No benchmark timings are inferred from them.
