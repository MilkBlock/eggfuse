"""Validate source provenance and actual scheduling from the archived native reports."""
import json
from pathlib import Path
from statistics import median
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "pair-source-frontier"))
from evidence import checked
from certify import evidence


def verify(folder):
    certificates = json.loads((folder / "certificates.json").read_bytes())
    assert certificates == json.loads(json.dumps(evidence()))
    for key, result in certificates.items():
        if "policy-gradient" in key:
            assert result["action"] == 4 and result["margin_bounds"][4] > 0
        else:
            assert result["action"] is None
    cases = ("sum-bits", "conjugate-gradient", "3mm")
    arms = {"off", "direct-1", "direct-8", "serial-8", "shared-8", "policy-8"}
    audits = []
    for seed, names in [(1703, cases), (1709, cases[:2])]:
        data = checked(folder, (f"seed{seed}.json",), names)
        for name, rows in data.items():
            assert set(rows) == arms | {"vanilla"}
            baseline = rows["off"]
            for arm in arms:
                v = rows[arm]
                stats = v["issuer"]
                assert len(v["ms"]) == 4
                assert 0 < stats["invocations"] == sum(stats["calls"])
                assert stats["source_headers"] == sum(stats["addressed"]) == baseline["issuer"]["source_headers"]
                assert stats["emitted"] == baseline["issuer"]["emitted"] > 0
                assert v["score_digest"] == baseline["score_digest"]
                if arm in ("direct-1", "direct-8"):
                    assert stats["evaluations"] == stats["source_headers"]
                if arm in ("shared-8", "direct-8"):
                    assert stats["real_parallel_calls"] > 0 and stats["peak_workers"] > 1
                if arm in ("off", "serial-8", "direct-1"):
                    assert stats["peak_workers"] == 1 and stats["real_parallel_calls"] == 0
            assert rows["policy-8"]["issuer"]["calls"] == baseline["issuer"]["calls"]
            assert rows["policy-8"]["issuer"]["evaluations"] == baseline["issuer"]["evaluations"]
            assert baseline["issuer"]["evaluations"] < rows["serial-8"]["issuer"]["evaluations"]
            assert rows["serial-8"]["issuer"]["evaluations"] == rows["shared-8"]["issuer"]["evaluations"]
            audits.append((name, seed))
    timing = json.loads((folder / "phases.json").read_bytes())
    assert set(timing) == set(cases)
    for group in timing.values():
        assert set(group) == arms
        for row in group.values():
            assert len(row["samples"]) == 3 and len(row["ms"]) == 6
            assert row["ms"] == list(map(median, zip(*row["samples"])))
            assert all(0 < sum(t[:4]) <= t[4] <= t[5] for t in row["samples"])
    return audits


if __name__ == "__main__":
    print("Verified equivalent neural scores, issued proofs, Run endpoints and row dispatch in",
          len(verify(HERE)), "complete Pass 3 program/seed pairs.")
