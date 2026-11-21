"""Normal sum-bits Bake + cached study smoke. No training or held-out benchmark matrix."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from runpy import run_path
import subprocess

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
bridge = run_path(str(HERE/"ripsat_bridge.py"))
cli = run_path(str(HERE/"check_publication_entry.py"))["cli"]

def read(path):
    return json.loads(path.read_bytes())

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(a):
    a.out.mkdir(parents=True, exist_ok=False)
    inputs = a.exp/"compact-holdouts-20261121-v1"
    target = inputs/"sum-bits-1703/program.json"
    donors = {k: inputs/(k+"-1703")/"program.json" for k in ("dot-product","jacobi-1d")}
    cmd = [HERE/"bake.py", "ripsat", "--evidence", BENCH/"ripsat-donor-evidence/evidence.json", "--target", target]
    for donor,path in donors.items():
        cmd.extend(("--donor",f"{donor}={path}"))
    artifacts={}
    paths={}
    for name,flags in (("let",[]),("direct",["--set-publication"]),("higher",["--higher-cell"])):
        paths[name]=a.out/(name+".json")
        cli([*cmd,*flags,"--out",paths[name]])
        artifacts[name]=read(paths[name])
    plain, direct, high=(artifacts[n] for n in ("let","direct","higher"))
    assert plain["strict_named"]==direct["strict_named"]==high["strict_named"]
    assert "higher_cell_program" not in plain and "higher_cell_program" not in direct
    assert "set_publication_authorization" not in plain
    assert direct["set_publication_authorization"]==high["set_publication_authorization"]==read(BENCH/"ripsat-publication-chain/sum-bits.json")
    higher=high["higher_cell_program"]
    assert higher["strict_named"]["set_publication"]==direct["set_publication_authorization"]["strict_named"]["set_publication"]
    assert higher["strict_named"]["higher_cell"]==dict(bridge["HIGHER_ABI"],target_sha256=sha(target))
    support=direct["set_publication_authorization"]["support"][0]["target_static"]
    assert higher["request_inputs"]["columns"]==support["columns"] and higher["request_inputs"]["sorts"]==support["sorts"]
    assert list(higher["reply_branches"])==bridge["HIGHER_ABI"]["branches"]
    assert higher["reply_branches"]["fresh"]["consumer_rule"]==higher["request_inputs"]["path"][1][2]
    assert all(higher["reply_branches"][k]["internal_terminal"] is False for k in ("no-new-fact","stale"))

    def study(native,cache,label,flags=()):
        return [BENCH/"filtered-explicit-parent/study.py",a.exp,native,BENCH/"filtered-explicit-parent/library.json",
                a.out/label,"--cases","sum-bits","--repeats","1","--ripsat-library",cache,*flags]
    refusals={}
    def refusal(name,command,why):
        cli(command,why)
        assert not (a.out/name/"results.json").exists()
        refusals[name]=why
    refusal("old-native",study(a.old_native,paths["higher"],"old-native",["--higher-cell"]),"requires the native resolve-constructor-set capability")
    for name in ("let","direct"):
        label="no-higher-"+name
        refusal(label,study(a.native,paths[name],label,["--higher-cell"]),"cache has no higher Cell program")
    for field in ("branch","input","grant","target"):
        tampered=copy.deepcopy(high)
        if field=="branch":tampered["higher_cell_program"]["reply_branches"]["no-new-fact"]["internal_terminal"]=True
        elif field=="input":tampered["higher_cell_program"]["request_inputs"]["columns"][0]=["slot",999]
        elif field=="grant":tampered["bake_inputs"]["higher_cell"]=False
        else:tampered["target_sha256"]="0"*64
        f=a.out/("bad-"+field+".json");f.write_text(json.dumps(tampered));label="tamper-"+field
        why={"grant":"inconsistent cached higher Cell authorization","target":"different target"}.get(field,"disagrees with its checked build evidence")
        refusal(label,study(a.native,f,label,["--higher-cell"]),why)
    # A newer cache must not implicitly activate either opt-in on an older direct-Set reader.
    cli(study(a.old_native,paths["higher"],"default"))
    ordinary=read(a.out/"default/results.json")["sum-bits"]["arms"]
    assert "ripsat_higher" not in ordinary and "ripsat_set" not in ordinary
    cli(study(a.old_native,paths["higher"],"direct-only",["--set-publication"]))
    direct_arms=read(a.out/"direct-only/results.json")["sum-bits"]["arms"]
    assert "ripsat_higher" not in direct_arms and direct_arms["ripsat_set"]["stats"]["set_publication"]["confirmed"]>0
    cli(study(a.native,paths["higher"],"cached",["--higher-cell"]))
    all_arms=read(a.out/"cached/results.json")["sum-bits"]["arms"]
    ht=all_arms["ripsat_higher"];dt=all_arms["ripsat_set"]
    assert ht["aligned"] and all(ht["checks"].values())
    for k in ("state_sha","rhs","checks","root_ids","nested_ids","commits",
              "physical","birth_digest","end_digest","selected_children","visible","packets"):
        assert ht[k]==dt[k],k
    assert ht["higher_work"]["requests"]>0 and ht["higher_work"]["transferred"]>0
    work=ht["higher_work"]
    assert work["terminal_commits"]==ht["by_depth"][1][2]>0
    assert work["queued_requests"]==work["requests"] and work["retired_no_result"]>0
    assert work["retired_fresh"]+work["retired_stale"]+work["retired_no_result"]==work["requests"]
    # Challenge both request-provided target fields together through the actual persistent binary.
    # A native target check based only on mutual equality of the fields would accept this.
    ctx=run_path(str(BENCH/"filtered-explicit-parent/study.py"))
    args=argparse.Namespace(exp=a.exp,out=a.out,seed=1703,cap=8192)
    prog,plans,req=ctx["strict"].src.config(args,"sum-bits")
    def native_config():
        return dict(ctx["filtered"](req,copy.deepcopy(higher["strict_named"])),source_sha256=sha(prog))
    config=native_config();foreign="0"*64
    config["source_sha256"]=foreign
    config["strict_named"]["set_publication"]["target_sha256"]=foreign
    config["strict_named"]["higher_cell"]["target_sha256"]=foreign
    q=subprocess.run([a.native,prog,plans],input=json.dumps(config)+"\n",text=True,capture_output=True)
    err=q.stderr
    if q.returncode==0:err=read_result_error(q.stdout)
    assert "target" in err.lower(),(q.returncode,err[:240])
    refusals["coordinated-native-target"]="rejected by actual loaded program digest"
    broken=native_config()
    broken["strict_named"]["higher_cell"]["request"]="select-independent-parent"
    q=subprocess.run([a.native,prog,plans],input=json.dumps(broken)+"\n",text=True,capture_output=True)
    msg=q.stderr if q.returncode else read_result_error(q.stdout)
    assert "incorrect higher Cell protocol" in msg,msg
    refusals["native-unprovided-request"]="request kind rejected by the higher Cell ABI"
    receipt={"schema":"eggfuse-higher-cell-cli-checks/v1","case":"sum-bits","target_sha256":sha(target),"native_sha256":sha(a.native),
        "native_capability":bridge["HIGHER_ABI"],"higher":ht["higher_work"],"direct_confirmed":dt["stats"]["set_publication"]["confirmed"],
        "source_checks":ht["checks"],"signed_roots_and_children":ht["packets"],"final_visible_origins":ht["visible"],
        "physical_root_digest":ht["physical"],"final_graph_sha256":ht["state_sha"],"default_arm_enabled":False,"direct_set_unchanged":True,
        "ports":higher["request_inputs"],"branches":higher["reply_branches"],"refusals":refusals}
    (a.out/"receipt.json").write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps(receipt["higher"]),len(refusals),"negative controls")


def read_result_error(stdout):
    return json.loads(stdout).get("source_error","")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("exp","native","old_native","out"):p.add_argument(key,type=Path)
    run(p.parse_args())
