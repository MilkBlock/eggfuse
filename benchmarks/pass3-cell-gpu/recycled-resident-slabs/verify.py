"""Validate archived paired source audits, fault injections, lifecycle, timings and RSS."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

def load(name):
    return json.loads((HERE / name).read_text())

def verify():
    manifest = load("manifest.json")
    for name, sha in manifest["files"].items():
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == sha, name
    timing, rss = load("results.json"), load("rss.json")
    assert set(timing) == set(rss) == {"conjugate-gradient", "3mm"}
    fields = ("raw","multi","commits","physical","root_parents","root_ids","nested_ids",
              "cells","state_sha","children","wire_hash","rhs","direct_cells","decisions")
    for case, arms in timing.items():
        base, dense = arms["off"], arms["dense"]
        assert all(base[k] == dense[k] for k in fields)
        for name in ("off", "dense"):
            row = arms[name]
            assert row["aligned"] and all(row["checks"].values())
            assert len(row["ms"]) == 4 and len(rss[case][name]["bytes"]) == 3
            assert row["rhs"] == row["neural_rhs"]
            w = row["store"]
            assert w["published"] == w["same_address"] == w["stats"]["same_fact_buffer"] == row["staging"]["used"]
            assert w["stats"]["private_dropped"] + w["published"] == w["stats"]["grants"]
            assert w["alive"] + w["stats"]["retired"] == w["published"]
            assert w["alive"] + w["held_holes"] == w["occupied_slots"]
        r = dense["store"]["recycle"]
        assert r["fresh_header_slots"] + r["grants_into_old_holes"] == dense["staging"]["granted"]
        assert r["new_pages"] + r["new_pages_avoided"] == base["store"]["recycle"]["new_pages"]
        assert r["published_from_old_holes"] and r["new_pages_avoided"] and r["all_reused_runs"]
        assert dense["store"]["old_run_reads"] == base["store"]["old_run_reads"] > 0
    faults = load("faults.json")
    assert set(faults) == {"moving", "resident", "duplicate", "withheld", "stale", "foreign"}
    for name, row in faults.items():
        assert row["aligned"] and all(row["checks"].values())
        assert all(row[k] == faults["moving"][k] for k in fields if k != "decisions")
        c, w = row["staging"], row["resident"]
        if name in ("stale", "withheld", "foreign"):
            deny = {"stale":"stale_named", "withheld":"missing_named", "foreign":"foreign_denials"}[name]
            assert c[deny] > 0 and c["fallback"] == c["fresh"] and w["published"] == w["occupied_slots"] == 0
        if name in ("resident","duplicate"):
            assert w["recycle"]["published_from_old_holes"] > 0 and w["same_address"] == c["used"]
        if name == "duplicate":
            assert c["duplicate_denials"] == c["used"] == faults["resident"]["staging"]["used"]
    fixture = (HERE / "test.txt").read_text()
    assert "dense_refill_keeps_neighbours_and_retires_old_ids ... ok" in fixture and "1 passed; 0 failed" in fixture
    print("Two paired source audits, six fault arms, stable-ID lifecycle and RSS samples verified.")

if __name__ == "__main__":
    verify()
