"""Measure natural old-owner supply and storage at settled source Run boundaries."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'owner-action-policy'))
from collect import action,allocation,sha
from evaluate import oracle_ref

CASES=("dot-product","stable-argmax","gemm-bias-relu","gated-state")


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    data={}
    for case in a.cases:
        group="old-pair-catalogs-v1" if case in CASES[:2] else "owner-action-fresh-v1"
        program=a.exp/group/case/"program.json"
        obs=a.exp/"repair-bake-families-20261120"/case/"observation"
        reference={k:json.loads((obs/(k+".json")).read_bytes()) for k in ("rhs","writes","resumes","state","report","events")}
        rows={}
        with tempfile.TemporaryDirectory(dir=a.out) as tmp:
            dest=Path(tmp)/"raw.json"
            for storage,decision in (("pooled","keep"),("isolate","keep"),("defer","keep"),("defer","merge"),("defer","policy")):
                policy=a.exp/"owner-action-weights-v2/regression.json" if decision=="policy" else "-"
                subprocess.run([a.engine,program,decision,dest,storage,"0","0","0",policy],check=True)
                result=json.loads(dest.read_bytes())
                oracle_ref(result,reference)
                assert all(r["event"]["kind"]=="existing_pair" for r in result["events"])
                rec=action(result)
                row=dict(source=sha(result["source_checks"]),graph=result["graph"],runs=result["runs"],
                         domain=result["domain"],placement=result["placement"],
                         final_charge=result["owner_final"],peak_charge=result["owner_peak"],
                         later_refs=sha(result["post_action_read_digests"]),later_runs=len(result["post_action_read_digests"]),
                         later_unions=result["post_action_unions"])
                if "distinct" in result:row.update(distinct=result["distinct"],graph_drop_bytes=result["graph_drop_bytes"])
                if rec:
                    e=rec["event"];assert e["new"]==e["old"] and e["issuer"]["members"]==e["old_members"]
                    assert len(set(i[1] for i in e["old_members"]))==2
                    row["action"]=dict(run=rec["source_run"],shape=e["shape"],members=e["old_members"],
                                       new_members=e["new_members"],epoch=e["old_epoch"],births=e["member_birth_epochs"],
                                       readers=len(e["old"]["external_readers"]),old_refs=sha(e["old"]),
                                       features=e["issuer"]["features"],score=e["issuer"]["score"],
                                       selected=e["issuer"]["compose"],saved_bytes=allocation(e)[0],temp_peak=allocation(e)[1],
                                       retired_owners=e["retired_owner_ids"])
                rows[storage+"/"+decision]=row
                print(case,storage,decision,row["domain"][-1],row["placement"],row["final_charge"][-1],row.get("action",{}).get("saved_bytes"),flush=True)
        data[case]=rows
        (a.out/"results.json").write_text(json.dumps(data,indent=1)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("exp","engine","out"):
        p.add_argument(key,type=Path)
    p.add_argument("--cases",nargs="+",default=CASES,choices=CASES)
    run(p.parse_args())
