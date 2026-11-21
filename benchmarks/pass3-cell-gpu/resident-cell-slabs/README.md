# Publishing Cell headers directly from speculative slabs

This native Cell CPU experiment changes storage beneath the whole-Run allocator and group-authenticated vouchers. The allocator constructs private Cell headers and their fact buffers in owned, fixed-length pages before verification. Each approved lane remains private until the original ordered RHS commit assigns a logical Cell ID and publishes its page and offset. Later logical reads and repairs resolve that ID back to the original header. Direct commits use the lane immediately. Promotions transfer ordinary scratch state into a claimed lane before publication.

Each page owns its lanes through a boxed slice. Growing the page directory can move the box handle while preserving the address of every header. A rejected lane drops its payload at Run close. A partially occupied page retains empty header slots until its last published member retires. The release path removes the public ID mapping before reusing page numbers. The dense ID directory has a sparse exception for distant IDs. Ordinary allocations continue to use the ordinary store.

Enable the holder with `spec_cells.timing="run"`, `spec_cells.storage="group"` and `spec_cells.resident_headers=true`. Set `spec_cells.page_width` to 16, 64, or 256 to change reclamation granularity. The moving-group control uses identical forecasts and vouchers with `resident_headers` disabled.

## Recorded native audits

The [sum-bits fault results](faults.json) compare each arm with an independent vanilla source trace across 1,428 Runs. There are 7,265 root proposals in the evaluated subset. The source comparison covers ordered RHS, effective writes, Spine resumptions, unions, schedule and final graph. The physical comparison also checks ordered parent streams, stable Cell IDs and child wiring against the moving-group arm.

At width 64, 2,140 of 5,696 granted headers became public at their original address. All 2,140 retained their fact-buffer address at publication. The audit checked 101,364 later-epoch accesses. At termination, 808 published headers remained live alongside 2,622 empty retained slots across 149 pages. The 3,430 reserved slots occupied 411,600 bytes in the lane arrays. The directory, fact buffers and ordinary store have additional costs. Peak resident memory and timing for repeated runs are covered by the [ablation](../resident-slab-ablation/).

Stale, foreign and withheld grants all published zero resident headers. Repeating valid claims rejected all 2,140 duplicates and preserved the original 2,140 publications. The dedicated [lifecycle test](conformance.rs) additionally exercises sparse ID lookup, private invisibility, later-epoch mutation, retirement and recycling. [Test output](test.txt)

## Reproduction

Run from this directory. The native builder expects the same frozen EggFuse source and offline workload bundle as the sibling group-named experiment. The private regression enables the measured Cargo features in an APFS clone of the built source tree.

```sh
exp=/Volumes/EggFuseWorkspace/experiments
python3 build.py "$exp/resident-fresh-build"
python3 probe.py "$exp/resident-fresh-build" "$exp/resident-fresh-test"
python3 faults.py --exp "$exp" --native "$exp/resident-fresh-build/session" \
  --weights ../speculative-allocation-policy/policy.json --out "$exp/resident-fresh-faults"
python3 verify.py
```

The [manifest](manifest.json) fingerprints the measured binary, implementation, trained policy and archived evidence. The offline verifier checks the recorded accounting, physical identity, semantic comparisons and fault controls without rebuilding the native binary.
