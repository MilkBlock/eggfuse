# Stopped experiment: transport of learned-key regions

**These results do not qualify as explicit-parent FEPT.** A region packet specifies a prefix predicate, a source interval and a posting window. The receiver reads public graph rows to discover which individual parents it denotes. Sending fewer descriptors changes transport traffic; it does not establish that a model independently proposed those parents or generated more final-visible nodes per explicit-parent token. The user stopped region optimization. The active timing job and queued RSS job were cancelled. [Explicit-parent FEPT accounting](../../../docs/EXPLICIT_PARENT_FEPT.zh.md)

## Observations before the stop

Each row compares the number of transmitted two-parent descriptors and actual descriptor bytes. The receiver must still reconstruct and verify candidate combinations.

| Workload | Configuration | Descriptors | Descriptor bytes | Receiver candidate pairs |
| --- | --- | ---: | ---: | ---: |
| 3mm | Original compound | 40,264 | 3,973,660 | 683,319 |
| 3mm | Explicit keys, larger bounds | 27,801 | 3,026,600 | 688,209 |
| 3mm | Fixed prefix | 12,242 | 1,566,976 | 688,209 |
| 3mm | Donor head chooses prefix split | 17,634 | 2,257,152 | 688,209 |
| sum-bits | Original compound | 1,542 | 131,716 | 14,818 |
| sum-bits | Explicit keys, larger bounds | 1,348 | 117,076 | 15,436 |
| sum-bits | Fixed prefix | 1,662 | 212,736 | 15,436 |
| sum-bits | Donor head chooses prefix split | 2,142 | 274,176 | 15,436 |

All four arms on both programs had already passed the full source and physical comparison before these counters were printed, including the ordered raw proposal stream and unchanged visible constructor-origin ledger. Those checks establish that the transport preserves the observed execution. The original 3mm workload still produced 92,658 visible constructor origins, and sum-bits still produced 2,691. Sum-bits timing and fault checks finished. The four native medians in table order were 45.16, 45.43, 50.15 and 50.10 ms. The stop occurred before the complete 3mm timing artifact was written. No RSS samples were collected.

The 128-byte fixed packet contains a typed full-key prefix, public source generations, a bounded root interval, right-posting offsets and a SHA-256 digest of the covered full keys. It carries no list of original left/right parent addresses. The receiver enumerates current public rows and postings, checks the full-key digest, cardinality and extent, then applies the original source guards. All source predicates, the arithmetic port and original singleton dispatch were shared with the original compound comparator. The donor head is the pre-existing three-coefficient occupancy head; it selected between a coarse prefix and two narrower prefixes before partner enumeration. It produced more transport records than the fixed prefix in both measured programs.

[Recorded transport counters and completed sum-bits samples](transport.json) · [Native region codec](region.rs)
