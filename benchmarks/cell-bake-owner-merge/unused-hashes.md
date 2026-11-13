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
