"""Project connected constructor slices from a successful source RHS.

The caller supplies the exact boundary values at the first use of each port.
Only positive constructor operations inside a single effect segment qualify.
"""
import hashlib
import json


def digest(value):
    data = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(data).hexdigest()


def project(nodes, selected, root):
    instructions = []
    returns = {}
    ports = {}
    sorts = []

    def visit(op):
        if op in returns:
            return returns[op]
        name, schema, args = nodes[op]
        inputs = []
        for sort, ref in zip(schema, args):
            if ref[0] == "op" and ref[1] in selected:
                inputs.append(["result", visit(ref[1])])
            else:
                # Literal values are supplied by the source occurrence. Sharing
                # is explicit, including repeated reads of the same SSA value.
                boundary = (sort, ref)
                if boundary not in ports:
                    ports[boundary] = len(sorts)
                    sorts.append(sort)
                inputs.append(["port", ports[boundary]])
        index = len(instructions)
        instructions.append([name, schema, inputs])
        returns[op] = index
        return index

    visit(root)
    return [sorts, instructions], list(ports), list(returns)


def cuts(nodes, root, limit):
    """Enumerate connected, rooted induced subgraphs, including shared inputs."""
    seen = set()
    todo = [frozenset([root])]
    while todo:
        selected = todo.pop()
        if selected in seen:
            continue
        seen.add(selected)
        if len(selected) > 1:
            yield selected
        if len(selected) < limit:
            children = {ref[1] for op in selected for ref in nodes[op][2]
                        if ref[0] == "op" and ref[1] in nodes}
            todo.extend(selected | {c} for c in sorted(children - selected))


def occurrences(program, max_ops=5):
    recipe = program["recipe"]
    tables = {t["name"]: t for t in recipe["tables"]}

    def operand(arg, definitions):
        if "slot" in arg:
            return definitions.get(arg["slot"], ("slot", arg["slot"]))
        return ("literal", arg["sort"]["name"], json.dumps(arg["literal"], sort_keys=True))

    for rid, rule in enumerate(recipe["rules"]):
        if rule["metadata"]["source_set"] == "initialization":
            continue
        nodes = {}
        definitions = {}
        for op, effect in enumerate(rule["effects"]):
            if effect["op"] == "copy":
                definitions[effect["dst"]] = operand(effect["arg"], definitions)
                continue
            name = effect.get("call", {}).get("table")
            if (effect["op"] != "let" or effect.get("kind") != "construct"
                    or tables[name]["kind"] != "constructor"):
                nodes.clear()
                if "dst" in effect:
                    definitions.pop(effect["dst"], None)
                continue
            schema = [s["name"] for s in tables[name]["schema"]]
            nodes[op] = (name, schema, [operand(a, definitions) for a in effect["args"]])
            definitions[effect["dst"]] = ("op", op)
            for selected in cuts(nodes, op, max_ops):
                shape, ports, operations = project(nodes, selected, op)
                yield shape, (rid, op, ports, operations)
