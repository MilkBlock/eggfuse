"""Check held-out source receipts, reward bounds, checkpoint/execution identity, and training split."""
from hashlib import sha256
import json
from math import isclose,tanh
from pathlib import Path

HERE=Path(__file__).resolve().parent
def load(name):
    return json.loads((HERE/name).read_bytes())


def score(w,x):
    def affine(weights,bias):
        for wi,xi in zip(weights,x):
            bias+=wi*xi
        return bias
    if "direct" in w:
        return affine(w["direct"],w["bias"])
    h=[tanh(affine(v,b)) for v,b in zip(w["hidden"],w["offsets"])]
    result=w["bias"]
    for v,weight in zip(h,w["output"]):
        result+=v*weight
    return result


def verify():
    checkpoint=load("models.json")
    donor=set(checkpoint["donor_sha"])
    assert donor=={"sum-bits","dot-product","jacobi-1d"}
    records=[]
    for c,checksum in checkpoint["donor_sha"].items():
        content=(HERE/"donors"/f"{c}.json").read_bytes()
        assert sha256(content).hexdigest()==checksum
        data=json.loads(content)
        assert data["case"]==c
        for ep,rid,x,n,e in data["samples"]:
            assert ep>=1 and rid>=0 and len(x)==12 and min(n,e)>=0
            records.append((x,n))
    for name,w in checkpoint["models"].items():
        selected=[(score(w,x)>0,n) for x,n in records]
        stats=checkpoint["training"][name]
        assert stats["choices"]==len(records)==5924
        assert stats["selected"]==sum(a for a,n in selected)
        assert stats["saved"]==sum(n-1 for a,n in selected if a)
        assert stats["maximum_saved"]==sum(max(n-1,0) for x,n in records)
    all_cases=load("heldout.json")
    all_cases.update(load("transfer.json"))
    assert set(all_cases)=={"conjugate-gradient","3mm","deriche"} and donor.isdisjoint(all_cases)
    terminal=load("terminal.json")
    for c,arms in all_cases.items():
        base=arms["never"];assert base["packets"]==terminal[c]["never"]["packets"]
        arms["terminal-8"]=terminal[c]["terminal-8"]
        for n,q in arms.items():
            for k in ("rhs","raw","multi","commits","physical","root_parents","root_ids","nested_ids","children","state_sha",
                      "decisions","source_final_serial","recurrent_final","cell_export_sha","coalescing_sha","visible","oracle_saved"):
                assert q[k]==base[k],(c,n,k)
            assert all(q["checks"].values())
            assert q["packets"]==base["packets"]-q["saved"] and q["saved"]<=q["oracle_saved"]
            assert q["chosen"]==q["actor"]["issued"] and 0<=q["chosen"]<=q["choices"]
            assert isclose(q["fept"],q["visible"]/q["packets"])
            assert isclose(q["fept_including_feedback"],q["visible"]/(q["packets"]+q["chosen"]))
            assert isclose(q["fept_charging_gate_declines"],q["visible"]/(q["packets"]+q["choices"]-q["chosen"]))
        assert arms["reinforce-8"]["chosen"] not in (0,base["choices"])
    print("Verified genuine donor-only learned decisions and complete native identities on CG, 3mm and Deriche.")


if __name__=="__main__":
    verify()
