"""Deduplicate identical source receipts across control arms while retaining every label."""
import argparse
import json
from pathlib import Path

FIELDS=("run","shape","ids","owners","epoch","birth_epochs","features","old_refs","reader_count","selected","saved_bytes","peak_bytes")


def pack(native,out,additional):
    sources=json.loads(native.read_bytes())
    for archive in additional:
        extra=json.loads(archive.read_bytes())
        for name,cases in extra.items():
            group=sources.setdefault(name,{})
            assert not group.keys() & cases.keys()
            group.update(cases)
    groups={}
    occurrences=[]
    for name,controls in sources.items():
        ids={}
        for label,row in controls.items():
            group={k:v for k,v in row.items() if k!="events"}
            actions=[]
            for e in row["events"]:
                record=json.dumps([name]+[e[k] for k in FIELDS],separators=(",",":"))
                if record not in ids:
                    ids[record]=len(occurrences)
                    occurrences.append(record)
                actions.append(ids[record])
            group["actions"]=actions
            groups.setdefault(name,{})[label]=group
    (out/"stream.json").write_text(json.dumps(groups,indent=1)+"\n")
    (out/"actions.jsonl").write_text(json.dumps(["source",*FIELDS])+"\n"+"\n".join(occurrences)+"\n")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("native",type=Path);p.add_argument("out",type=Path)
    p.add_argument("--additional",type=Path,nargs="*",default=[])
    args=p.parse_args();pack(args.native,args.out,args.additional)
