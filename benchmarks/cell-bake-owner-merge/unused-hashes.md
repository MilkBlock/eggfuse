# Remove hash payloads after port domains take over uniqueness

`use_port_domains_only` already removes the optional constructor birth-hint
index for tables whose complete symbolic-port domains provide exact lookup.
However, covered facts retained their old hash, and ordinary activation still
computed a hash even though no index would use it. Completed owners then copied
one eight-byte hash per fact into their backing arrays.

Covered facts now zero this unused payload when the hint index is removed, and
new covered facts normalize their stored hash to zero. Ordinary activation skips
the unused hash calculation. Paths that prepared a hash for another purpose
still do that work; this change does not claim to remove all hashing. Uncovered
constructors keep their actual hash and canonical index. Port equality checks,
field reads, constructor completion and repair remain required.

Completed fact storage represents an all-zero hash column by an empty array.
Its builder allocates no hash array until it encounters a nonzero value, so this
also avoids the unnecessary temporary array during takeover. Mixed owners keep
the dense array with exact zero prefixes and retired positions. A later nonzero
write materializes that array; lifecycle changes alone do not. This is a uniform
column omission, without a per-fact tag, sparse hash map or reverse dependency.
Fact membership and lifecycle arrays remain authoritative, and source-sized
restoration remains unchanged.

The existing `stored_hash_bytes` profile now reports the actual retained hash
arrays. It must not be confused with eight times the count of zero hashes: zeros
in mixed owners do not save array space. Already completed dense arrays are not
rescanned/repacked merely when hints are disabled; newly built completed owners
can omit them. No extra mutation-time compaction scan is introduced.

Tests cover zero arrays, mixed arrays with retired positions, re-materialization
on a nonzero write, source-stage inheritance and independent restoration. The
short integration test enables port-domain-only mode before execution and after
the first Run, transfers completed owners, then checks union, deletion and
recreation. Final exports, Run snapshots and binding audits agree with the
hint-enabled control. Independently constructed homogeneous owners are included
so the test verifies actual array removal; an earlier mixed-only fixture rightly
showed no array-byte reduction and is not evidence of savings.

This removes a real obsolete runtime payload but is a limited compression change.
There is no new full-workload Graph-memory percentage, speed result, native
egglog acceptance, or saturated-rule skip claim. The large compression target
remains unachieved.

Validation: jobs 249–250 pass seven arena/storage unit tests, all 66 ownership
integration tests, and the runtime no-default-features compile check.

## Four-workload retained-memory check

Job 252 runs the current binary once per previously frozen artifact, comparing
with the saved `b3322f9f` memory observations. This is a cumulative branch check,
not a same-binary isolated ablation. The new binary and both result files are
hashed in `hash-memory.json`.

| case | Graph before | Graph after | saved bytes | reduction | hash arrays after |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 535,367 | 528,711 | 6,656 | 1.24% | 1,176 |
| loopfact | 512,765 | 506,437 | 6,328 | 1.23% | 1,024 |
| sum-bits | 1,486,983 | 1,461,607 | 25,376 | 1.71% | 1,352 |
| dot-product | 1,434,643 | 1,412,907 | 21,736 | 1.52% | 2,416 |

Only the `cells` field changes in the Graph teardown; its exact reduction equals
the hash-array reduction in every case. Retained Program bytes are identical.
Maximum takeover extra bytes change 11,648→11,136; 11,152→10,876;
15,908→15,820; 15,848→15,376, respectively. Process high-water also decreases,
but includes the roughly 158–162 MB retained Program and cannot establish the
Graph-only execution peak.

Program digest, Run count, final export digest, owned fact lifecycle inventory,
component identities/bindings and static shapes match exactly. This does not
provide per-Run acceptance or a new native semantic proof. The 2,652 source Runs
are workload coverage, not committed-mutation counts.

The small complete-Graph benefit is real but closes this optimization direction:
only 1–2.4 KB of hash arrays remain per workload. No further hash packing can
make a meaningful contribution to the requested 70% overall reduction. The next
structural work must remove other fact/index or per-instance maintenance, rather
than making this format more elaborate.

Reproduce under the shared compute queue (use a fresh output directory):

```sh
~/.local/bin/eggfuse-job run --kind compute -- python3 benchmarks/cell-bake-owner-merge/hash_memory.py /private/tmp/eggfuse-dual-local-target/debug/examples/runtime_storage_peak out/cell-physical-regions out/cell-bake-owner-merge/batch/prefix-all out/cell-hash-memory-new benchmarks/cell-bake-owner-merge/hash-memory.json
```

Three comparator tests reject changed final state, lifecycle or wiring and check
actual array-byte accounting. There was no timing campaign.
