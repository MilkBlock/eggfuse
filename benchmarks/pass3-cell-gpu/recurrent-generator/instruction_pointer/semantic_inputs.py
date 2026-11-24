"""Compile constructor witnesses from query/effect IR by forward symbolic evaluation.

Source addresses designate named receipts. Any reused receipt is still verified on
its consuming Run. Equality of keys alone never creates an external witness.
"""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

from ripsat_layout import queries
from ripsat_replay import unpack


def literal(arg):
    return ("literal", json.dumps(arg, sort_keys=True))


def compile_unit(unit, rules, constructors):
    # Each symbolic name is local to this layout. Receipt identity and the
    # scalar value returned by a constructor are deliberately separate.
    rows = {}
    epochs = {}
    substitutions = {}
    derived_values = 0
    key_only = set()
    for step,(rid,group,wires) in enumerate(unit):
        rule = rules[rid]
        atoms = queries(rule)
        known = {}
        work = []
        def value(a):
            return known.get(a["slot"]) if "slot" in a else literal(a)
        def bind(args, fields):
            for arg, field in zip(args,fields,strict=True):
                if "slot" in arg:
                    known.setdefault(arg["slot"],field)
        def remember(a,tab,arity):
            if a not in rows:
                rows[a]=(tab,tuple(("field",a,j) for j in range(arity)))
            return rows[a][1]

        for atom,src in zip(atoms,wires,strict=True):
            src=substitutions.get(src,src)
            tab=atom["call"]["table"]
            if src in rows or step==0 or src[0]>=0:
                bind(atom["args"],remember(src,tab,len(atom["args"])))
            else:
                work.append((atom,src))
        while work:
            progress=False
            for atom,src in work[:]:
                tab=atom["call"]["table"]
                args=atom["args"]
                keys=tuple(value(a) for a in args[:-1])
                if src in rows:
                    candidate=src
                elif src in substitutions:
                    candidate=substitutions[src]
                elif None not in keys and tab in constructors:
                    key_only.add(src)
                    candidate=next((k for k,(t,v) in rows.items() if t==tab and v[:-1]==keys
                                    and (k[0]<0 or epochs[k]<group)),None)
                else:
                    candidate=None
                if candidate is not None:
                    if src!=candidate:
                        substitutions[src]=candidate
                    bind(args,rows[candidate][1])
                    work.remove((atom,src))
                    progress=True
            if not progress and work:
                atom,src=work.pop(0)
                bind(atom["args"],remember(src,atom["call"]["table"],len(atom["args"])))

        for pc,e in enumerate(rule["effects"]):
            if e["op"]=="copy":
                term=value(e["arg"])
                if term is not None:
                    known[e["dst"]]=term
            elif e["kind"]=="construct":
                tab=e["call"]["table"]
                keys=tuple(value(a) for a in e["args"])
                src=(step,pc)
                if None not in keys:
                    fields=keys+(("ctor",tab,keys),)
                    derived_values+=1
                else:
                    fields=remember(src,tab,len(keys)+1)
                rows[src]=(tab,fields)
                epochs[src]=group
                known[e["dst"]]=fields[-1]
    result=tuple((r,g,tuple(substitutions.get(src,src) for src in wires)) for r,g,wires in unit)
    # Intern external IDs again since native receivers expect compact boundaries.
    ext={}
    compact=tuple((r,g,tuple((i,s) if i>=0 else (-1,ext.setdefault(s,len(ext))) for i,s in wires))
                  for r,g,wires in result)
    return compact, len(substitutions), derived_values, len(key_only-substitutions.keys())


def audit(program, layouts, out):
    rules=program["recipe"]["rules"]
    constructors={t["name"] for t in program["recipe"]["tables"] if t["kind"]=="constructor"}
    counts=Counter()
    rewrites={}
    rows=[]
    for i,l in enumerate(layouts):
        new,saved,values,mere_keys=compile_unit(l,rules,constructors)
        external={s for _,_,w in l for p,s in w if p<0}
        atom_refs=sum(len(w) for _,_,w in l)
        row=dict(template=i,steps=len(l),effect_instructions=sum(len(rules[r]["effects"]) for r,_,_ in l),
                 parent_roles=atom_refs,external_before=len(external),external_after=len(external)-saved,
                 internal_reads=sum(p>=0 for _,_,w in l for p,s in w),eliminated=saved,
                 proved_constructor_values=values,known_keys_without_receipt=mere_keys,
                 publication_crossings=len({g for _,g,_ in l})-1)
        counts.update({k:v for k,v in row.items() if k!="template"})
        if saved:
            rewrites[i]=new
        rows.append(row)
    out.mkdir(parents=True,exist_ok=True)
    with (out/"inputs.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n")
        w.writeheader();w.writerows(rows)
    (out/"rewrites.json").write_text(json.dumps(rewrites,separators=(",",":"))+"\n")
    print(json.dumps(dict(templates=len(layouts),changed=len(rewrites),totals=counts),indent=2))


def observed_ready(root, donor, layouts, out):
    from ripsat_layout import capture

    changes = json.loads((out / "rewrites.json").read_bytes())
    candidates = {layouts[int(i)] for i in changes}
    results = {}
    for name in ("sum", "dot", "fact", "loopfact", "sum-divisors"):
        _, _, roots, _ = capture(root / name, donor, 10, grow_consumers=True)
        ready = Counter()
        for choices in roots.values():
            for layout, occurrences in choices.items():
                if layout in candidates:
                    ready[layout] += sum(ok and first for _,ok,first,_ in occurrences)
        results[name] = dict(ready_layouts=len(+ready), ready_instances=ready.total())
    (out / "observations.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__=="__main__":
    p=argparse.ArgumentParser()
    for name in ("program","catalog","out"):
        p.add_argument(name,type=Path)
    p.add_argument("--tapes", type=Path)
    a=p.parse_args()
    donor=json.loads(a.program.read_bytes())
    layouts=unpack(json.loads(a.catalog.read_bytes())["layouts"])
    audit(donor,layouts,a.out)
    if a.tapes:
        observed_ready(a.tapes,donor,layouts,a.out)
