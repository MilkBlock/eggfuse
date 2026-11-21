"""Check independent source ledgers, equal grants, training splits and held-out placement."""
import json
from pathlib import Path
from runpy import run_path

HERE = Path(__file__).resolve().parent
checked = run_path(str(HERE.parent / "pair-source-frontier/evidence.py"))["checked"]


def load(name):
    return json.loads((HERE / name).read_bytes())


def verify():
    policy = load("policy.json")
    assert set(policy["donors"]) == {"sum-bits", "dot-product", "jacobi-1d"}
    lanes = births = 0
    for case in policy["donors"]:
        data = load(f"donors/{case}.json")
        assert len(data["groups"]) == data["counts"]["rules"]
        counts = [sum(v[i] for _, v in data["hist"]) for i in (0, 1)]
        lanes += sum(counts)
        births += counts[1]
        assert [sum(row[i+1] for _, _, _, rows in data["groups"] for row in rows) for i in (0, 1)] == counts
    assert policy["training_lanes"] == lanes and policy["training_births"] == births
    ceilings = load("ceilings.json")
    for seed, name, cases in ((1703,"results.json",("conjugate-gradient","3mm")), (1709,"seed1709.json",("conjugate-gradient",))):
        data = checked(HERE, [name], cases)
        assert set(cases).isdisjoint(policy["donors"])
        for case, arms in data.items():
            first = arms["first"]["rank"]
            for arm, v in arms.items():
                if arm in ("off", "vanilla"):
                    continue
                staging, rank = v["staging"], v["rank"]
                assert rank["lanes"] == first["lanes"] and rank["fresh_lanes"] == v["root_allocated"]
                assert rank["before_verifier"] == rank["selected"] == first["selected"]
                assert staging["offers_after_first_verify"] == staging["slots_after_first_verify"] == 0
                assert staging["granted"] == arms["first"]["staging"]["granted"]
                hits = rank["selected_fresh"]
                assert hits == staging["used"] == staging["payload_identity"]
                assert rank["first_fresh"] == first["selected_fresh"]
                assert hits <= rank["oracle_fresh"] == first["oracle_fresh"]
                if arm in ("first","feature","zero"):
                    assert hits == rank["first_fresh"]
                else:
                    weights = policy["models"][f"{arm}-{seed}"]
                    assert rank["scored"] > rank["selected"] and len(weights.get("hidden", [])) == int(arm.split("-")[1])
                    if seed == 1703:
                        c = ceilings[case]
                        assert c["selected"] == rank["selected"] and rank["oracle_fresh"] == c["local_oracle"] <= c["per_run_oracle"]
                        interval = c["bounds"][f"{arm}-{seed}"]
                        assert interval["lower"] <= hits <= interval["upper"], (case, arm, hits, interval)
    print("Verified training split, equal allocation budgets, held-out score bounds and aligned source executions.")


if __name__ == "__main__":
    verify()
