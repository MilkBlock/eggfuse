"""Verify exclusive main-thread attribution and agreement of the two execution endpoints."""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
data=json.loads((HERE/"results.json").read_bytes())
for case,arms in data.items():
    assert arms["packed"]["request"]["state_sha"]==arms["vanilla"]["request"]["state_sha"]
    assert arms["packed"]["request"]["runs"]==arms["vanilla"]["request"]["runs"]
    for v in arms.values():
        assert sum(sum(b.values()) for b in v["categories"].values())==v["main"]
        assert sum(v["multi"].values())==v["categories"]["execute"].get("multi_witness",0)
        assert v["request"]["samples_ms"] and all(x>0 for x in v["request"]["samples_ms"])
print("Verified sampled main-thread attribution and complete execution endpoints on 3mm and Deriche.")
