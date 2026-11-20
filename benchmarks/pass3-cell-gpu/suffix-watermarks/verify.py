"""Validate the source stream, physical receipts and activity of each frontier policy."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "pair-source-frontier"))
from evidence import checked


def verify(folder):
    small = {"sum-bits", "conjugate-gradient"}
    large = {"3mm", "deriche"}
    cases = checked(folder, ("small.json", "large.json"), small | large)
    for name, arms in cases.items():
        expected = {"vanilla", "off", "headers-cut", "threshold", "carry"}
        if name in small:
            expected |= {"headers", "scalar-cut", "proof"}
        assert set(arms) == expected
        for label, row in arms.items():
            assert len(row["ms"]) == 4
            if label == "vanilla":
                continue
            counts = row["frontier"]
            if label == "off":
                assert not any(counts.values())
                continue
            assert counts["requests"] > 0 and counts["audited"] > 0
            assert (counts["header_reads"] > 0) == (label in ("headers", "headers-cut", "threshold"))
            assert (counts["scalar_scans"] > 0) == (label == "scalar-cut")
            assert (counts["inspections"] > 0) == (label in ("proof", "carry"))
            assert (counts["threshold_skips"] > 0) == (label in ("threshold", "proof", "carry"))
            if label != "carry":
                assert counts["cross_generation_proofs"] == 0
            assert row["counts"]["exhausted"] == 0
    return cases


if __name__ == "__main__":
    print("Verified all frozen winners, raw receipts and frontier evidence on", len(verify(HERE)), "programs.")
