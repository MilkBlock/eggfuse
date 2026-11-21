"""Compile a RipSat donor manifest for the target of a neural CPU session."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile

HERE = Path(__file__).resolve().parent


def donor_paths(items):
    donors = {}
    for item in items:
        name, sep, filename = item.partition("=")
        if not sep or not name or not filename:
            raise ValueError("expected --donor NAME=PROGRAM.json")
        if name in donors:
            raise ValueError(f"duplicate donor {name}")
        donors[name] = Path(filename)
    if not donors:
        raise ValueError("at least one RipSat donor program is required")
    return donors


def build(evidence, donors, target, *, trust_index=None, source_dir=None):
    """The adapter rechecks the evidence and relinks the static edges to this target."""
    path = HERE.parent / "ripsat-strict-programs/compile.py"
    spec = importlib.util.spec_from_file_location("eggfuse_ripsat_programs", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    options = {}
    if trust_index is not None:
        options["trust_index"] = Path(trust_index)
    if source_dir is not None:
        options["source_dir"] = Path(source_dir)
    artifact = module.compile_library(Path(evidence), donors, Path(target), **options)
    if artifact.get("target_sha256") != hashlib.sha256(Path(target).read_bytes()).hexdigest():
        raise ValueError("RipSat compiler returned a different target")
    # These paths describe local offline build inputs. They are never exposed
    # to inference and do not substitute for a proof of source dependencies.
    artifact["bake_inputs"] = {
        "evidence": str(Path(evidence).resolve()),
        "donors": {name: str(Path(p).resolve()) for name, p in sorted(donors.items())},
    }
    return artifact


def load_checked(library, target, *, trust_index=None, source_dir=None):
    """Revalidate a previously published library once, before the native session."""
    artifact = json.loads(Path(library).read_bytes())
    if not isinstance(artifact, dict) or artifact.get("target_sha256") != hashlib.sha256(Path(target).read_bytes()).hexdigest():
        raise ValueError("compiled RipSat library belongs to a different target program")
    inputs = artifact.get("bake_inputs", {})
    if not isinstance(inputs, dict) or not inputs.get("evidence") or not isinstance(inputs.get("donors"), dict):
        raise ValueError("missing offline build inputs; recompile with bake.py ripsat")
    checked = build(Path(inputs["evidence"]), {k: Path(v) for k, v in inputs["donors"].items()}, target,
                    trust_index=trust_index, source_dir=source_dir)
    if checked != artifact:
        raise ValueError("compiled RipSat library disagrees with its checked build evidence")
    return checked


def write_artifact(output, artifact):
    """Keep an earlier successful library or publish a complete new one."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output.parent,
                                         prefix=f".{output.name}.", delete=False) as out:
            temp = out.name
            json.dump(artifact, out, indent=2, ensure_ascii=False, allow_nan=False)
            out.write("\n")
        os.replace(temp, output)
    finally:
        if temp is not None and os.path.exists(temp):
            os.unlink(temp)


def add_provenance_args(p):
    p.add_argument("--trust-index", type=Path, help="independently generated donor and native receipt index")
    p.add_argument("--source-dir", type=Path, help="directory containing the original egg source parts")


def add_study_args(parser):
    add_provenance_args(parser)
    parser.add_argument("--partial", action="store_true",
                        help="use the partial named-parent runtime for every treatment")
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--ripsat-evidence", type=Path, help="recompile checked native RipSat evidence for each target")
    src.add_argument("--ripsat-library", type=Path, help="validate and use a precompiled library with its one named target")
    parser.add_argument("--donor", action="append", default=[], metavar="NAME=PROGRAM.json")


def cli(argv):
    p = argparse.ArgumentParser(prog="bake.py ripsat", description=__doc__)
    p.add_argument("--evidence", required=True, type=Path)
    p.add_argument("--donor", required=True, action="append", metavar="NAME=PROGRAM.json")
    p.add_argument("--target", required=True, type=Path, help="compiled neural target program.json")
    p.add_argument("--out", "--output", required=True, type=Path)
    add_provenance_args(p)
    a = p.parse_args(argv)
    try:
        donors = donor_paths(a.donor)
        inputs = [a.evidence, a.target, *donors.values()]
        if a.trust_index is not None:
            inputs.append(a.trust_index)
        if a.out.resolve() in {p.resolve() for p in inputs}:
            raise ValueError("output would overwrite an input")
        artifact = build(a.evidence, donors, a.target, trust_index=a.trust_index, source_dir=a.source_dir)
        write_artifact(a.out, artifact)
    except (OSError, ValueError) as err:
        p.exit(1, f"{p.prog}: {err}\n")
    spec = artifact["strict_named"]
    print(f"{a.out}  ({len(spec['library'])} statically linked programs, depth {spec['depth']})")
