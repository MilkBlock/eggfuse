"""Check the natural placement census and the source and storage accounts for its real actions."""
import json
import hashlib
import argparse
from pathlib import Path
from statistics import median

HERE=Path(__file__).resolve().parent
CASES={"dot-product","stable-argmax","gemm-bias-relu","gated-state"}
LAYOUTS={"pooled","isolate","defer-only","multi-prefix","defer"}


def verify(folder):
    read=lambda p:json.loads((folder/p).read_bytes())
    first=read("first.json")
    assert set(first)=={"dot-product","stable-argmax"}
    for name,arms in first.items():
        assert len({r["source"] for r in arms.values()})==len({r["graph"] for r in arms.values()})==1
        assert all("action" not in arms[l+"/keep"] for l in ("pooled","isolate"))
        keep,merge,gate=[arms["defer/"+d] for d in ("keep","merge","policy")]
        for r in (merge,gate):
            assert r["later_refs"]==keep["later_refs"] and r["later_runs"]==keep["later_runs"]>0
            assert r["action"]["members"]==keep["action"]["members"] and r["action"]["old_refs"]==keep["action"]["old_refs"]
        assert len(merge["action"]["retired_owners"])==1 and merge["action"]["saved_bytes"]<0
        assert not gate["action"]["selected"] and gate["action"]["readers"]>0
    stream=read("stream.json")
    assert set(stream)==CASES
    header,*rows=[json.loads(line) for line in (folder/"actions.jsonl").read_text().splitlines()]
    actions=[dict(zip(header,r)) for r in rows]
    used=set()
    prepared=json.loads((HERE.parent/"owner-action-policy/policies.json").read_bytes())["regression"]
    natural=read("natural-regression.json")
    assert set(natural["training"])=={"dot-product","stable-argmax"}
    for case,train in natural["training"].items():
        donor=stream[case]["defer/merge"]
        pairs=[(actions[i]["features"],actions[i]["saved_bytes"]) for i in donor["actions"]]
        assert train["events"]==len(pairs) and train["source"]==donor["source_sha"]
        assert train["samples_sha"]==hashlib.sha256(json.dumps(pairs,separators=(",",":")).encode()).hexdigest()
    for name,arms in stream.items():
        observed={l+"/keep" for l in LAYOUTS}|{l+"/"+d for l in ("defer","defer-only","multi-prefix") for d in ("merge","policy")}
        if name in ("gemm-bias-relu","gated-state"):
            observed.add("defer/retrained")
        assert set(arms)==observed
        if name in first:
            assert arms["pooled/keep"]["source_sha"]==first[name]["pooled/keep"]["source"]
        assert len({r["source_sha"] for r in arms.values()})==len({r["graph"] for r in arms.values()})==1
        assert arms["pooled/keep"]["distinct"]==0
        for label,row in arms.items():
            hits=[actions[i] for i in row["actions"]];used.update(row["actions"])
            assert len(hits)==row["issued"]<=row["distinct"]<=row["domain"][-1]
            assert sum(r["selected"] for r in hits)==row["selected"]
            assert sum(r["saved_bytes"] for r in hits)==row["immediate_bytes"]
            assert row["final_charge"][-1]==sum(row["final_charge"][3:6])<=row["peak_charge"][-1]
            assert row["graph_drop_bytes"]>=row["final_charge"][-1]>0
            assert len({tuple(map(tuple,r["owners"])) for r in hits})==len(hits)
            for e in hits:
                assert e["source"]==name and e["reader_count"]>0 and len({owner for _,owner in e["owners"]})==2
                assert e["ids"]==[i for i,_ in e["owners"]]
                assert max(e["birth_epochs"])<=e["epoch"] and e["run"]<=row["runs"]
                assert len(e["old_refs"])==64 and len(e["features"])==8
                if not e["selected"]:assert e["saved_bytes"]==e["peak_bytes"]==0
                if label.endswith(("/policy","/retrained")):
                    p=natural if label.endswith("/retrained") else prepared
                    score=p["intercept"]
                    for x,w in zip(e["features"],p["weights"]):score+=x*w
                    assert e["selected"]==(score>0)
                if label.endswith("/merge"):assert e["selected"]
                if label.endswith("/keep"):assert not e["selected"]
        for layout in ("defer","multi-prefix","defer-only"):
            ctrl=arms[layout+"/keep"]
            for tag,row in arms.items():
                if not tag.startswith(layout+"/"):
                    continue
                assert row["first_read_digest"]==ctrl["first_read_digest"]
                assert row["first_read_runs"]==ctrl["first_read_runs"]
                assert row["first_subsequent_unions"]==ctrl["first_subsequent_unions"]
                if ctrl["actions"]:
                    first_candidate=actions[ctrl["actions"][0]]
                    treatment=actions[row["actions"][0]]
                    assert all(first_candidate[k]==treatment[k] for k in ("run","old_refs","owners","features"))
    assert used==set(range(len(actions)))
    from returns import report
    assert report(folder)==read("returns.json")
    return stream


def timings(folder):
    sources=verify(folder)
    samples=json.loads((folder/"timing.json").read_bytes())
    assert set(samples)=={"dot-product","stable-argmax"}
    for case,arms in samples.items():
        assert set(arms)==LAYOUTS
        for layout,row in arms.items():
            ref=sources[case][layout+"/keep"]
            for k in ("placement","runs","graph"):
                assert row[k]==ref[k]
            # Capacity growth of auxiliary source containers can vary between processes.
            assert row["owner_final"][:3]==ref["final_charge"][:3]
            assert row["median_ms"]==median(row["ms"]) and row["median_maintenance_ms"]==median(row["maintenance_ms"])
            assert len(row["ms"])==len(row["maintenance_ms"])==4 and all(x>y>0 for x,y in zip(row["ms"],row["maintenance_ms"]))
    return samples


if __name__=="__main__":
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--folder",type=Path,default=HERE)
    folder=cli.parse_args().folder
    print("Verified",len(verify(folder)),"full source streams and natural owner actions")
    if (folder/"timing.json").exists():
        print("Verified",len(timings(folder)),"source-aligned placement timing matrices")
