"""Same-binary factorial audit, candidate-work accounting and rule-level traffic attribution."""
import argparse,hashlib,json
from collections import Counter,defaultdict
from pathlib import Path
from runpy import run_path
from statistics import median
from time import perf_counter

HERE=Path(__file__).resolve().parent
wave=run_path(str(HERE.parent/"verified-wave-execution/study.py"))
src=wave["source"]
pair_weights=json.loads((HERE/"pair-policy.json").read_bytes())["weights"]
endpoint_ref=json.loads((HERE.parent/"token-constructor-births/results.json").read_bytes())
KEYS=("rhs","raw","commits","physical","source_pass_rhs","root_ids","root_parents","nested_ids","children",
      "state_sha","single_winners","multi_winners","cells","direct_cells","root_allocated")
SAME=(*(k for k in KEYS if k!="raw"),"raw_parent_sha","recurrence_sha","decisions","root_commit_sha","visible_sha","collision_sha",
      "owned","visible","expanded_single","expanded_multi","selected_children","child_scores","single_final",
      "rule_call_sha","recurrent","logical_root_ids")


def sha(x):return hashlib.sha256(json.dumps(x,separators=(",",":"),sort_keys=True).encode()).hexdigest()

def settings(req,a,trace=False):
    core=wave["settings"](req,a)["packed"]
    modes={"packed":(0,False),"single":(1,False),"pair":(0,True),"both":(1,True)}
    arms={}
    for name,(s,p) in modes.items():
        arms[name]=dict(core,class_actor=s,pair_actor=dict(enabled=p,weights=pair_weights,trace=trace))
    if getattr(a,"single_weights",None):
        arms["gate_pair"]=dict(arms["both"],rows=dict(core["rows"],fept_gate={"mode":"learned","weights":a.single_weights}))
    return arms


def summarize(v,gold,program,case,learned_gate):
    q=src.base.summarize(v,gold); assert q["aligned"] and all(q["checks"].values())
    s=v["single"];m=v["multi"];r=v["root_recipe"]; ch=v["merge_child"];b=v["constructor_births"]
    st=dict(s["class_actor"]);calls=st.pop("rule_calls");sranges=st.pop("audit_ranges");pg=m["pair_examples"];p=m["pair_actor"]
    roots={row[2]:row[1] for row in r["commits"]}
    assert len(roots)==q["rhs"]==q["neural_rhs"]
    postings={}
    def spans(items,category):
        for idx,(start,n,*_) in enumerate(items):
            for i in range(start,start+n):
                assert i not in postings
                postings[i]=(category,idx)
    spans(sranges,"class");spans(pg,"bucket")
    assert sum(n for _,n in sranges)==st["internal_receipts"]
    assert sum(entry[1] for entry in pg)==p["declared_lanes"]==p["receiver_postings"] and len(pg)==p["groups"]
    raw=m["counts"]["raw_tuples"];ns,nm=r["emitted"]
    assert raw==p["declared_lanes"]+p["external_residual"] and nm==p["external_residual"]
    assert ns==sum(row[6] for row in calls)
    chid=[tok for tok in ch["issued"] if tok["selected"]];cfresh={tok["allocated"] for tok in chid if tok["allocated"] is not None}
    visible={f for f,t,hidden in b["endpoint"] if not hidden}
    group_counts={"class":len(sranges),"single":ns-st["internal_receipts"],"bucket":len(pg),"multi":nm,"child":len(chid)}
    birth=Counter();kept=Counter()
    for f,t,ep,ctor,serial,anc,cross,flags in b["rows"]:
        if not(ctor and serial and flags&1):continue
        if f>>32 in cfresh and f&0xffffffff==0:k=("child",f)
        elif serial in postings:k=postings[serial]
        else:k=(roots[serial],serial)
        birth[k]+=1
        if f in visible:kept[k]+=1
    groups={}
    for k,n in group_counts.items():
        vals=[x for (label,_),x in kept.items() if label==k]
        groups[k]=dict(packets=n,owned=sum(x for (label,_),x in birth.items() if label==k),
              visible=sum(vals),zero=n-len(vals),one=vals.count(1),two_plus=sum(x>=2 for x in vals),max=max(vals,default=0))
        assert groups[k]["zero"]>=0
    total=sum(group_counts.values());num=sum(kept.values())
    assert num==endpoint_ref[case]["retention"]["original_visible_per_committed_root"]["births"]
    # Source rule is read from each native receipt at emission, including unmatched literals.
    byrule=defaultdict(Counter)
    for epoch,rid,eligible,choose,scanned,accepted,survivors,descriptor,fallback,empty in calls:
        byrule[rid]["class"]+=descriptor;byrule[rid]["single"]+=fallback
    for rid,(n,pages,refs) in m["pair_rule_issues"].items():byrule[int(rid)]["multi"]+=n
    for start,n,features,epoch,rid in pg:byrule[rid]["bucket"]+=1
    for tok in chid:byrule[tok["parent"]["rule"]]["child"]+=1
    sums=Counter()
    for g in byrule.values():sums.update(g)
    assert dict(sums)==group_counts or all(sums[k]==g for k,g in group_counts.items())
    assert sum(sums.values())==total
    families=defaultdict(Counter);rules=program["recipe"]["rules"]
    for rid,n in byrule.items():families[rules[rid]["metadata"]["source_set"]].update(n)
    top=[]
    for rid,d in sorted(byrule.items(),key=lambda it:-sum(it[1].values()))[:15]:
        rule=rules[rid];top.append(dict(rid=rid,ruleset=rule["metadata"]["source_set"],packets=dict(d),
            lhs=[a["call"].get("table") or a["call"].get("primitive") for a in rule["query"]],name=rule["metadata"]["name"][:180]))
    single_legacy_lane_decisions=sum(row[4] for row in calls if not row[3])
    gate=s["fept_gate"]
    actual_gate_calls=p["score_calls"]-p["small_or_large"]
    assert actual_gate_calls==p["groups"]+p["gate_reject"]
    # Each class chooses a mask (two logits); each fallback singleton has one threshold decision.
    # Bucket gate failures and declined children are charged; public hard-ineligible checks are separate.
    strict=st["issued"]+single_legacy_lane_decisions+actual_gate_calls+nm+len(ch["issued"])
    gate_extra=gate["calls"] if learned_gate else 0
    strict+=gate_extra
    assert strict>=total
    single_pages=s["packed"]["pages"]-(st["issued"]-st["empty"])
    single_wire=64*single_pages+37*group_counts["single"]
    external_multi_pages=sum(j[1] for j in m["pair_rule_issues"].values());external_parent_refs=sum(j[2] for j in m["pair_rule_issues"].values())
    multi_wire=48*external_multi_pages+32*external_parent_refs
    child_wire=sum(8+len(json.dumps({k:x for k,x in tok.items() if k not in {"entered_allocator","allocated","reused","rejected"}},
                        separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()) for tok in chid)
    wire=dict(class_actions=64*st["issued"],single_residual=single_wire,bucket_actions=p["wire_bytes"],multi_residual=multi_wire,
              selected_children=child_wire,receiver_feedback=st["feedback_bytes"])
    flat={k:q[k] for k in KEYS}
    flat.update(checks=q["checks"],raw_parent_sha=m["raw_sha256"],recurrence_sha=st["recurrence_digest"],decisions=s["adaptive_rows"]["decision_digest"],
        root_commit_sha=sha(r["commits"]),visible_sha=sha(b["endpoint"]),collision_sha=sha(b["coalesced"]),
        groups=groups,owned=sum(birth.values()),visible=num,expanded_single=ns,expanded_multi=raw,selected_children=len(chid),child_scores=len(ch["issued"]),
        logical_root_ids=sha([(a[0],a[1],a[2]) for a in r["commits"]]),
        single_final=s["source_final_serial"],recurrent=s["recurrence_final_bits"],rule_call_sha=sha([[i[0],i[1],i[2],i[4],i[5],i[6],i[9]] for i in calls]),
        rule_traffic={str(i):dict(v) for i,v in byrule.items() if sum(v.values())},families={k:dict(v) for k,v in families.items() if sum(v.values())},
        largest_rules=top,single_stats=st,pair_stats=p,single_gate=gate,single_logits=s["adaptive_rows"]["stats"]["evaluations"],
        residual_single_decisions=single_legacy_lane_decisions,pair_gate_evaluations=actual_gate_calls,single_dispatch_learned=gate_extra,
        approximate_visits=m["counts"]["approximate_visits"],verified_parent_tuples=m["counts"]["verified_parent_tuples"],
        packets=total,strict_decisions=strict,packets_including_feedback=total+st["issued"],fept=num/total,
        fept_including_feedback=num/(total+st["issued"]),fept_strict=num/strict,
        max_packets_for_fept_two=num//2,additional_reduction_needed=total-num//2,wire=wire,bi_bytes=sum(wire.values()),ms=[],wall_ms=[])
    return flat


def common(a):
    a.seed=1703;a.cap=8192
    a.policy=json.loads((HERE.parent/"speculative-allocation-policy/policy.json").read_bytes())
    a.fraction=json.loads((HERE.parent/"wave-demand-policy/policy.json").read_bytes())["models"]["fraction"]
    if getattr(a,"single_policy",None):
        checkpoint=json.loads(a.single_policy.read_bytes())
        a.single_weights=checkpoint["models"][a.gate_model] if "models" in checkpoint else checkpoint["weights"]
    else:a.single_weights=None


def main(a):
    a.out.mkdir(parents=True,exist_ok=True);all_results={}
    for case in a.cases:
        prog,plans,req=src.common.config(a,case);program=json.loads(prog.read_bytes())
        with src.base.session(a.exp/"compact-vanilla-20261121/vanilla-audit",prog) as orig:gold=orig({"audit":True})
        arms=settings(req,a,True);normal=settings(req,a,False);rows={};faults={}
        if getattr(a,"only_gate",False):
            assert "gate_pair" in arms
            arms={k:arms[k] for k in ("packed","gate_pair")}
        with src.base.session(a.native,prog,plans) as run:
            for mode,cfg in arms.items():
                v=run(dict(cfg,audit=True,birth_ledger=True));assert "source_error" not in v,(case,mode,v.get("source_error"))
                row=rows[mode]=summarize(v,gold,program,case,mode=="gate_pair");del v
                for k in SAME: assert row[k]==rows["packed"][k],(case,mode,k)
                print(case,mode,row["packets"],row["visible"],row["fept"],row["strict_decisions"],flush=True)
            cfg=normal["both"]
            for name,f in (("single",dict(cfg,class_actor=3)),("pair",dict(cfg,pair_actor=dict(cfg["pair_actor"],bad_bound=True)))):
                v=run(f);assert ("generation mismatch" if name=="single" else "bucket") in v.get("source_error",""),(case,name)
                faults[name]={"runs":v["runs"],"error":v["source_error"]}
            names=list(arms)
            for lap in range(1+a.repeats):
                seq=names[lap%len(names):]+names[:lap%len(names)]
                for mode in seq if lap%2 else reversed(seq):
                    t=perf_counter();v=run(normal[mode]);wall=1000*(perf_counter()-t)
                    assert v["runs"]==gold["runs"] and v["state_sha"]==gold["state_sha"]
                    assert rows[mode]["root_allocated"]==v["root_recipe"]["allocated"]
                    assert rows[mode]["pair_stats"]["groups"]==v["multi"]["pair_actor"]["groups"]
                    if lap:rows[mode]["ms"].append(v["ms"]);rows[mode]["wall_ms"].append(wall)
            for row in rows.values():row.update(median_ms=median(row["ms"]),median_wall_ms=median(row["wall_ms"]))
        all_results[case]={"arms":rows,"runs":gold["runs"],"faults":faults}
        (a.out/"results.json").write_text(json.dumps(all_results,indent=1)+"\n")

if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","out"):p.add_argument(k,type=Path)
    p.add_argument("--single-policy",type=Path);p.add_argument("--gate-model",default="reward-0");p.add_argument("--only-gate",action="store_true");p.add_argument("--cases",nargs="+",default=["sum-bits","conjugate-gradient","3mm"]);p.add_argument("--repeats",type=int,default=4)
    a=p.parse_args();common(a);main(a)
