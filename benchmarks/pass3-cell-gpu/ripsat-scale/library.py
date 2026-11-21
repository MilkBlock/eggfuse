"""Bake and relink finite constructor programs for already matched source Cells."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from runpy import run_path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
fragment = run_path(str(HERE / "fragments.py"))
digest = fragment["digest"]
occurrences = fragment["occurrences"]
atomic_write = run_path(str(HERE.parent / "explicit-parent-cell-composition/ripsat_bridge.py"))["write_artifact"]


def native_entry(shape):
    ports, ops = shape
    scalars = {"String", "i64", "bool", "f64", "Unit"}
    signatures = {name: schema for name, schema, _ in ops}
    sorts = sorted({s for types in signatures.values() for s in types} - scalars)
    # Use EggFuse's existing symbol names for constructor rows. Generated
    # boundary constructors are private to this isolated, positive RHS slice.
    lines = [f"(sort {s})" for s in [*sorts, "ScaleFrameSort"]]
    for name, schema in signatures.items():
        lines.append(f"(constructor {name} ({' '.join(schema[:-1])}) {schema[-1]})")
    lines.extend(f"(constructor ScaleHole{i} (i64) {s})" for i, s in enumerate(sorts) if s in ports)
    lines.append(f"(constructor ScaleFrame ({' '.join(ports)}) ScaleFrameSort)")
    lines.append("(ruleset complete)")
    vars_ = [f"x{i}" for i in range(len(ports))]
    args = " ".join(vars_)
    # Nest the expression to run the actual constructor operations. Reference
    # sharing is recovered by native interning and checked again on export.
    expressions = []
    for name, _, inputs in ops:
        values = [vars_[index] if kind == "port" else expressions[index] for kind, index in inputs]
        expressions.append("(" + " ".join([name, *values]) + ")")
    lines.append(f"(rule ((= frame (ScaleFrame {args}))) ({expressions[-1]}) :ruleset complete)")
    for i, sort in enumerate(ports):
        values = {"i64": str(i + 1), "String": json.dumps(f"input-{i}"),
                  "bool": "true" if i % 2 else "false", "f64": f"{i + 1}.25", "Unit": "()"}
        value = values[sort] if sort in values else f"(ScaleHole{sorts.index(sort)} {i})"
        lines.append(f"(let input_{i} {value})")
    names = " ".join(f"input_{i}" for i in range(len(ports)))
    lines.append(f"(let input_frame (ScaleFrame {names}))")
    return "\n".join(lines) + "\n"


def verify_native(shape, binary):
    source = native_entry(shape).encode()
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        (root / "entry.egg").write_bytes(source)
        out = root / "native"
        run = subprocess.run([binary, root / "entry.egg", out], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, timeout=15, check=False)
        if run.returncode:
            raise ValueError(run.stderr.decode()[-500:])
        read = lambda name: json.loads((out / name).read_bytes())
        receipt = read("acceptance.json")
        if not (receipt["accepted"] and receipt["ripen_state"] == "Saturated"
                and receipt["records"] and receipt["artifact_sha256"]["entry.egg"] == hashlib.sha256(source).hexdigest()):
            raise ValueError(f"native export declined: {receipt.get('reason')}")
        def root_present(graph):
            rows = {(r["op"], tuple(r["args"])): r["result"] for i,r in enumerate(graph["rows"])
                    if i not in graph.get("subsumed_rows", [])}
            ports = [graph["ports"][f"input_{i}"] for i in range(len(shape[0]))]
            results = []
            for name, _, inputs in shape[1]:
                args = tuple((ports if kind == "port" else results)[idx] for kind,idx in inputs)
                if (name, args) not in rows:
                    return False
                results.append(rows[name,args])
            return True
        if root_present(read("initial-state.json")) or not root_present(read("saturated-rule-composition.json")):
            raise ValueError("expected a newly derived root on the supplied boundary")
    return hashlib.sha256(source).hexdigest()


def catalog(donor_paths, target, binary, max_ops, workers):
    def index(path):
        raw = path.read_bytes()
        sites = {}
        shapes = {}
        for shape, site in occurrences(json.loads(raw), max_ops):
            key = digest(shape)
            shapes[key] = shape
            sites.setdefault(key, []).append(site)
        return hashlib.sha256(raw).hexdigest(), shapes, sites

    donor_hashes = []
    donor_keys = set()
    for path in donor_paths:
        sha, shapes, _ = index(path)
        donor_hashes.append(sha)
        donor_keys.update(shapes)
    target_sha, shapes, sites = index(target)
    keys = sorted(donor_keys.intersection(shapes))
    def check(key):
        try:
            return key, verify_native(shapes[key], binary), None
        except (ValueError, subprocess.TimeoutExpired) as err:
            return key, None, str(err)
    entries, rejected = [], {}
    with ThreadPoolExecutor(workers) as pool:
        for key, evidence, error in pool.map(check, keys):
            if error is None:
                entries.append(dict(id=key, program=shapes[key], native_entry_sha256=evidence, sites=sites[key]))
            else:
                rejected[key] = error
    return dict(schema="eggfuse-ripsat-rhs-fragments/v1", max_ops=max_ops, target_sha256=target_sha,
                donors=sorted(set(donor_hashes)), binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                donor_candidates=len(donor_keys), target_candidates=len(shapes), shared_candidates=len(keys),
                entries=entries, rejected=rejected)


def cli(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor", type=Path, action="append", required=True)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--native", required=True, type=Path)
    parser.add_argument("--max-ops", type=int, choices=range(2, 9), default=5)
    parser.add_argument("--workers", type=int, default=4)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out", type=Path)
    mode.add_argument("--check", type=Path, help="relink to exact source sites and replay all native proofs")
    a = parser.parse_args(argv)
    if a.workers < 1:
        parser.error("--workers must be positive")
    if a.out and a.out.resolve() in {p.resolve() for p in [a.target, a.native, *a.donor]}:
        parser.error("output overlaps a build input")
    result = catalog(a.donor, a.target, a.native.resolve(), a.max_ops, a.workers)
    if a.check:
        # JSON round trip also normalizes tuple-backed site references.
        if json.loads(a.check.read_bytes()) != json.loads(json.dumps(result)):
            parser.exit(1, "cached library differs from exact-source native replay\n")
    else:
        atomic_write(a.out, result)
    print(f"{len(result['entries'])} checked RHS fragments, {len(result['rejected'])} declined")


if __name__ == "__main__":
    import sys
    cli(sys.argv[1:])
