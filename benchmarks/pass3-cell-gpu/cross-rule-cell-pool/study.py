"""Compare rule-local and compatible cross-rule private records on complete Pass 3."""
import argparse
from collections import defaultdict
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
d = HERE.parent / "sealed-lane-claims"
sys.path.insert(0, str(d))
spec = importlib.util.spec_from_file_location("sealed_study", d / "study.py")
sealed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sealed)
source = sealed.source
EQUAL_COUNTS = ("granted", "preconstructed", "fresh", "offers", "slabs", "requested", "clipped",
                "authorized_lanes", "group_pages", "bitmap_bytes", "peak_bitmap_bytes", "peak_slots",
                "header_capacity_bytes", "private_payload_capacity_bytes", "peak_private_bytes",
                "slots_before_first_verify", "offers_before_first_verify")


def configurations(req, args):
    cases = sealed.arms(req, args)
    native = cases["sealed"]
    program = Path(req["single_config"]).parent / "program.json"
    args.widths = [min(4, max(1, len(r["effects"]))) for r in json.loads(program.read_bytes())["recipe"]["rules"]]
    return {"off": cases["off"], **{name: dict(native, spec_cells=dict(native["spec_cells"], cross_pool=name))
                                   for name in ("per-rule", "shared")}}


def overlaps(spec, widths):
    grants = {(e,r):g for e,r,_,g,_,_ in spec["grants"]}
    bins = defaultdict(lambda: [[0, 0, 0] for _ in range(4)])
    local = 0
    for epoch, rid, template, _, offered, _, fresh in spec["samples"]:
        grant = grants[epoch, rid]
        assert template == rid
        row = bins[epoch][widths[rid] - 1]
        row[0] += grant
        row[1] += fresh
        row[2] += grant if offered else 0
        local += min(grant, fresh)
    counts = dict(rule_bound=local, run_bound=0, layout_bound=0, offered_layout_bound=0, offered_run_bound=0)
    by_run = []
    for epoch, rows in sorted(bins.items()):
        counts["layout_bound"] += sum(min(g,d) for g,d,_ in rows)
        counts["offered_layout_bound"] += sum(min(d,o) for _,d,o in rows)
        grant, demand, offered = map(sum, zip(*rows))
        counts["run_bound"] += min(grant,demand)
        counts["offered_run_bound"] += min(offered,demand)
        by_run.append([epoch, rows])
    digest = sha256(json.dumps(by_run, separators=(",", ":")).encode()).hexdigest()
    return counts, digest


def observe(name, native, q, rows, args):
    if name == "off":
        return
    q["staging"] = c = native["spec_cells"]["counts"]
    q["pool"] = p = native["spec_cells"]["pool"]
    q["redemption"] = sig = native["root_recipe"]["redemption"]
    bounds, q["run_layout_sha256"] = overlaps(native["spec_cells"], args.widths)
    assert all(p[k] == value for k,value in bounds.items()), (name, bounds, p)
    assert sig["attempts"] == sig["fast_accepts"] == sig["audit_comparisons"] == c["used"] > 0
    assert sig["content_reads"] == sig["fast_denials"] == 0
    assert c["payload_identity"] == p["own"] + p["borrowed"] == c["used"]
    assert c["used"] == p["layout_bound" if name == "shared" else "rule_bound"]
    assert p["rejected_layout"] == 0
    for k in sealed.ENDPOINTS:
        assert q[k] == rows["off"][k], (name,k)
    if name == "shared":
        assert q["run_layout_sha256"] == rows["per-rule"]["run_layout_sha256"]
        for k in EQUAL_COUNTS:
            assert c[k] == rows["per-rule"]["staging"][k], k


def faults(a):
    a.out.mkdir(parents=True,exist_ok=False)
    p, plans, req = source.common.config(a, "sum-bits")
    with source.base.session(a.exp / "compact-vanilla-20261121/vanilla-audit", p) as ref:
        gold = ref({"audit":True})
    cfgs = configurations(req, a)
    entries = {}
    with source.base.session(a.native,p,plans) as infer:
        for fault in ("per-rule","none","bad-layout","other-rule","reissued","stale","foreign","withheld","duplicate"):
            cfg = cfgs["per-rule" if fault == "per-rule" else "shared"]
            v = dict(cfg["spec_cells"])
            if fault == "bad-layout":
                v["cross_pool"] = fault
            if fault in ("other-rule","stale","foreign","withheld","duplicate"):
                v["fault"] = fault
            native = infer(dict(cfg,spec_cells=v,sealed_redemption=2 if fault=="reissued" else 1,audit=True))
            assert "source_error" not in native, native.get("source_error")
            q = source.base.summarize(native, gold)
            q.pop("rows")
            q.pop("work")
            for k in sealed.ENDPOINTS:
                if entries:
                    assert q[k] == entries["per-rule"][k], (fault, k)
            q["staging"] = native["spec_cells"]["counts"]
            q["redemption"] = native["root_recipe"]["redemption"]
            q["pool"] = native["spec_cells"]["pool"]
            entries[fault] = q
    (a.out/"faults.json").write_text(json.dumps(entries,indent=1)+"\n")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("exp","native","out"):
        parser.add_argument(name,type=Path)
    parser.add_argument("--faults",action="store_true")
    parser.add_argument("--cases",nargs="+",default=["conjugate-gradient","3mm"])
    parser.add_argument("--repeats",type=int,default=4)
    a=parser.parse_args()
    a.seed=1703
    a.cap=8192
    a.policy=json.loads((HERE.parent/"speculative-allocation-policy/policy.json").read_bytes())
    if a.faults:
        faults(a)
    else:
        source.study(a,configurations,lambda *fields:observe(*fields,a),None)
