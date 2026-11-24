"""Build a portable HTML viewer from one or more Bake catalogs."""
import hashlib
import json
from pathlib import Path


def _load(path):
    return json.loads(path.read_bytes())


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _catalog(path, program):
    path = Path(path)
    if path.is_dir():
        path = path / "catalog.json"
    source = _load(path)
    folder = path.parent
    if isinstance(source, list):
        layouts, signatures = source, None
        fixed = folder / "fixed.json"
        if fixed.exists():
            spec = _load(fixed)
            if spec["catalog"] == _digest(path):
                signatures = spec["signatures"]
    else:
        layouts, signatures = source["layouts"], source["signatures"]

    for idx, layout in enumerate(layouts):
        if not layout:
            raise ValueError(f"empty layout {idx}")
        for step, (rule, group, inputs) in enumerate(layout):
            if rule < 0 or group < 0 or (signatures and rule >= len(signatures)):
                raise ValueError(f"invalid rule or Run group at layout {idx}, step {step}")
            if any(owner < -1 or owner >= step or port < 0 for owner, port in inputs):
                raise ValueError(f"invalid wiring at layout {idx}, step {step}")

    rules = {}
    candidate = Path(program) if program else folder.parent / "sum" / "program.json"
    if program or (signatures and candidate.exists()):
        recipe = _load(candidate)["recipe"]["rules"]
        mapped = {hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest(): r
                  for r in recipe}
        for rid in {s[0] for l in layouts for s in l}:
            r = mapped.get(signatures[rid]) if signatures else recipe[rid]
            if r is None:
                continue
            rules[rid] = dict(name=r["metadata"]["name"], group=r["metadata"]["source_set"],
                              atoms=[a["call"]["table"] for a in r["query"] if "table" in a["call"]],
                              effects=[e.get("call", {}).get("table", e["op"]) for e in r["effects"]])
    replay = {}
    evidence = folder / "replay.json"
    if evidence.exists():
        report = _load(evidence)
        expected = report.get("catalog")
        matched = expected == _digest(path)
        units = folder / "units.json"
        if not matched and units.exists() and expected == _digest(units):
            matched = _load(units) == layouts
        if matched:
            replay = {name: data["complete_layouts"] for name, data in report["cases"].items()}
    return dict(name=folder.name if path.name in ("catalog.json","units.json") else path.stem,
                layouts=layouts, rules=rules, replay=replay)


def render(catalogs, output, program=None):
    """Write a self-contained interactive viewer. Accept a path or iterable of paths."""
    if isinstance(catalogs, (str, Path)):
        catalogs = [catalogs]
    data = [_catalog(p, program) for p in catalogs]
    if not data:
        raise ValueError("supply at least one catalog")
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("<", "\\u003c")
    html = Path(__file__).with_name("viewer.html").read_text(encoding="utf-8")
    target = Path(output)
    target.write_text(html.replace("/*CATALOGS*/", payload), encoding="utf-8")
    return target
