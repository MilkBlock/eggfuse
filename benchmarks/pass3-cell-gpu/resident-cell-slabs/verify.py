"""Check archived native evidence, including source agreement and physical pointer identity."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = {"moving", "resident", "stale", "foreign", "withheld", "duplicate"}
IDENTICAL = ("rhs", "raw", "commits", "physical", "root_parents", "root_ids",
             "nested_ids", "cells", "state_sha", "children", "multi", "wire_hash")
FAULTS = {"stale": "stale_named", "foreign": "foreign_denials", "withheld": "missing_named"}


def verify():
    manifest = json.loads((HERE / "manifest.json").read_text())
    for file, digest in manifest["local_sources"].items():
        assert hashlib.sha256((HERE / file).read_bytes()).hexdigest() == digest, file
    report = json.loads((HERE / "faults.json").read_text())
    assert set(report) == ARMS
    moving = report["moving"]
    for arm, case in report.items():
        assert case["aligned"] and all(case["checks"].values()), arm
        assert case["rhs"] == case["neural_rhs"] == 7265
        assert 100 * case["direct_cells"] >= 98 * case["fresh"]
        assert all(case[key] == moving[key] for key in IDENTICAL), arm
        store, stage = case["resident"], case["staging"]
        stats = store["stats"]
        if arm == "moving":
            assert store["width"] == stats["grants"] == 0 and stage["used"] > 0
            continue
        assert store["width"] == 64
        assert stats["grants"] == stage["granted"] == stats["published"] + stats["private_dropped"]
        assert stats["published"] == store["published"] == store["alive"] + stats["retired"]
        assert stage["used"] == stats["published"] == store["same_address"] == stats["same_fact_buffer"]
        assert store["occupied_slots"] == store["alive"] + store["held_holes"]
        assert store["reserved_header_bytes"] == store["occupied_slots"] * store["header_slot_bytes"]
        if arm in FAULTS:
            assert stage[FAULTS[arm]] > 0 and stage["fallback"] == stage["fresh"]
            assert store["occupied_slots"] == stats["published"] == 0
        else:
            assert stage["used"] == moving["staging"]["used"] > 0
            assert store["pointer_checks"] >= store["old_run_reads"] > 0
            assert stats["peak_held_holes"] >= store["held_holes"] > 0
            assert stats["cumulative_held_hole_runs"] >= stats["peak_held_holes"]
            assert stats["cumulative_resident_live_runs"] >= store["alive"] > 0
            assert stats["retired"] > 0 and stats["released_pages"] > 0
        if arm == "duplicate":
            assert stage["duplicate_denials"] == stage["used"]
    fixture = (HERE / "test.txt").read_text()
    assert "private_lanes_become_visible_in_place_and_release_the_last_owner ... ok" in fixture
    assert "1 passed; 0 failed" in fixture
    print("Six native source/physical audits and the slab lifecycle fixture agree.")


if __name__ == "__main__":
    verify()
