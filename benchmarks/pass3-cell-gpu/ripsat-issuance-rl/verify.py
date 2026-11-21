"""Reconcile committed training returns and independent held-out interventions."""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
def read(name):
    return json.loads((HERE/name).read_bytes())


def main():
    actor=read("actor.json")
    assert actor["weights"]!=actor["initial_weights"]
    episodes=actor["episodes"]
    assert len(episodes)==len({e["seed"] for e in episodes})
    for e in episodes:
        assert e["leaf_packets"]-e["sample_packets"]==e["savings"]
        assert 0<=e["composed"]<=e["decisions"] and 0<=e["terminal"]<=e["savings"]
    assert any(0<e["composed"]<e["decisions"] for e in episodes)
    timing=read("performance.json")
    results=read("results.json")
    assert set(results)==set(timing)=={"3mm","sum-bits"}
    for case,arms in results.items():
        leaf,trained,full=arms["leaf"],arms["learned"],arms["full"]
        for row in arms.values():
            assert all(row["checks"].values())
            assert row["saved"]==leaf["packets"]-row["packets"]
            assert row["final_origins"]==leaf["final_origins"]
            assert row["fept"]==row["final_origins"]/row["packets"]
        assert trained["packets"]==full["packets"]<leaf["packets"]
        assert arms["initial"]["packets"]==leaf["packets"]
        assert min(arms["sample"]["token_actions"])>0
        measured=timing[case]["arms"]
        assert measured["stale"]["packets"]-trained["packets"]==trained["terminal"]>0
        assert measured["stale"]["terminal"]==0
        assert measured["learned"]["exact_rhs"]==0
        for trial in measured["learned"]["rss"]:
            assert trial["increment"][0]=="reached"
        print(case,trained["saved"],"fewer packets;",trained["terminal"],"terminal commits")


if __name__=="__main__":
    if not __debug__: raise ValueError("verification requires assertions")
    main()
