"""Check factorial provenance, external and decision budgets, packet families and raw OS crossings."""
from collections import Counter
import hashlib,json
from pathlib import Path
from statistics import median
HERE=Path(__file__).resolve().parent

def read(n):return json.loads((HERE/n).read_bytes())

def check_memory(all_data,audits):
    for case,row in all_data.items():
        assert set(row["arms"])==set(audits[case]["arms"])
        base=median(x["start_kib"] for x in row["calibration"])
        rise=median(x["peak_kib"]-x["start_kib"] for x in row["calibration"])
        assert row["levels_kib"]=={str(f):base+round(f*rise) for f in (.5,.9)}
        for name,samples in row["arms"].items():
            assert len(samples)==3
            for x in samples:
                assert x["runs"]==audits[case]["runs"] and x["state_sha"]==audits[case]["arms"][name]["state_sha"]
                trace=[];t=k=0
                for dt,dk in x["trace_delta_us_kib"]:
                    t+=dt;k+=dk;trace.append((t,k))
                assert trace[0][0]==0 and trace[-1][0]==x["interval_us"] and all(b[0]>a[0] for a,b in zip(trace,trace[1:]))
                assert max(k for t,k in trace)==x["peak_kib"]
                for frac,threshold in row["levels_kib"].items():
                    first=next((t for t,k in trace if k>=threshold),None)
                    rec=x["crossings"][frac]
                    assert rec["status"]==("unreached" if first is None else ("left" if first==0 else "reached"))
                    assert rec["ms"]==(None if first is None else first/1000)


def check_execution(data,expected):
    for case,d in data.items():
        assert set(d["arms"])==expected
        base=d["arms"]["packed"]
        for name,x in d["arms"].items():
            assert all(x["checks"].values()) and all(x[k]==base[k] for k in (
                "rhs","commits","physical","cells","root_ids","root_parents","nested_ids","children","state_sha","single_winners",
                "multi_winners","raw_parent_sha","root_commit_sha","recurrence_sha","decisions","rule_call_sha","visible_sha","collision_sha",
                "owned","visible","expanded_single","expanded_multi","selected_children","logical_root_ids"))
            g=x["groups"];n=sum(v["packets"] for v in g.values());assert n==x["packets"]
            assert all(v["zero"]+v["one"]+v["two_plus"]==v["packets"] for v in g.values())
            assert sum(v["visible"] for v in g.values())==x["visible"]
            assert sum(x["wire"].values())==x["bi_bytes"]
            assert x["fept"]==x["visible"]/n
            assert x["packets_including_feedback"]==n+g["class"]["packets"]
            assert x["fept_including_feedback"]==x["visible"]/(n+g["class"]["packets"])
            assert x["strict_decisions"]==g["class"]["packets"]+x["residual_single_decisions"]+x["pair_gate_evaluations"]+g["multi"]["packets"]+x["child_scores"]+x["single_dispatch_learned"]
            assert x["fept_strict"]==x["visible"]/x["strict_decisions"]
            assert x["additional_reduction_needed"]==n-x["visible"]//2 and x["max_packets_for_fept_two"]==x["visible"]//2
            for col in ("families","rule_traffic"):
                total=Counter()
                for v in x[col].values():total.update(v)
                assert all(total[k]==g[k]["packets"] for k in g)
            assert x["expanded_single"]==g["single"]["packets"]+x["single_stats"]["internal_receipts"]
            assert x["expanded_multi"]==g["multi"]["packets"]+x["pair_stats"]["receiver_postings"]
            assert len(x["ms"])==len(x["wall_ms"])==4
        assert set(d["faults"])=={"single","pair"}
        assert all(v["runs"]<d["runs"] for v in d["faults"].values())


def main():
    for f,digest in read("manifest.json")["files"].items():
        assert hashlib.sha256((HERE/f).read_bytes()).hexdigest()==digest,f
    factorial=read("results.json");gated=read("gated.json")
    assert set(factorial)==set(gated)=={"sum-bits","conjugate-gradient","3mm"}
    check_execution(factorial,{"packed","single","pair","both"})
    check_execution(gated,{"packed","gate_pair"})
    check_memory(read("rss.json"),factorial);check_memory(read("gated-rss.json"),gated)
    for c,r in gated.items():
        assert r["arms"]["packed"]["visible_sha"]==factorial[c]["arms"]["packed"]["visible_sha"]
        assert r["arms"]["gate_pair"]["single_dispatch_learned"]>0
    print("Factored source runs, two frozen actors, donor-trained dispatcher, budgets, error controls and OS RSS traces verified.")

if __name__=="__main__":main()
