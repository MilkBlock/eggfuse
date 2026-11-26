"""Build a portable HTML viewer from one or more Bake catalogs."""
import gzip
import hashlib
import json
import re
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


def _primitive_catalog(program, recipe):
    tables = recipe["recipe"]["tables"]
    rules, layouts = {}, []
    for rid, contract in enumerate(recipe["receipt_contract"]["rules"]):
        if contract["recipe_rule"] != rid:
            raise ValueError("unexpected Recipe rule order")
        rule = recipe["recipe"]["rules"][rid]
        inputs = [tables[port["table"]]["name"] for port in contract["inputs"]]
        rules[rid] = dict(name=rule["metadata"]["name"], group=rule["metadata"]["source_set"],
                          atoms=inputs, effects=[e.get("call", {}).get("table", e["op"]) for e in rule["effects"]])
        layouts.append([[rid, 0, [[-1, i] for i in range(len(inputs))]]])
    return dict(name="当前程序 · Primitive", layouts=layouts, rules=rules, replay={},
                program_sha=_digest(Path(program)))


def _embedded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).replace("<", r"\u003c")


def suite_html(catalogs, program=None, *, stream=None, start_stream=False, egraph_link=False):
    """Assemble the catalog and token views into one self-contained document."""
    if isinstance(catalogs, (str, Path)):
        catalogs = [catalogs]
    data = [_catalog(p, program) for p in catalogs]
    trace = None
    if stream:
        path = Path(stream)
        with path.open("rb") as f:
            packed = f.read(2) == bytes([31, 139])
        with (gzip.open(path, "rt", encoding="utf-8") if packed else path.open(encoding="utf-8")) as f:
            trace = json.load(f)
        if not isinstance(trace, dict) or not isinstance(trace.get("events"), list) or not trace["events"]:
            raise ValueError("expected a credit-scaling buffer shard with events")
    if program and (stream or start_stream):
        if trace and trace.get("program") != _digest(Path(program)):
            raise ValueError("program.json SHA-256 does not match the stream")
        recipe = _load(Path(program))
        if "receipt_contract" in recipe:
            data.append(_primitive_catalog(program, recipe))
    if not data and not (stream or start_stream):
        raise ValueError("supply at least one catalog or a token stream")
    package = Path(__file__).parent
    html = (package / "viewer.html").read_text(encoding="utf-8")
    parts = {
        "<!--EGRAPH_LINK-->": '<a href="/" style="color:white">E-graph</a>' if egraph_link else "",
        "/*CATALOGS*/": _embedded(data),
        "<!--STREAM-->": (package / "stream.html").read_text(encoding="utf-8"),
        "/*STREAM_SCRIPT*/": (package / "stream.js").read_text(encoding="utf-8"),
        "/*STREAM_DATA*/": _embedded(dict(name=Path(stream).name if stream else "", trace=trace)),
        "/*START_STREAM*/": str(bool(stream or start_stream)).lower(),
    }
    return re.sub("|".join(map(re.escape, parts)), lambda m: parts[m[0]], html)


def render(catalogs, output, program=None, *, stream=None, start_stream=False):
    """Write one portable document containing both inspection modes."""
    target = Path(output)
    target.write_text(suite_html(catalogs, program, stream=stream, start_stream=start_stream), encoding="utf-8")
    return target
