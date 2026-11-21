"""Compile a RipSat donor manifest for the target of a neural CPU session."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from runpy import run_path
import subprocess
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


def build(evidence, donors, target, *, trust_index=None, source_dir=None, set_publication=False, higher_cell=False):
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
    if set_publication or higher_cell:
        # The publication authorizer pins its own donor/history and companion
        # receipts. The ordinary Let compiler cannot grant this capability.
        authorize = run_path(str(HERE.parent / "ripsat-publication-chain/authorize.py"))["authorize"]
        kwargs = {"source_dir": Path(source_dir)} if source_dir is not None else {}
        certificate = authorize(Path(evidence), donors, Path(target), **kwargs)
        named = certificate.get("strict_named", {})
        publication = named.get("set_publication", {})
        if (certificate.get("schema") != "eggfuse-ripsat-publication-chain/v1"
                or certificate.get("target_sha256") != artifact["target_sha256"]
                or publication.get("target_sha256") != artifact["target_sha256"]
                or not certificate.get("support") or named.get("depth") != 2
                or named.get("partial") is not True
                or not all(prefix in artifact["strict_named"]["library"] for prefix in named["library"])):
            raise ValueError("publication authorizer did not grant an applicable Set program")
        artifact["set_publication_authorization"] = certificate
        artifact["bake_inputs"]["set_publication"] = True
        if higher_cell:
            artifact["higher_cell_program"] = derive_higher_cell(certificate)
            artifact["bake_inputs"]["higher_cell"] = True
    return artifact


def load_checked(library, target, *, trust_index=None, source_dir=None, set_publication=False, higher_cell=False):
    """Revalidate a previously published library once, before the native session."""
    artifact = json.loads(Path(library).read_bytes())
    if not isinstance(artifact, dict) or artifact.get("target_sha256") != hashlib.sha256(Path(target).read_bytes()).hexdigest():
        raise ValueError("compiled RipSat library belongs to a different target program")
    inputs = artifact.get("bake_inputs", {})
    if not isinstance(inputs, dict) or not inputs.get("evidence") or not isinstance(inputs.get("donors"), dict):
        raise ValueError("missing offline build inputs; recompile with bake.py ripsat")
    cached_publication = inputs.get("set_publication", False)
    if type(cached_publication) is not bool or cached_publication != ("set_publication_authorization" in artifact):
        raise ValueError("inconsistent cached Set publication authorization")
    cached_higher = inputs.get("higher_cell", False)
    if (type(cached_higher) is not bool or cached_higher != ("higher_cell_program" in artifact)
            or (cached_higher and not cached_publication)):
        raise ValueError("inconsistent cached higher Cell authorization")
    if higher_cell and not cached_higher:
        raise ValueError("cache has no higher Cell program; rebuild with bake.py ripsat --higher-cell")
    if set_publication and not cached_publication:
        raise ValueError("cache has no Set publication authorization; rebuild with bake.py ripsat --set-publication")
    checked = build(Path(inputs["evidence"]), {k: Path(v) for k, v in inputs["donors"].items()}, target,
                    trust_index=trust_index, source_dir=source_dir, set_publication=cached_publication, higher_cell=cached_higher)
    if checked != artifact:
        raise ValueError("compiled RipSat library disagrees with its checked build evidence")
    return checked


HIGHER_ABI = {
    "schema": "eggfuse-ripsat-higher-cell/v1",
    "request": "resolve-constructor-set",
    "branches": ["fresh", "no-new-fact", "stale"],
    "batch": "post-run",
}


def derive_higher_cell(certificate):
    named = certificate["strict_named"]
    publication = named["set_publication"]
    plans = [s["target_static"] for s in certificate["support"]]
    if not plans or any(p != plans[0] for p in plans):
        raise ValueError("higher Cell requires one unambiguous, checked static Set projection")
    static = plans[0]
    if static["table"] != publication["table"] or static["pivot"] != publication["pivot"]:
        raise ValueError("higher Cell operands disagree with the checked Set publication")
    abi = {**HIGHER_ABI, "branches": list(HIGHER_ABI["branches"]),
           "target_sha256": certificate["target_sha256"]}
    # Preserve the existing proof's actual column/literal operands. No observed
    # donor address becomes a literal or an independently chosen target parent.
    return {
        "strict_named": {**named, "higher_cell": abi},
        "request_inputs": {"path": publication["path"], "kinds": publication["kinds"],
                           "table": static["table"], "sorts": static["sorts"],
                           "columns": static["columns"], "terminal_slots": static["terminal_slots"],
                           "middle_return_alias": static["middle_return_alias"]},
        "reply_branches": {
            "fresh": {"value": "published_factref_and_version", "table": static["table"],
                      "consumer_rule": publication["path"][1][2], "release": "original_run"},
            "no-new-fact": {"value": None, "internal_terminal": False},
            "stale": {"value": None, "internal_terminal": False},
        },
    }


def require_higher_capability(native):
    try:
        probe = subprocess.run([str(native), "--higher-cell-capabilities"], input="", text=True,
                               capture_output=True, timeout=10)
        advertised = json.loads(probe.stdout) if probe.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        raise ValueError("--higher-cell requires the native resolve-constructor-set capability") from exc
    if not isinstance(advertised, dict) or any(advertised.get(k) != v for k, v in HIGHER_ABI.items()):
        raise ValueError("--higher-cell requires the native resolve-constructor-set capability")


def require_runtime_higher(result):
    report = result.get("strict_named")
    work = report.get("higher_cell") if isinstance(report, dict) else None
    fields = ("requests", "transferred", "retired_no_result", "stale_replies", "duplicate_replies", "terminal_commits")
    if (not isinstance(work, dict) or work.get("enabled") is not True
            or any(type(work.get(k)) is not int or work[k] < 0 for k in fields)):
        raise ValueError("native execution did not report the enabled higher Cell protocol")
    counts = work.get("counts")
    detail = ("queued_requests", "request_reads", "request_batches", "named_inputs",
              "replies", "retired_stale", "retired_fresh")
    if not isinstance(counts, dict) or any(type(counts.get(k)) is not int or counts[k] < 0 for k in detail):
        raise ValueError("native higher Cell report has no physical request-queue ledger")
    if (work.get("pending") != 0 or work.get("specialized") != 0
            or counts["queued_requests"] != work["requests"]
            or counts["retired_fresh"] != work["transferred"]
            or counts["retired_fresh"] + work["retired_no_result"] + counts["retired_stale"] != work["requests"]
            or (work["requests"] > 0 and counts["request_batches"] == 0)
            or (work["terminal_commits"] > 0 and counts["request_reads"] == 0)):
        raise ValueError("higher Cell request, retirements or terminal commits do not reconcile")
    return {**{k: work[k] for k in fields}, **{k: counts[k] for k in detail}}


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


def require_runtime_publication(result):
    # Older native readers accept unknown JSON options. They cannot expose
    # this dedicated verifier's counters or its audited typed release list.
    report = result.get("strict_named")
    counters = report.get("set_publication") if isinstance(report, dict) else None
    if (not isinstance(counters, dict) or not isinstance(report.get("set_commits"), list)
            or any(type(counters.get(k)) is not int for k in
                   ("encoded", "active_middles", "fresh_activations", "published", "confirmed", "excluded_generation"))):
        raise ValueError("--set-publication requires the ripsat-set-receipt native runtime")
    return counters


def add_provenance_args(p):
    p.add_argument("--set-publication", action="store_true",
                   help="authorize the separate typed fresh constructor-Set program for the exact target")
    p.add_argument("--higher-cell", action="store_true",
                   help="compile the checked Set path with its typed request and post-Run result branches")
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
        artifact = build(a.evidence, donors, a.target, trust_index=a.trust_index, source_dir=a.source_dir,
                         set_publication=a.set_publication, higher_cell=a.higher_cell)
        write_artifact(a.out, artifact)
    except (OSError, ValueError) as err:
        p.exit(1, f"{p.prog}: {err}\n")
    spec = artifact["strict_named"]
    extra = ", checked Set publication available" if a.set_publication or a.higher_cell else ""
    if a.higher_cell:
        extra += ", higher Cell request available"
    print(f"{a.out}  ({len(spec['library'])} statically linked programs, depth {spec['depth']}{extra})")
