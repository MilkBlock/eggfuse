"""Reconcile the archived logical constructor birth and final-origin survival ledgers."""
from pathlib import Path
import hashlib,json,math

HERE=Path(__file__).resolve().parent


def load(n):
    return json.loads((HERE/n).read_bytes())


def check_hist(h):
    bins={int(k):v for k,v in h["counts"].items()}
    assert sum(bins.values())==h["denominator"]
    assert sum(k*n for k,n in bins.items())==h["births"]
    assert bins.get(0,0)==h["zero"] and bins.get(1,0)==h["one"]
    assert sum(n for k,n in bins.items() if k>1)==h["two_plus"]
    assert max(bins)==h["max"]
    if "mean" in h:assert math.isclose(h["mean"],h["births"]/h["denominator"])


def main():
    m=load("manifest.json")
    for f,expected in m["files"].items():
        assert hashlib.sha256((HERE/f).read_bytes()).hexdigest()==expected,f
    data=load("results.json")
    assert set(data)=={"sum-bits","dot-product","conjugate-gradient","3mm","deriche"}
    for case,x in data.items():
        q=x["exact"];assert all(q["checks"].values())
        h=x["per_committed_root"];issued=x["per_issued_root"];a=x["activations"]
        ret=x["retention"];live=ret["original_visible_per_committed_root"];status=ret["by_origin"]
        assert h["denominator"]==q["rhs"]==q["neural_rhs"]
        assert issued["denominator"]==sum(x["issued_roots"].values()) and issued["births"]==h["births"]
        assert a["typed_rhs"]+a["runtime_dynamic"]==h["births"]
        assert h["births"]+a.get("unowned_runtime",0)==a["run_constructors"]
        assert sum(a.get(s,0) for s in ("initial_constructors","initial_relations","run_constructors","run_relations"))==x["all_activations"]
        assert sum(status["owned"].values())==h["births"] and live["births"]==status["owned"]["visible"]
        assert sum(ret["owned_visible_paths"].values())==live["births"]
        assert sum(status["initial"].values())==a["initial_constructors"]
        assert sum(status.get("unowned",{}).values())==a.get("unowned_runtime",0)
        for z in (h,issued,live,x["per_original_spine_root"],ret["original_visible_spine_reattribution"],
                  *x["per_committed_provider"].values(),*x["per_committed_provider_visible"].values(),
                  x["without_initialization"]["all_born"],x["without_initialization"]["original_visible"]):
            check_hist(z)
        assert sum(z["births"] for z in x["per_committed_provider"].values())==h["births"]
        assert sum(z["births"] for z in x["per_committed_provider_visible"].values())==live["births"]
        assert x["per_original_spine_root"]["births"]==h["births"]
        assert ret["original_visible_spine_reattribution"]["births"]==live["births"]
        c=x["child_packets"];assert c["fresh"]+c["reused"]<=c["selected"]<=c["candidates"]
        for name,n in (("constructor_births",h["births"]),("original_visible",live["births"])):
            exclusive=x["exclusive_issued_packet_distributions"][name];check_hist(exclusive)
            assert exclusive["births"]==n and exclusive["denominator"]==issued["denominator"]+c["selected"]
        assert live["per_root_and_selected_child"]==live["births"]/(issued["denominator"]+c["selected"])
        e=x["extremes"]["immediate"];assert sum(e["immediate_paths"].values())==e["credited_births"]==h["max"]
        e=x["extremes"]["spine_attribution"]
        assert sum(e["immediate_paths"].values())+e["descendant_typed_rhs"]+e["descendant_dynamic"]==e["credited_births"]
    print("Five complete source/physical/Spine and final-export ledgers, request denominators and survivor distributions agree.")


if __name__=="__main__":main()
