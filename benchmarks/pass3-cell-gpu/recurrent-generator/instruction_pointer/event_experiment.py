"""Independent generation, frozen local-prefix control, and all-terminal diagnostic."""
import argparse
from pathlib import Path
import torch
from generation_frontier import Generator
from protocol_experiment import dump
from reachability_rollout import ReachStream
from recursive_coverage import Target, snapshot
from recursive_train import folder, read
from train_reachability import Prefix
from transaction_native import execute


def frozen(root, case, admit):
    g = Generator(root, "A", 0, case)
    g.stream_type = ReachStream
    g.dense = g.prefix_open = g.relaxed = False
    g.no_look = True
    g.terminal_open = admit
    g.adapter = Prefix().eval()
    g.adapter.load_state_dict(torch.load("run-recall/structural-reach/prefix.pt", weights_only=True))
    return g


def run(root, out, case, mode, rep, seconds):
    if mode in ("local", "admit"):
        policy = frozen(root, case, mode == "admit")
    else:
        from event_generator import EventGenerator
        policy = EventGenerator(root, case, out, mode)
    series = f"cell-events/{mode}/{rep}"
    m = execute(root, case, study=policy, seconds=seconds, series=series)
    work = root / series / (case + "-stream-multi")
    d = folder(root, case)
    path = work / "align.json"
    target = Target(read(d / "program.json"), snapshot(root,d,"reference","-",None,path)[0])
    seed = target.match(snapshot(root,d,"reference","-",0,path)[0])
    hits = target.match(read(work/"state.json")) - seed
    m['neural_tokens']=m['paid']+m['work'].get('neural_controls',0)
    trace=m.pop("trace")
    m["last_sealed_paid"]=trace[-1]["paid"] if trace else 0
    m["unsealed_paid"]=m["paid"]-m["last_sealed_paid"]
    m.update(mode=mode, repeat=rep, facts=len(hits), reference=len(target.gold)-len(seed))
    dump(out / f"{case}_{mode}_{rep}.json",m)
    print(case,rep,mode,m["termination"],m["facts"],m["exact_endpoint"],m["paid"],m["work"].get("visits",0),m["wall"],flush=True)


if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("root",type=Path)
    p.add_argument("out",type=Path)
    p.add_argument("--cases",nargs="+",required=True)
    p.add_argument("--modes",nargs="+",default=["local","admit"])
    p.add_argument("--reps",type=int,default=4)
    p.add_argument("--offset",type=int,default=0)
    p.add_argument("--seconds",type=float,default=1200)
    a=p.parse_args()
    a.out.mkdir(exist_ok=True,parents=True)
    torch.set_num_threads(1)
    exhausted=set()
    for i in range(a.offset,a.offset+a.reps):
        for case in a.cases:
            for mode in a.modes if i%2==0 else reversed(a.modes):
                key=(case,mode)
                if key in exhausted:
                    continue
                run(a.root,a.out,case,mode,i,a.seconds)
                record=read(a.out/f"{case}_{mode}_{i}.json")
                if record["termination"]=="wall_budget":
                    exhausted.add(key)
                    print(f"{case} {mode}: wall budget exhausted in Run {record['last_run']}; skipping further timing repeats",flush=True)
