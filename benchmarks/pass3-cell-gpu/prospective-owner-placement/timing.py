"""Time original Run execution, completed storage admission and normal boundary compaction."""
import argparse
import json
from pathlib import Path
from statistics import median
import subprocess
import tempfile


def main(a):
    data={}
    a.out.mkdir(parents=True,exist_ok=False)
    arms=("pooled","isolate","defer-only","multi-prefix","defer")
    for case in a.cases:
        rows={}
        program=a.exp/"old-pair-catalogs-v1"/case/"program.json"
        with tempfile.TemporaryDirectory(dir=a.out) as tmp:
            dest=Path(tmp)/"sample.json"
            for trial in range(5):
                seq=arms[trial%len(arms):]+arms[:trial%len(arms)]
                for layout in seq if trial%2 else reversed(seq):
                    subprocess.run([a.engine,program,"bench",dest,layout],check=True)
                    v=json.loads(dest.read_bytes())
                    fixed={k:v[k] for k in ("graph","runs","placement")}
                    row=rows.setdefault(layout,dict(**fixed,owner_final=v["owner_final"][:3],charge_samples=[],ms=[],maintenance_ms=[]))
                    assert all(row[k]==x for k,x in fixed.items())
                    assert v["owner_final"][:3]==row["owner_final"]
                    if trial:
                        row["charge_samples"].append(v["owner_final"][-1])
                        for field in ("ms","maintenance_ms"):row[field].append(v[field])
        for row in rows.values():
            for field in ("ms","maintenance_ms"):row["median_"+field]=median(row[field])
        data[case]=rows
        (a.out/"timing.json").write_text(json.dumps(data,indent=1)+"\n")
        print(case,{k:round(v["median_ms"],2) for k,v in rows.items()},flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("exp","engine","out"):p.add_argument(k,type=Path)
    p.add_argument("--cases",nargs="+",default=["dot-product","stable-argmax"])
    main(p.parse_args())
