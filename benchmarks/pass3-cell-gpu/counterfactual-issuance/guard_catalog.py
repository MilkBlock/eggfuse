"""Compile edges from real returned constructor rows to scalar-guarded consumers."""


def extend(recipe, base, reserved):
    tables = {t["name"] for t in recipe["tables"] if t["kind"]=="constructor"}
    consumers = {}
    for rid, rule in enumerate(recipe["rules"]):
        query=rule["query"]
        if not rule["metadata"]["seminaive"] or len(query)<2:
            continue
        row=query[0]
        table=row["call"].get("table")
        if table not in tables:
            continue
        slots = [a["slot"] for a in row["args"] if "slot" in a]
        if len(set(slots))!=len(slots) or any("slot" not in a and a.get("sort",{}).get("kind")!="i64" for a in row["args"]):
            continue
        def supported(test):
            op=test["call"]
            args=test["args"]
            return (op.get("primitive") in ("<","<=",">",">=")
                    and op.get("inputs")==["i64","i64"] and op.get("output")=="Unit"
                    and len(args)==3 and "slot" in args[2] and args[2]["slot"] not in slots
                    and all(a.get("slot") in slots or "literal" in a for a in args[:2]))
        if not all(supported(test) for test in query[1:]):
            continue
        destinations = [test["args"][2]["slot"] for test in query[1:]]
        if len(set(destinations)) == len(destinations):
            consumers.setdefault(table,[]).append((rid,row))
    paths={tuple(map(tuple,p)) for p in base["library"]}
    tails={p[0] for p in paths if len(p)==1}
    for parent,rule in enumerate(recipe["rules"]):
        for op,effect in enumerate(rule["effects"]):
            if effect["op"] not in ("set","let"):
                continue
            table=effect.get("call",{}).get("table")
            for rid,row in consumers.get(table,[]):
                operands=effect["args"]
                if effect["op"]=="set":
                    operands=[*operands,effect["value"]]
                if all("slot" in a or (i<len(operands) and ("slot" in operands[i] or
                       operands[i].get("literal")==a["literal"])) for i,a in enumerate(row["args"])):
                    tails.add((parent,op,rid))
    by_source={}
    for edge in tails:
        by_source.setdefault(edge[0],[]).append(edge)
    paths.update((edge,) for edge in tails)
    paths.update((e,t) for e in tails for t in by_source.get(e[2],[]) if (e,t)!=reserved)
    return dict(base,library=sorted(paths),row_guards=True)
