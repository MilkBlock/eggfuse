"""Check the recorded scale, full-source outcomes and FEPT accounting."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE/name).read_bytes())


def main():
    manifest, data, memory = read("manifest.json"), read("results.json"), read("rss-results.json")
    assert set(data["cases"]) == set(manifest["targets"]) == set(memory) == {"sum-bits","3mm"}
    assert data["inference_device"] == "single-threaded Rust CPU"
    hashes = set()
    for case, result in data["cases"].items():
        target = manifest["targets"][case]
        hashes.add(target["ordered_id_digest"])
        assert target["accepted_shapes"] == result["templates"] >= 500
        assert result["target_sha256"] == target["target_sha256"]
        baseline = result["arms"]["leaf"]
        union = result["arms"]["union"]
        for name, row in result["arms"].items():
            assert all(row["checks"].values())
            assert row["coverage"]["neural_rhs"] == row["rhs"] == row["coverage"]["source_pass_rhs"]
            assert row["coverage"]["residual_rhs"] == 0
            assert not row["coverage"]["multi_residual_enabled"] and not row["coverage"]["single_residual_enabled"]
            for key in ("runs","rhs","state_sha","physical","births_sha","end_sha","visible"):
                assert row[key] == baseline[key]
            assert sum(row["emitted"])+row["child"] == row["packets"]
            assert row["visible"]/row["packets"] == row["fept"]
            assert baseline["packets"]-row["packets"] == row["internal"]
            if name.startswith("union_"):
                assert 0 < row["fragment_completions"] <= row["fragment_roots_accepted"] <= row["fragment_sites_issued"]
                assert sum(item[4] for item in row["fragment_ledger"]) == row["fragment_ops"]
                assert sum(row["fragment_final_origins"].values()) <= row["visible"]
                assert row["packets"] == union["packets"]
        for arm in memory[case]["arms"].values():
            assert len(arm["trials"]) == 4 and arm["reached"] == sum(t["crossing"][0]=="reached" for t in arm["trials"])
        print(case,result["templates"],union["packets"],union["fept"])
    assert len(hashes)==1


if __name__=="__main__":
    if not __debug__:
        raise ValueError("verification requires assertions")
    main()
