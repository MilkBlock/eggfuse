"""Charge before-enumeration singleton class actions, literal fallback and downstream materialization."""
import argparse,hashlib,json
from collections import Counter
from pathlib import Path
from runpy import run_path
from statistics import median
from time import perf_counter
HERE=Path(__file__).resolve().parent
w=run_path(str(HERE.parent/"verified-wave-execution/study.py"));src=w["source"]
gold_yield=json.loads((HERE.parent/"token-constructor-births/results.json").read_bytes())
CHECK=("rhs","raw","multi","wire_hash","commits","physical","source_pass_rhs","root_ids","root_parents",
       "nested_ids","children","state_sha","single_winners","multi_winners","cells","direct_cells","root_allocated")


def digest(rows):return hashlib.sha256(json.dumps(rows,separators=(",",":")).encode()).hexdigest()


def result(case,v,gold,actor):
    a=src.base.summarize(v,gold);assert a["aligned"] and all(a["checks"].values())
    q={i:a[i] for i in (*CHECK,"checks")}
    single=v["single"];root=v["root_recipe"];child=v["merge_child"]
    fix=dict(single["class_actor"]);intervals=fix.pop("audit_ranges");calls=fix.pop("rule_calls")
    calls_sha=digest([[a,b,c,e,f,h,j] for a,b,c,selected,e,f,h,desc,res,j in calls])
    assert sum(r[6] for r in calls)==root["emitted"][0]
    assert sum(r[7] for r in calls)==fix["issued"] and sum(r[8] for r in calls)==root["emitted"][0]-fix["internal_receipts"]
    assert all((r[7],r[8])==((1,0) if r[3] else (0,r[6])) for r in calls)
    wire_child=0
    for c in child["issued"]:
        if c["selected"]:
            fields={k:v for k,v in c.items() if k not in {"entered_allocator","allocated","reused","rejected"}}
            wire_child+=8+len(json.dumps(fields,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode())
    multi_counts=v["multi"]["counts"];mp=v["multi"]["pages"]
    assert v["multi"]["paged_tuples"]==root["emitted"][1]==multi_counts["raw_tuples"]
    wire_multi=48*mp+32*multi_counts["raw_root_slots"]
    external_single_pages=single["packed"]["pages"]-(fix["issued"]-fix["empty"])
    wire_single=64*external_single_pages+37*(root["emitted"][0]-fix["internal_receipts"])
    wire_tx=wire_single+wire_multi+wire_child+64*fix["issued"]
    inclusive={}
    for ix,(first,n) in enumerate(intervals):
        for serial in range(first,first+n):
            assert serial not in inclusive;inclusive[serial]=ix
    singles,multi=root["emitted"];selected=child["counts"][1]
    if actor:
        assert fix["issued"]==len(intervals) and 2*len(intervals)==fix["logit_evaluations"]
        assert fix["internal_receipts"]==len(inclusive) and fix["internal_receipts"]+fix["residual_receipts"]==singles
        assert fix["feedback_bytes"]==20*fix["issued"] and fix["accepted_by_action"]==fix["internal_receipts"]+fix["scalar_rejected"]
    else:assert not intervals and fix["issued"]==0
    c_universe={"class":fix["issued"],"single":singles-len(inclusive),"multi":multi,"child":selected}
    labels={r[2]:r[1] for r in root["commits"]};nested={r["allocated"] for r in child["issued"] if r["allocated"] is not None}
    b=v["constructor_births"];visible={fid for fid,t,hide in b["endpoint"] if not hide}
    retained=Counter();born=Counter();owned=0;other=0
    for fid,t,epoch,ctor,s,ancestor,cross,flags in b["rows"]:
        if not ctor or not flags&1:continue
        if not s:other+=1;continue
        owned+=1
        if fid>>32 in nested and fid&0xffffffff==0:token=("child",fid)
        elif s in inclusive:
            assert labels[s]=="single";token=("class",inclusive[s])
        else:token=(labels[s],s)
        born[token]+=1
        if fid in visible:retained[token]+=1
    groups={}
    for kind,n in c_universe.items():
        pos=[z for (t,i),z in retained.items() if t==kind]
        groups[kind]=dict(packets=n,visible=sum(pos),born=sum(z for (t,i),z in born.items() if t==kind),
                         zero=n-len(pos),one=pos.count(1),two_plus=sum(z>1 for z in pos),max=max(pos,default=0))
        assert groups[kind]["zero"]>=0
    ref=gold_yield[case]
    assert sum(retained.values())==ref["retention"]["original_visible_per_committed_root"]["births"]
    assert [singles,multi]==list(ref["issued_roots"].values()) and owned==ref["per_committed_root"]["births"]
    n=sum(c_universe.values());fb=fix["issued"]
    stats=single["adaptive_rows"]["stats"]
    q.update(public_call_sha=calls_sha,logged_calls=len(calls),external_single_pages=external_single_pages,
             canonical_wire=dict(single_literals=wire_single,unchanged_multi=wire_multi,unchanged_selected_child=wire_child,
                                 descriptors=64*fix["issued"],forward=wire_tx,feedback=fix["feedback_bytes"],both=wire_tx+fix["feedback_bytes"]),
             groups=groups,packets=n,visible=sum(retained.values()),born=owned,unowned_births=other,
             fept=sum(retained.values())/n,fept_including_feedback=sum(retained.values())/(n+fb),
             actor=fix,action_bytes=64*fix["issued"],fixed_feedback_bytes=fix["feedback_bytes"],
             original_issued_single=singles,original_issued_multi=multi,selected_children=selected,
             model_evaluations=stats["evaluations"],source_headers=stats["source_headers"],
             verifier_activity=single["work"],queue=single["packed"],recurrent_final=single["recurrence_final_bits"],
             source_final_serial=single["source_final_serial"],decisions=single["adaptive_rows"]["decision_digest"],
             cell_export_sha=digest(b["endpoint"]),coalescing_sha=digest(b["coalesced"]),
             ms=[],wall_ms=[])
    return q


def study(a):
    a.out.mkdir(parents=True,exist_ok=True);out={}
    for case in a.cases:
        pp,plans,req=src.common.config(a,case);base=w["settings"](req,a)["packed"]
        with src.base.session(a.exp/"compact-vanilla-20261121/vanilla-audit",pp) as exact:gold=exact({"audit":True})
        group={};bad={}
        with src.base.session(a.native,pp,plans) as run:
            for mode,arm in enumerate(("packed","class")):
                v=run(dict(base,audit=True,class_actor=mode,birth_ledger=True));assert "source_error" not in v,(case,arm,v.get("source_error"))
                q=group[arm]=result(case,v,gold,mode);del v
                assert all(q[k]==group["packed"][k] for k in (*CHECK,"decisions","recurrent_final","source_final_serial",
                           "queue","original_issued_single","original_issued_multi","selected_children","verifier_activity","cell_export_sha","coalescing_sha","public_call_sha","logged_calls"))
                assert q["actor"]["recurrence_digest"]==group["packed"]["actor"]["recurrence_digest"]
                print(case,arm,q["visible"],q["packets"],q["fept"],q["actor"]["issued"],q["source_headers"],q["model_evaluations"],flush=True)
            for mode,why in ((2,"checksum mismatch"),(3,"generation mismatch"),(4,"source serial mismatch")):
                v=run(dict(base,class_actor=mode));assert why in v.get("source_error","") and v["runs"]<gold["runs"],v.get("source_error")
                bad[str(mode)]={"reason":v["source_error"],"runs":v["runs"]}
            for trial in range(1+a.repeats):
                names=[(0,"packed"),(1,"class")]
                for mode,arm in names if trial%2 else reversed(names):
                    start=perf_counter();v=run(dict(base,audit=False,class_actor=mode));wall=1000*(perf_counter()-start)
                    assert v["runs"]==gold["runs"] and v["state_sha"]==gold["state_sha"]
                    q=group[arm];assert v["single"]["class_actor"]["internal_receipts"]==q["actor"]["internal_receipts"]
                    assert v["root_recipe"]["allocated"]==q["root_allocated"] and v["single"]["recurrence_final_bits"]==q["recurrent_final"]
                    if trial:q["ms"].append(v["ms"]);q["wall_ms"].append(wall)
            for q in group.values():q.update(median_ms=median(q["ms"]),median_wall_ms=median(q["wall_ms"]))
        out[case]={"arms":group,"faults":bad}
        (a.out/"results.json").write_text(json.dumps(out,indent=1)+"\n")

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for n in ("exp","native","out"):p.add_argument(n,type=Path)
    p.add_argument("--cases",nargs="+",default=["sum-bits","conjugate-gradient","3mm"]);p.add_argument("--repeats",type=int,default=4)
    a=p.parse_args();a.seed=1703;a.cap=8192
    a.policy=json.loads((HERE.parent/"speculative-allocation-policy/policy.json").read_bytes())
    a.fraction=json.loads((HERE.parent/"wave-demand-policy/policy.json").read_bytes())["models"]["fraction"]
    study(a)
