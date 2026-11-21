"""Sample the same two native processes after warmup; distinguish executor and request costs."""
import argparse
import json
import subprocess
from pathlib import Path
from runpy import run_path

HERE=Path(__file__).resolve().parent
driver=run_path(str(HERE.parent/"verified-wave-execution/study.py"))
source=driver["source"]


def record(binary,files,request,path,seconds):
    cmd=(json.dumps(request)+"\n").encode()
    with subprocess.Popen([str(binary),*map(str,files)], stdin=subprocess.PIPE,stdout=subprocess.PIPE) as svc:
        def request_once():
            svc.stdin.write(cmd)
            svc.stdin.flush()
            data=json.loads(svc.stdout.readline())
            assert "source_error" not in data
            return data
        warm=request_once()
        with subprocess.Popen(["/usr/bin/sample",str(svc.pid),str(seconds),"1","-file",str(path)],
                              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL) as watch:
            observed=[]
            while watch.poll() is None:
                v=request_once()
                assert (v["state_sha"],v["runs"])==(warm["state_sha"],warm["runs"])
                observed.append(v["ms"])
            assert watch.returncode==0 and path.is_file()
        svc.stdin.close()
    return {"state_sha":warm["state_sha"],"runs":warm["runs"],"samples_ms":observed,"phases":warm.get("phases_ms")}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","out"):
        p.add_argument(k,type=Path)
    p.add_argument("--cases",nargs="+",default=["3mm","deriche"])
    p.add_argument("--seconds",type=int,default=7)
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    a.seed=1703
    a.cap=8192
    a.policy=json.loads((HERE.parent/"speculative-allocation-policy/policy.json").read_bytes())
    a.fraction=json.loads((HERE.parent/"wave-demand-policy/policy.json").read_bytes())["models"]["fraction"]
    results={}
    for case in a.cases:
        prog,plan,req=source.common.config(a,case)
        arm=driver["settings"](req,a)["packed"]
        pair={}
        for name,b,fs,request in (("vanilla",a.exp/"compact-vanilla-20261121/vanilla",[prog],{}),
                                   ("packed",a.native,[prog,plan],arm)):
            pair[name]=record(b,fs,request,a.out/(case+"-"+name+".sample"),a.seconds)
        assert pair["vanilla"]["state_sha"]==pair["packed"]["state_sha"]
        results[case]=pair
        (a.out/"summary.json").write_text(json.dumps(results,indent=1)+"\n")

if __name__=="__main__":
    main()
