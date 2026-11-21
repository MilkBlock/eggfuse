"""Count native first constructor activations against root packets, committed roots and nested packets."""
import argparse, hashlib, json
from collections import Counter,defaultdict
from pathlib import Path
from runpy import run_path

HERE=Path(__file__).resolve().parent
wave=run_path(str(HERE.parent/"verified-wave-execution/study.py"))
source=wave["source"]


def hist(values):
    xs=list(values)
    bins=Counter(xs)
    return {"counts":dict(sorted(bins.items())),"denominator":len(xs),"births":sum(xs),
            "zero":bins[0],"one":bins[1],"two_plus":sum(n for k,n in bins.items() if k>=2),
            "max":max(xs,default=0),"mean":sum(xs)/len(xs) if xs else None}


def digest(x):
    return hashlib.sha256(json.dumps(x,separators=(",",":")).encode()).hexdigest()


def analyze(v,gold,exact_log,program):
    q=source.base.summarize(v,gold)
    assert q["aligned"] and all(q["checks"].values())
    rr=v["root_recipe"];roots=rr["commits"]; issued=dict(zip(("single","multi"),rr["emitted"]))
    kinds={r[2]:r[1] for r in roots}; epoch_of={r[2]:r[5] for r in roots}
    assert len(kinds)==len(roots)==q["neural_rhs"]==q["rhs"]
    # Independent winner serial ledgers use separate local IDs for each provider.
    parent={r[0]:(r[2],r[8]) for r in v["single"]["committed"]}
    parent.update({r["ordinal"]:(r["rule"],r["local_token_id"]) for r in v["multi"]["tickets"]})
    assert len(parent)==len(roots)
    ordinals={r[0]:r for r in roots}
    assert all(parent[o][0]==r[3] for o,r in ordinals.items())
    b=v["constructor_births"];rows=b["rows"];schema=v["constructor_schema"]
    split=Counter();direct=Counter();lineage=Counter();cross=Counter()
    trace=[]; ctor_table=Counter(); owned_by_cell={}
    distinct={f for f,*_ in rows};assert len(distinct)==len(rows)==b["all_activations"]
    for f,t,epoch,constructor,token,ancestor,later,flags in rows:
        running=bool(flags&1);dynamic=bool(flags&2)
        assert bool(constructor)==schema[t]
        split[("run_" if running else "initial_")+("constructors" if constructor else "relations")]+=1
        if running:trace.append((f,t))
        if not running:assert token==ancestor==0
        if not running or not constructor:continue
        ctor_table[t]+=1
        if token:
            assert token in kinds and epoch==epoch_of[token] and ancestor in kinds
            direct[token]+=1;lineage[ancestor]+=1;owned_by_cell[f]=(token,t,dynamic)
            if later:
                assert epoch!=epoch_of[ancestor]
                cross[ancestor]+=1
            if dynamic:split["nested_dynamic"]+=1
        else:split["unowned_runtime"]+=1
    # Compare each (FactRef, table) independently against source-only birth events.
    native_events=[(e[4],e[1]) for run in v["events"] for e in run if e[0]=="birth"]
    vanilla_events=[(e[4],e[1]) for run in exact_log["events"] for e in run if e[0]=="birth"]
    assert native_events==vanilla_events==trace,(len(native_events),len(vanilla_events),len(trace))
    assert sum(direct.values())+split["unowned_runtime"]==split["run_constructors"]
    assert sum(lineage.values())==sum(direct.values())
    # The fresh child Cell IDs have op zero, naming the actual newly born constructor.
    children=v["merge_child"]; candidates=children["issued"]; rawcounts=children["counts"]
    assert len(candidates)==rawcounts[0]
    active=sum(int(c["selected"]) for c in candidates)
    assert active==rawcounts[1]
    fresh=0
    for c in candidates:
        if c["allocated"] is None:continue
        fid=c["allocated"]<<32
        expected=ordinals[c["parent"]["ordinal"]][2]
        assert owned_by_cell[fid]==(expected,c["constructor"],True),(fid,expected)
        fresh+=1
    assert fresh==rawcounts[5]<=split["nested_dynamic"]
    compiled=json.loads(program.read_bytes())["recipe"]
    tables=[t["name"] for t in compiled["tables"]]
    rules=compiled["rules"]
    root_row={r[2]:r for r in roots}
    root_cells={r[0]:r[5] for r in rr["fresh"]}
    native_birth_rows=[e for run in v["events"] for e in run if e[0]=="birth"]
    ordinary_birth_rows=[e for run in exact_log["events"] for e in run if e[0]=="birth"]
    assert native_birth_rows==ordinary_birth_rows
    event_by_ref={e[4]:e for e in native_birth_rows}
    epochs=defaultdict(list)
    for r in roots:epochs[r[5]].append(r)
    classifications=Counter();unowned=Counter();by_root=defaultdict(Counter);recipients=defaultdict(Counter)
    chosen={}
    for metric,counts in (("immediate",direct),("spine_attribution",lineage)):
        serial=max(counts,key=counts.get)
        if serial:chosen[metric]=serial
    for fid,t,epoch,ctor,serial,ancestor,later,flags in rows:
        if not flags&1 or not ctor:continue
        if not serial:
            unowned[(tables[t],str(event_by_ref[fid][5]),bool(flags&2))]+=1
            continue
        loc=event_by_ref[fid][5]
        r=root_row[serial];rid=r[3]; op=fid&0xffffffff
        assert loc is not None and epochs[epoch][loc[0]][2]==serial and loc[1]==rid,(r[:6],loc)
        if flags&2:
            path="runtime_dynamic"
        else:
            effects=rules[rid]["effects"]
            e=effects[op] if op<len(effects) else {}
            assert e.get("call",{}).get("table")==tables[t] and e.get("op") in ("let","set"),(r[:6],fid,tables[t],e)
            assert root_cells.get(fid>>32)==serial,(fid,serial)
            path="typed_rhs"
        classifications[path]+=1
        if serial in chosen.values():by_root[serial][path]+=1
        if ancestor==chosen["spine_attribution"]:
            recipients[ancestor][(serial,epoch,rid,path)]+=1
    max_examples={}
    for metric,serial in chosen.items():
        r=root_row[serial];rule=rules[r[3]];metadata=rule["metadata"]
        child=recipients[serial] if metric=="spine_attribution" else {}
        max_examples[metric]={"serial":serial,"provider":r[1],"epoch":r[5],"rule":r[3],
            "ruleset":metadata["source_set"],"name_prefix":metadata["name"][:200],
            "template":r[4],"static_rhs_instructions":len(rule["effects"]),
            "immediate_paths":by_root[serial],"credited_births":lineage[serial] if metric=="spine_attribution" else direct[serial],
            "descendant_tokens_with_births":len({s for s,e,rid,path in child if s!=serial}),
            "distinct_runs_with_births":len({e for s,e,rid,path in child}) if child else 1,
            "descendant_typed_rhs":sum(n for (s,e,rid,path),n in child.items() if s!=serial and path=="typed_rhs"),
            "descendant_dynamic":sum(n for (s,e,rid,path),n in child.items() if s!=serial and path=="runtime_dynamic")}
    split.update(classifications)
    plain=exact_log["constructor_births"]
    assert b["endpoint"]==plain["endpoint"] and b["coalesced"]==plain["coalesced"]
    endpoint={f:(t,hidden) for f,t,hidden in b["endpoint"]}
    displaced=dict(b["coalesced"])
    assert len(endpoint)==len(b["endpoint"]) and len(displaced)==len(b["coalesced"])
    assert set(endpoint).isdisjoint(displaced)
    assert set(endpoint)|set(displaced)<=distinct
    kept=Counter();kept_lineage=Counter();kept_paths=Counter();status=defaultdict(Counter)
    child_visible=sum(c["allocated"] is not None and (c["allocated"]<<32) in endpoint
                      and not endpoint[c["allocated"]<<32][1] for c in candidates)
    for f,t,epoch,ctor,serial,ancestor,later,flags in rows:
        if not ctor:continue
        origin="initial" if not flags&1 else ("owned" if serial else "unowned")
        if f in endpoint:
            target_t,hidden=endpoint[f];assert t==target_t
            state="hidden" if hidden else "visible"
        elif f in displaced:
            keeper=displaced[f];visited={f}
            while keeper in displaced:
                assert keeper not in visited
                visited.add(keeper);keeper=displaced[keeper]
            if keeper in endpoint:
                assert endpoint[keeper][0]==t
                state="coalesced_to_hidden" if endpoint[keeper][1] else "coalesced_to_visible"
            else:state="coalesced_terminal_absent"
        else:state="absent_without_collision_record"
        status[origin][state]+=1
        if state=="visible" and serial:
            kept[serial]+=1;kept_lineage[ancestor]+=1
            kept_paths["runtime_dynamic" if flags&2 else "typed_rhs"]+=1
    retained=hist(kept[s] for s in kinds)
    retained.update(per_issued_root=retained["births"]/sum(issued.values()),
                    per_root_and_selected_child=retained["births"]/(sum(issued.values())+active),
                    per_root_and_all_child_decisions=retained["births"]/(sum(issued.values())+len(candidates)))
    retained_examples={}
    for key,cnts in (("immediate",kept),("spine_attribution",kept_lineage)):
        serial=max(cnts,key=cnts.get);r=root_row[serial];meta=rules[r[3]]["metadata"]
        retained_examples[key]={"serial":serial,"rule":r[3],"provider":r[1],"epoch":r[5],"ruleset":meta["source_set"],
                                "source_name_prefix":meta["name"][:150],"credited_visible":cnts[serial]}
    assert sum(x["visible"]+x["hidden"] for x in status.values())==len(endpoint)
    assert sum(kept.values())==status["owned"]["visible"]
    init={r[2] for r in roots if rules[r[3]]["metadata"]["source_set"]=="initialization"}
    retained_breakdown={k:hist(kept[s] for s in kinds if kinds[s]==k) for k in issued}
    ordinary_tokens=[s for s in kinds if s not in init]
    without_init={"committed_roots":len(ordinary_tokens),"initialization_roots":len(init),
                  "all_born":hist(direct[s] for s in ordinary_tokens),
                  "original_visible":hist(kept[s] for s in ordinary_tokens)}
    qualifying_children=Counter();kept_children=Counter()
    for c in candidates:
        if c["allocated"] is None:continue
        serial=ordinals[c["parent"]["ordinal"]][2];qualifying_children[serial]+=1
        end=endpoint.get(c["allocated"]<<32)
        if end and not end[1]:kept_children[serial]+=1
    own_remainder=[direct[s]-qualifying_children[s] for s in kinds]
    surviving_remainder=[kept[s]-kept_children[s] for s in kinds]
    assert min(own_remainder)>=0 and min(surviving_remainder)>=0
    def exclusive(xs,children):
        hh=Counter(xs);hh[1]+=children;hh[0]+=sum(issued.values())-len(kinds)+active-children
        return {"counts":dict(sorted(hh.items())),"zero":hh[0],"one":hh[1],
                "two_plus":sum(n for k,n in hh.items() if k>1),"denominator":sum(hh.values()),
                "births":sum(k*n for k,n in hh.items()),"max":max(hh)}

    bykind={k:hist(direct[s] for s in kinds if kinds[s]==k) for k in issued}
    forwards=hist(direct[s] for s in kinds);original=hist(lineage[s] for s in kinds)
    packet_count=sum(issued.values())
    from_issued=dict(forwards);from_issued["counts"]=dict(forwards["counts"])
    not_committed=packet_count-len(kinds)
    from_issued.update(denominator=packet_count,zero=forwards["zero"]+not_committed,mean=forwards["births"]/packet_count)
    from_issued["counts"][0]=from_issued["zero"]
    return {"exact":{k:q[k] for k in ("checks","rhs","neural_rhs","direct_cells","root_allocated","state_sha","root_ids","physical","root_parents","children","wire_hash","commits","multi")},
            "runs":v["runs"],"issued_roots":issued,"activations":dict(split),"all_activations":len(rows),"source_birth_digest":digest(trace),
            "per_committed_root":forwards,"per_issued_root":from_issued,"per_committed_provider":bykind,
            "per_original_spine_root":original,"spine_live_steps":b["spine_live_steps"],"cross_run_resumes":b["cross_run_steps"],
            "cross_run_constructor_births":sum(cross.values()),"producers_with_cross_run_births":len(cross),
            "retention":{"original_visible_per_committed_root":retained,"original_visible_spine_reattribution":hist(kept_lineage[s] for s in kinds),
                "by_origin":dict(status),"owned_visible_paths":kept_paths,"selected_child_original_visible":child_visible,
                "endpoint_sha":digest(b["endpoint"]),"displacements_sha":digest(b["coalesced"]),"extremes":retained_examples},
            "exclusive_issued_packet_distributions":{"constructor_births":exclusive(own_remainder,fresh),
                 "original_visible":exclusive(surviving_remainder,child_visible)},
            "per_committed_provider_visible":retained_breakdown,"without_initialization":without_init,
            "extremes":max_examples,"unowned_tables":[[t,source,d,n] for (t,source,d),n in unowned.items()],
            "table_constructor_counts":dict(ctor_table),"child_packets":{"candidates":len(candidates),"selected":active,
                "entered":rawcounts[2],"rejected":rawcounts[3],"reused":rawcounts[4],"fresh":fresh},
            "mean_per_issued_root_and_selected_child":forwards["births"]/(packet_count+active),
            "mean_per_issued_root_and_all_child_decisions":forwards["births"]/(packet_count+len(candidates)),
            "mean_per_committed_root_and_fresh_child":forwards["births"]/(len(kinds)+fresh)}


def main(a):
    a.out.mkdir(parents=True,exist_ok=True);out={}
    for case in a.cases:
        program,plan,req=source.common.config(a,case)
        cfg=wave["settings"](req,a)["packed"]
        baseline=a.exp/"compact-vanilla-20261121/vanilla-audit"
        with source.base.session(baseline,program) as exact:gold=exact({"audit":True})
        with source.base.session(a.native,program,plan) as execute:
            exact_log=execute({"baseline":True,"audit":True,"birth_ledger":True})
            assert exact_log["state_sha"]==gold["state_sha"] and exact_log["runs"]==gold["runs"]
            v=execute(dict(cfg,audit=True,birth_ledger=True))
        assert "source_error" not in v,v.get("source_error")
        q=analyze(v,gold,exact_log,program);out[case]=q;del v,gold,exact_log
        (a.out/"results.json").write_text(json.dumps(out,indent=1)+"\n")
        print(case,q["issued_roots"],q["per_committed_root"],q["child_packets"],q["activations"],flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for n in ("exp","native","out"):p.add_argument(n,type=Path)
    p.add_argument("--cases",nargs="+",default=["sum-bits","3mm","dot-product","conjugate-gradient","deriche"])
    a=p.parse_args();a.seed=1703;a.cap=8192
    a.policy=json.loads((HERE.parent/"speculative-allocation-policy/policy.json").read_bytes())
    a.fraction=json.loads((HERE.parent/"wave-demand-policy/policy.json").read_bytes())["models"]["fraction"]
    main(a)
