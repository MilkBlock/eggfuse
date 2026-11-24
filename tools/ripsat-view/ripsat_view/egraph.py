"""Render native state rows and conditional, typed Bake layout equations as e-graphs."""
import json
from collections import defaultdict
from pathlib import Path
import shutil
import subprocess

from . import _load


class Graph:
    def __init__(self):
        self.parents = []
        self.labels = []
        self.nodes = []
        self.notes = []
        self.show_empty = True

    def value(self, label=""):
        i = len(self.parents)
        self.parents.append(i)
        self.labels.append(label)
        return i

    def root(self, i):
        while i != self.parents[i]:
            self.parents[i] = self.parents[self.parents[i]]
            i = self.parents[i]
        return i

    def union(self, a, b):
        self.parents[self.root(b)] = self.root(a)

    def node(self, op, args, result, marker=False):
        self.nodes.append((str(op), tuple(args), result, marker))

    def dot(self):
        quote = lambda s: json.dumps(str(s), ensure_ascii=False)
        members = defaultdict(list)
        for i in range(len(self.parents)):
            if self.show_empty:
                members[self.root(i)]
        for op,args,result,marker in self.nodes:
            node = op,tuple(self.root(a) for a in args),marker
            for a in node[1]:
                members[a]
            group = members[self.root(result)]
            if node not in group:
                group.append(node)
        out = ['digraph G {rankdir=BT; compound=true; bgcolor="white"; graph [fontname="Helvetica",nodesep=.22,ranksep=.45]; node [fontname="Helvetica",shape=box,style="rounded,filled",fillcolor="#eef4f2"]; edge [color="#74877e",fontsize=9];']
        for i,nodes in members.items():
            label = "e"+str(i)+"  "+self.labels[i]
            out.append('subgraph cluster_%d {label=%s; color="#a0b5a8"; style="rounded,dashed";'%(i,quote(label)))
            for j,(op,args,marker) in enumerate(nodes or [("•",(),False)]):
                out.append('n%d_%d [label=%s,fillcolor="%s"];'%(i,j,quote(op),"#ffdc8c" if marker else "#eef4f2"))
            out.append('}')
        for i,nodes in members.items():
            for j,(_,args,_) in enumerate(nodes):
                for k,a in enumerate(args):
                    # The edge targets the class boundary. The member at index
                    # zero is only Graphviz's geometric anchor.
                    clip = f',lhead=cluster_{a}' if a!=i else ''
                    out.append(f'n{i}_{j} -> n{a}_0 [label="{k}"{clip}];')
        return '\n'.join(out+['}'])


def integer_sort(sort):
    return sort in {"i8","i16","i32","i64","i128","u8","u16","u32","u64","u128","BigInt"}


def snapshot_graph(path):
    data = _load(path)
    g = Graph()
    # Marker arguments are the serializer's slot IDs. They belong to a
    # different namespace from program operands, even if both equal e.g. 1.
    marker_ops = {r["op"] for r in data["rows"] if r["op"].startswith("RipenInput")}
    slot_ids = {a for r in data["rows"] if r["op"] in marker_ops for a in r["args"]}
    operands = {a for r in data["rows"] if r["op"] not in marker_ops for a in r["args"]}
    outputs = {r["result"] for r in data["rows"]}
    index_only = slot_ids - operands - outputs
    remap = {}
    for old, v in enumerate(data["values"]):
        if old in index_only:
            continue
        i = remap[old] = g.value(v["sort"])
        if v["literal"] is not None:
            g.node("IntParam" if integer_sort(v["sort"]) else v["literal"], [], i)
    for row in data["rows"]:
        marker = row["op"] in marker_ops
        op = "RipenInput" if marker else row["op"]
        args = [] if marker else [remap[a] for a in row["args"]]
        g.node(op,args,remap[row["result"]],marker)
    return g


def layout_graph(steps, rules, constructors):
    g = Graph()
    boundary, outputs, literals = {}, {}, {}
    constructor_nodes = []
    for n,(rid,group,wires) in enumerate(steps):
        rule = rules[rid]
        slots = [g.value(s["sort"]["name"]) for s in rule["slots"]]

        def term(v):
            if "slot" in v:
                return slots[v["slot"]]
            key = v["sort"]["name"],json.dumps(v["literal"],ensure_ascii=False)
            if key not in literals:
                i = literals[key] = g.value(key[0])
                g.node("IntParam" if integer_sort(key[0]) else key[1],[],i)
            return literals[key]

        def call(op,args,out):
            g.node(op,args,out)
            if op in constructors:
                constructor_nodes.append((op,args,out))

        roles = iter(wires)
        for atom in rule["query"]:
            callee = atom["call"]
            vals = [term(v) for v in atom["args"]]
            op = callee.get("table",callee.get("primitive"))
            if "table" in callee:
                owner,pc = next(roles)
                if owner<0:
                    if pc not in boundary:
                        boundary[pc] = vals
                        for col,v in enumerate(vals):
                            g.node(f"RipenInput({pc}, {col})",[],v,True)
                    source = boundary[pc]
                else:
                    source = outputs[owner,pc]
                if len(source)!=len(vals):
                    raise ValueError("producer and consumer row arities differ")
                for src,dst in zip(source,vals):
                    g.union(src,dst)
            call(op,vals[:-1],vals[-1])
        for pc,e in enumerate(rule["effects"]):
            op=e["op"]
            args=[term(v) for v in e.get("args",[])]
            if op=="copy":
                g.union(term(e["arg"]),slots[e["dst"]])
            elif op=="union":
                g.union(*args)
            elif op in ("let","set"):
                result=slots[e["dst"]] if op=="let" else term(e["value"])
                name=e["call"].get("table",e["call"].get("primitive"))
                call(name,args,result)
                outputs[n,pc]=args+[result]
            else:
                g.notes.append(f"步骤 {n} · op {pc} · {op}")
    # Close congruence only for immutable constructors. Mutable calls are
    # observations/write equations at their own step, not global equalities.
    changed=True
    while changed:
        changed=False
        seen={}
        for op,args,out in constructor_nodes:
            key=op,tuple(map(g.root,args))
            if key in seen and g.root(seen[key])!=g.root(out):
                g.union(seen[key],out)
                changed=True
            seen[key]=out
    g.show_empty = False
    return g


def svg(g):
    binary=shutil.which("dot")
    if not binary:
        raise ValueError("Rendering requires Graphviz (dot).")
    dot=g.dot()
    proc=subprocess.run([binary,"-Tsvg"],input=dot,text=True,capture_output=True,timeout=45)
    if proc.returncode:
        raise ValueError(proc.stderr[:500])
    return proc.stdout[proc.stdout.index("<svg"):]
