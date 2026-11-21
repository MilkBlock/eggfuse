"""Validate issued-token denominators, independent origin survival and resource curves."""
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent


def load(path):
    return json.loads(path.read_bytes())


def scorecard():
    births=load(HERE.parent/"token-constructor-births/results.json")
    samples=load(HERE/"results.json")
    rss=load(HERE.parent/"verified-wave-rss/results.json")
    proofs=load(HERE.parent/"verified-wave-rss/audit.json")
    joint={}
    for c,variants in samples.items():
        ref=births[c]
        baseline=variants["baseline"]
        for arm,q in variants.items():
            n=sum(q["tokens"])
            assert q["birth_digest"]==ref["source_birth_digest"]
            assert q["constructor_births"]==ref["per_committed_root"]["births"]
            assert q["retained_origins"]==ref["retention"]["original_visible_per_committed_root"]["births"]
            assert q["source"]==baseline["source"] and all(q["checks"].values())
            assert q["rhs"]==ref["per_committed_root"]["denominator"] and q["nested_ids"]==baseline["nested_ids"]
            assert q["per_packet"]==q["constructor_births"]/n
            assert q["effective_per_packet"]==q["retained_origins"]/n
            assert q["decisions"]==baseline["decisions"]
            if arm.startswith("rl-") or arm=="row4":
                assert q["tokens"]==baseline["tokens"]
        assert variants["row4"]["pages"]>baseline["pages"]
        assert baseline["tokens"][:2]==[ref["issued_roots"][x] for x in ("single","multi")]
        assert baseline["tokens"][2]==ref["child_packets"]["selected"]
        for view in (1,2,3):
            assert variants[f"view{view}"]["views"]==view
        all_data=load(HERE.parent/"verified-wave-execution"/("small.json" if c=="sum-bits" else "large.json"))[c]
        section=joint[c]={}
        for label,key in (("raw","off"),("filter","filter"),("packed","packed"),("ports","ports"),("fraction","pool")):
            q=variants["expanded" if label=="raw" else "baseline"]
            run=all_data[key]
            rd=proofs[c]["arms"][label]["source"]
            for field in ("rhs","raw","multi","physical","state_sha","commits"):
                assert rd[field]==run[field],(c,label,field)
            for field in ("rhs","root_ids","nested_ids"):
                assert q[field]==run[field]
            assert q["source"]==run["state_sha"]
            assert q["tokens"][:2]==[run["neural_events"][s] for s in ("sealed_single","sealed_multi")]
            assert run["children"]==all_data["packed"]["children"]
            m=rss[c]["arms"][label]["median"]
            threshold=m["thresholds"]["delta0.9"]
            section[label]=dict(effective_per_packet=q["effective_per_packet"],delta_kib=rss[c]["thresholds_kib"]["0.9"][1],
                                time_ms=threshold["median_ms"],crossings=threshold["outcomes"],peak_mib=m["peak_mib"],
                                redeemed_at_threshold=threshold["median_redeemed_at_cross"],plain_inference_ms=m["plain_ms"])
    return joint


if __name__=="__main__":
    actual=scorecard()
    assert actual==load(HERE/"scorecard.json")
    print("Verified separate birth/endpoint numerators, root/child denominators and RSS-threshold source identities.")
