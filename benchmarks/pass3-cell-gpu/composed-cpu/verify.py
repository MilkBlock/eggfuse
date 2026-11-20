"""Verify archived source audits, paired sample counts and active paths without executing benchmarks."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "pair-source-frontier"))
from evidence import CASES, checked


def verify(folder):
    groups = checked(folder, ("core.json", "large.json"), CASES, raw=False)
    for case, arms in groups.items():
        assert set(arms) == {"vanilla", "off", "arithmetic", "headers", "combined", "lazy", "combined-lazy"}
        for name, row in arms.items():
            assert len(row["ms"]) == (4 if case in ("3mm", "deriche") else 6)
            if name in ("headers", "combined", "combined-lazy"):
                assert row["header"]["delta_updates"] > 0 and row["header"]["checked_rows"] > 0
            if name in ("arithmetic", "combined"):
                assert row["equations"]["numeric_requests"] > 0
            if name in ("lazy", "combined-lazy"):
                assert row["lazy"]["computed"] > 0 and row["lazy"]["table_hits"] > 0
            if name in ("arithmetic", "combined", "lazy", "combined-lazy"):
                assert row["counts"]["raw_tuples"] < arms["off"]["counts"]["raw_tuples"]
            if name in ("headers", "combined", "lazy", "combined-lazy"):
                reference = arms["off" if name == "headers" else "arithmetic"]
                for field in ("raw", "multi", "commits", "physical", "children"):
                    assert row[field] == reference[field], (case, name, field)
    return groups


if __name__ == "__main__":
    print("Verified combined CPU execution and source-aligned ownership on", len(verify(HERE)), "programs")
