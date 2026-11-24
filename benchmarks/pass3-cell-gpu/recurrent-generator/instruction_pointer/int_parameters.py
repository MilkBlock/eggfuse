"""Bind structural Bake identities to concrete, executable rule instances."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


FORMAT = "typed-int-parameters-v1"
INT_SORTS = frozenset(f"{prefix}{width}" for prefix in ("i", "u")
                      for width in (8, 16, 32, 64, 128)) | {"BigInt"}


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


def integer_operand(arg):
    return "literal" in arg and arg["sort"]["name"] in INT_SORTS


class RuleShape:
    def __init__(self, rule, merges):
        parameters = {}
        markers = {}

        def walk(item, marker=False):
            if isinstance(item, list):
                return [walk(elem, marker and i == 0) for i, elem in enumerate(item)]
            if not isinstance(item, dict):
                return item
            if integer_operand(item):
                pool = markers if marker else parameters
                key = item["sort"]["name"], item["literal"]
                return {"sort": item["sort"], "boundary" if marker else "int_param":
                        pool.setdefault(key, len(pool))}
            is_marker = item.get("call", {}).get("table", "").startswith("RipenInput")
            return {k: walk(v, is_marker and k == "args") for k, v in sorted(item.items())}

        # Query and effects define the dataflow. Source pretty-print and compiler
        # temporary names can themselves contain decimal payloads.
        metadata = {k: v for k, v in rule["metadata"].items() if k != "name"}
        slots = [{k: v for k, v in s.items() if k != "name"} for s in rule["slots"]]
        tables = sorted({op["call"]["table"] for op in rule["effects"] if op["op"] == "set"})
        body = [metadata, slots, rule["query"], rule["effects"],
                [merges[t] for t in tables if t in merges]]
        self.shape = walk(body)
        self.key = digest(self.shape)
        self.values = tuple(parameters)
        self.markers = tuple(markers)

    def instantiate(self, values, markers):
        """Rebind typed operands into executable IR, including guard and merge operands."""
        def restore(item):
            if isinstance(item, list):
                return [restore(v) for v in item]
            if not isinstance(item, dict):
                return item
            for key, bindings in (("int_param", values), ("boundary", markers)):
                if key in item:
                    sort, payload = bindings[item[key]]
                    if sort != item["sort"]["name"]:
                        raise ValueError("wrong sort for bound parameter")
                    return {"literal": payload, "sort": item["sort"]}
            return {k: restore(v) for k, v in item.items()}
        return restore(self.shape)


class StructuralBake:
    def __init__(self, program):
        merges = {m["table"]: m for m in program["merge_programs"]["programs"]}
        self.rules = [RuleShape(r, merges) for r in program["recipe"]["rules"]]

    def describe(self, layout):
        params, markers, boundary = {}, {}, {}
        steps = []
        for rid, group, wires in layout:
            rule = self.rules[rid]
            refs = [params.setdefault(p, len(params)) for p in rule.values]
            ids = [markers.setdefault(p, len(markers)) for p in rule.markers]
            sources = [(owner, boundary.setdefault(pc, len(boundary)) if owner == -1 else pc)
                       for owner, pc in wires]
            steps.append((rule.key, group, sources, refs, ids))
        return steps, tuple(params), tuple(markers)

    def manifest(self, layouts):
        return dict(representation=FORMAT, rule_shapes=[r.key for r in self.rules],
                    structural_keys=[self.key(layout) for layout in layouts])

    def key(self, layout):
        return digest(self.describe(layout)[0])


def link_layouts(program, manifest, limit=None):
    """Link static code to concrete target rules, preserving the target's literal values."""
    from ripsat_layout import signatures

    exact = {sig: i for i, sig in enumerate(signatures(program))}
    mapping = [exact.get(sig) for sig in manifest["signatures"]]
    bake = None
    if manifest.get("representation") is not None:
        if manifest["representation"] != FORMAT:
            raise ValueError("unsupported structural catalog format")
        bake = StructuralBake(program)
        by_shape = {}
        for rid, rule in enumerate(bake.rules):
            # Ambiguous alternatives need an explicit concrete rule binding.
            by_shape[rule.key] = None if rule.key in by_shape else rid
        for i, key in enumerate(manifest["rule_shapes"]):
            if mapping[i] is None:
                mapping[i] = by_shape.get(key)
    for index, layout in enumerate(manifest["layouts"][:limit]):
        if any(mapping[r] is None for r, _, _ in layout):
            continue
        unit = [(mapping[r], group, tuple(map(tuple, wires))) for r, group, wires in layout]
        if bake is None or bake.key(unit) == manifest["structural_keys"][index]:
            yield index, unit


def audit(program_path, catalog_path, out, targets=()):
    from ripsat_layout import signatures
    from higher_cell import fingerprint

    program = json.loads(program_path.read_bytes())
    catalog = json.loads(catalog_path.read_bytes())
    if signatures(program) != catalog["signatures"]:
        raise ValueError("exact rule identities differ from the catalog donor")
    baked = StructuralBake(program)
    groups = Counter()
    exact = set()
    used = set()
    parameterized = 0
    shared_across_steps = 0
    for layout in catalog["layouts"]:
        steps, values, markers = baked.describe(layout)
        groups[digest(steps)] += 1
        exact.add(digest(layout))
        used.update(r for r, _, _ in layout)
        parameterized += bool(values)
        shared_across_steps += sum(len(s[3]) for s in steps) > len(values)
        for (rid, _, _), (_, _, _, refs, ids) in zip(layout, steps, strict=True):
            rule = baked.rules[rid]
            if tuple(values[i] for i in refs) != rule.values or tuple(markers[i] for i in ids) != rule.markers:
                raise ValueError("instance binding does not reconstruct concrete operands")
    rules = program["recipe"]["rules"]
    for i in used:
        shape = baked.rules[i]
        body = shape.instantiate(shape.values, shape.markers)
        if body[2:4] != [rules[i]["query"], rules[i]["effects"]]:
            raise ValueError("bound query/effect program differs from the native instance")
    result = dict(format=FORMAT, catalog_sha256=hashlib.sha256(catalog_path.read_bytes()).hexdigest(),
                  entries=len(catalog["layouts"]), concrete_layouts=len(exact), structures=len(groups),
                  multiplicities=dict(sorted(Counter(groups.values()).items())), integer_layouts=parameterized,
                  cross_step_integer_sharing=shared_across_steps, used_rule_ids=len(used),
                  used_exact_rules=len({fingerprint(rules[i]) for i in used}),
                  used_rule_shapes=len({baked.rules[i].key for i in used}),
                  donor_rules=len(rules), donor_rule_shapes=len({r.key for r in baked.rules}))
    if targets:
        typed = dict(catalog, **baked.manifest(catalog["layouts"]))
        result["target_linking"] = {}
        for path in targets:
            target = json.loads(path.read_bytes())
            linked = dict(link_layouts(target, typed))
            prior = dict(link_layouts(target, catalog))
            extra = linked.keys() - prior.keys()
            target_bake = StructuralBake(target)
            changed = sum(any(baked.rules[r].values != target_bake.rules[t].values
                              for (r, _, _), (t, _, _) in zip(catalog["layouts"][i], linked[i], strict=True))
                          for i in extra)
            result["target_linking"][path.parent.name] = dict(
                concrete=len(prior), structural=len(linked), new_with_changed_values=changed,
                new_with_same_values=len(extra)-changed, lost=len(prior.keys()-linked.keys()))
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(result)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for key in ("program", "catalog", "out"):
        p.add_argument(key, type=Path)
    p.add_argument("--targets", type=Path, nargs="*", default=[])
    a = p.parse_args()
    audit(a.program, a.catalog, a.out, a.targets)
