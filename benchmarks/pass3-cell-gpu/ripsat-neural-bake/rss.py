"""Fresh-process inference-window RSS for the frozen leaf, trace, RipSat and union arms."""
import argparse
from collections import Counter
from hashlib import sha256
import json
import mmap
from pathlib import Path
from runpy import run_path
from statistics import median
import struct
import subprocess
import tempfile
import threading

HERE = Path(__file__).resolve().parent
driver = run_path(str(HERE / "study.py"))
observer = run_path(str(HERE.parent / "verified-wave-rss/measure.py"))["observer"]
METHODS = ("leaf", "trace", "ripsat", "union")
CALIBRATION = HERE.parent / "verified-wave-rss/results.json"


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def measure(native, files, cfg, sampled, expected):
    """Keep samples outside the target. Only the two marker RSS values are target reads."""
    with tempfile.TemporaryDirectory() as directory:
        marker = Path(directory) / "window"
        marker.write_bytes(bytes(4096))
        with marker.open("r+b") as handle, mmap.mmap(handle.fileno(), 4096) as mem:
            samples, errors, done = [], [], threading.Event()
            req = dict(cfg, rss_file=str(marker)) if sampled else cfg
            with subprocess.Popen([native, *files], stdin=subprocess.PIPE, stdout=subprocess.PIPE) as child:
                thread = None
                if sampled:
                    thread = threading.Thread(target=observer, args=(child.pid, mem, done, samples, errors))
                    thread.start()
                try:
                    out, _ = child.communicate((json.dumps(req) + "\n").encode())
                finally:
                    done.set()
                    if thread:
                        thread.join()
                if child.returncode != 0:
                    raise RuntimeError(f"{native} exit code {child.returncode}")
            result = json.loads(out)
            assert "source_error" not in result, result.get("source_error")
            counts = (result["strict_named"] or {}).get("counts", {})
            endpoints = dict(runs=result["runs"], source=result["state_sha"], emitted=result["root_recipe"]["emitted"],
                             internal=counts.get("source_commits", 0), audit_score_inputs=counts.get("audit_score_inputs", 0))
            for key in ("runs", "source", "emitted", "internal"):
                assert endpoints[key] == expected[key], (key, endpoints, expected[key])
            assert endpoints["audit_score_inputs"] == 0
            row = dict(ms=result["ms"], endpoints=endpoints)
            if sampled:
                assert not errors, errors
                start, before, end, after = struct.unpack_from("4Q", mem)
                assert start < end and before and after
                assert abs((end - start) / 1e6 - row["ms"]) < max(2, row["ms"] * .01)
                observed = [(start, before), *((v[0], v[1]) for v in samples if start < v[0] < end), (end, after)]
                row["trace"] = [[round((t-start)/1000), n//1024] for t,n in observed]
                assert len(row["trace"]) >= 5
            return row


def crossing(trace, level):
    if trace[0][1] >= level:
        return ["left", 0], 0
    for prev, current in zip(trace, trace[1:]):
        if current[1] >= level:
            return ["reached", current[0]], current[0] - prev[0]
    return ["unreached", None], None


def summarize(rows):
    summary = {key: median(row[key] for row in rows) for key in
               ("sampled_ms","plain_ms","start_kib","peak_kib","rise_kib","time_to_peak_us","sample_count","max_gap_us","paired_overhead_pct")}
    summary["crossings"] = {}
    for key in ("increment","absolute"):
        outcomes = [r["crossings"][key] for r in rows]
        reached = [t for state,t in outcomes if state=="reached"]
        summary["crossings"][key] = {"outcomes":dict(Counter(state for state,_ in outcomes)),
            "reached_median_us":median(reached) if reached else None}
    return summary


def verify(data, semantic, calibration):
    for case,case_data in data.items():
        levels = calibration[case]["thresholds_kib"]["0.9"]
        assert case_data["thresholds_kib"] == levels and set(case_data["arms"]) == set(METHODS)
        assert len(case_data["order"]) == 32
        for name,rows in case_data["arms"].items():
            assert len(rows) == 4
            assert case_data["summary"][name] == summarize(rows)
            for trial,r in enumerate(rows):
                trace = r["trace"]; before = trace[0][1]
                assert r["sample_count"] == len(trace) >= 5 and trace[0][0]==0
                assert all(b[0]>a[0] for a,b in zip(trace,trace[1:]))
                assert r["start_kib"] == before and r["peak_kib"] == max(n for _,n in trace)
                want = semantic[case]["arms"][name]
                assert all(want["checks"].values())
                assert all(r["endpoints"][key] == want[key] for key in ("runs","source","emitted","internal"))
                assert r["endpoints"]["audit_score_inputs"] == 0 and r["control_endpoints"]==r["endpoints"]
                for metric,level in (("absolute",levels[0]),("increment",before+levels[1])):
                    value, gap = crossing(trace,level)
                    assert r["crossings"][metric]==value and r["crossing_gap_us"][metric]==gap
                flags = [flag for lap,arm,flag in case_data["order"] if lap==trial and arm==name]
                assert set(flags)=={True,False} and len(flags)==2
            assert len(set([arm for lap,arm,flag in case_data["order"] if lap==n][::2].index(name) for n in range(4)))==4


def run(a):
    a.out.mkdir(parents=True,exist_ok=False)
    archive = json.loads(a.study.read_bytes())
    trace_lib = json.loads(a.trace_library.read_bytes())
    calibration = json.loads(CALIBRATION.read_bytes())
    out = {}
    for case in a.cases:
        pp, plans, req = driver["src"].config(a,case)
        path = a.study.parent / (case+"-ripsat.json")
        artifact = driver["bake"].ripsat["load_checked"](path,pp)
        specs, counts = driver["options"](driver["candidates"](trace_lib,pp),artifact["strict_named"])
        assert all(archive[case]["library"][k]==v for k,v in counts.items())
        cfgs = {}
        for k in METHODS:
            cfg = driver["bake"].settings(req,dict(specs[k],partial=True))
            cfgs[k]=dict(cfg,rows=dict(cfg["rows"],scalar_certificates=True),integral_packets=False,integral_root="off")
        levels=calibration[case]["thresholds_kib"]["0.9"]
        groups={k:[] for k in METHODS};order=[]
        for trial in range(4):
            for k in METHODS[trial:]+METHODS[:trial]:
                pair = {}
                flags = (True,False) if (trial+METHODS.index(k))%2==0 else (False,True)
                for flag in flags:
                    pair[flag]=measure(a.native,(pp,plans),cfgs[k],flag,archive[case]["arms"][k])
                    order.append([trial,k,flag])
                sampled, plain=pair[True],pair[False];trace=sampled["trace"];start=trace[0][1];peak=max(n for _,n in trace)
                row=dict(trace=trace,sampled_ms=sampled["ms"],plain_ms=plain["ms"],sample_count=len(trace),
                    start_kib=start,peak_kib=peak,rise_kib=peak-start,time_to_peak_us=next(t for t,n in trace if n==peak),
                    max_gap_us=max(b[0]-a[0] for a,b in zip(trace,trace[1:])),endpoints=sampled["endpoints"],control_endpoints=plain["endpoints"],
                    paired_overhead_pct=100*(sampled["ms"]/plain["ms"]-1),crossings={},crossing_gap_us={})
                for metric,level in (("absolute",levels[0]),("increment",start+levels[1])):
                    row["crossings"][metric],row["crossing_gap_us"][metric]=crossing(trace,level)
                groups[k].append(row)
            print(case,trial+1,[(k,groups[k][-1]["crossings"]["increment"]) for k in METHODS],flush=True)
        out[case]=dict(thresholds_kib=levels,arms=groups,summary={k:summarize(v) for k,v in groups.items()},order=order,
            hashes={"native":digest(a.native),"semantic_results":digest(a.study),"effective_library":digest(path),
                "trace_library":digest(a.trace_library),"target_program":digest(pp),"historical_calibration":digest(CALIBRATION)})
        verify({case:out[case]},archive,calibration)
        (a.out/"rss.json").write_text(json.dumps(out,separators=(",",":"))+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","native","trace_library","study","out"):
        p.add_argument(k,type=Path)
    p.add_argument("--cases",nargs="+",default=["sum-bits","3mm"])
    run(p.parse_args())
