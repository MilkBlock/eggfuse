"""Verify saved semantic, provenance, lifetime and timing measurements."""
import json
from pathlib import Path
from runpy import run_path
from statistics import median

HERE = Path(__file__).resolve().parent
checked = run_path(str(HERE.parent / "pair-source-frontier/evidence.py"))["checked"]


def verify():
    cases = ("sum-bits", "conjugate-gradient", "3mm")
    results = checked(HERE, ["results.json"], cases)
    rss = json.loads((HERE / "rss.json").read_bytes())
    for case, arms in results.items():
        moving = arms["move"]["private"]
        for width in (16, 64, 256):
            arm = arms[f"resident-{width}"]
            private, store = arm["private"], arm["store"]
            stats = store["stats"]
            for key in ("used", "fresh", "granted", "redeemed", "fallback", "unused"):
                assert private[key] == moving[key]
            assert private["offers_after_first_verify"] == private["slots_after_first_verify"] == 0
            assert store["width"] == width
            assert store["old_run_reads"] > 0
            assert store["published"] == store["same_address"] == stats["same_fact_buffer"] == private["used"]
            assert store["alive"] + stats["retired"] == private["used"]
            assert store["alive"] + store["held_holes"] == store["occupied_slots"]
            assert store["reserved_header_bytes"] == store["occupied_slots"] * store["header_slot_bytes"]
        assert set(rss[case]) == set(arms) - {"off", "vanilla"}
        for arm in rss[case].values():
            assert len(arm["bytes"]) == 3 and median(arm["bytes"]) == arm["median"]
    print("Verified resident header identity, later reads, capacity, source execution and process RSS on three programs.")


if __name__ == "__main__":
    verify()
