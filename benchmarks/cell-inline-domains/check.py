#!/usr/bin/env python3
"""Short Cell CPU work comparison. No workload timing or speed claim."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def read(path):
    return json.loads(path.read_text())


def sha(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def run(command, log):
    with log.open("w") as output:
        subprocess.run(list(map(str, command)), check=True, stdout=output,
                       stderr=subprocess.STDOUT, timeout=180)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("before", "after", "fixture", "sum_program", "ray_program", "saved_semantic", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    args.output.mkdir()
    root = args.output.resolve()
    result = {
        "scope": "standalone Cell CPU; short work and semantic checks, not performance evidence",
        "control_commit": "3c4dc524",
        "binaries": {k: sha(getattr(args, k)) for k in ("before", "after")}, "cases": {},
    }
    fields = ("ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches", "executed_bindings", "changed")
    for case, source, limit in (("fixture", args.fixture, 128), ("sum", args.sum_program, 2000),
                                ("ray1280", args.ray_program, 1280)):
        lanes, reference = {}, None
        for label in ("before", "after"):
            output = root / f"{case}-{label}"
            run([getattr(args, label).resolve(), source.resolve(), output, limit, 4, 64,
                 "canonical", "--repair-ports", "--entry-publications", "--cell-absorption"],
                root / f"{case}-{label}.log")
            report = read(output / "report.json")
            assert report["program_sha256"] == read(source)["sha256"]
            runs = [[s[k] for k in fields] for s in report["steps"]]
            evidence = (sha(output / "state.json"), runs, report["stats"])
            if reference is None:
                reference = evidence
            else:
                assert evidence == reference, (case, "state, source Run or committed-effect mismatch")
            lanes[label] = {
                "report_sha256": sha(output / "report.json"), "state_sha256": evidence[0], "runs": len(runs),
                "run_signature_sha256": hashlib.sha256(json.dumps(runs).encode()).hexdigest(),
                "graph_stats_sha256": hashlib.sha256(json.dumps(evidence[2], sort_keys=True).encode()).hexdigest(), "queries": report["key_lookup_calls"],
                "graph_work": {k: report["stats"][k] for k in (
                    "bindings", "single_writes", "constructor_requests", "union_requests", "decoded_rows")},
                "free_join": report["free_join"],
                "transport": report.get("query_domain_transport"),
                "spine": {k: v for k, v in report["stage_spine"]["stats"].items() if k in (
                    "output_registrations", "cell_output_slot_reads", "cell_output_deliveries", "direct_publication_hash_probes")},
            }
        old, new = (lanes[k] for k in ("before", "after"))
        assert old["queries"] == new["queries"]
        for field, count in old["free_join"].items():
            # An independent later general probe may materialize a view that
            # entry admission no longer built. Retain both counters and compare
            # their total; that shifted work is not an eliminated allocation.
            if field not in ("entry_bucket_rows_materialized", "bucket_rows_materialized"):
                assert count == new["free_join"][field], (case, field)
        assert new["free_join"]["inline_domain_deliveries"] > 0, case
        materialized = lambda lane: sum(lane["free_join"][f] for f in
            ("entry_bucket_rows_materialized", "bucket_rows_materialized"))
        assert materialized(new) < materialized(old), case
        result["cases"][case] = {"program_sha256": sha(source), "lanes": lanes}
    semantic = root / "semantic"
    semantic.mkdir()
    for name in ("native-source.json", "native-legacy.json", "native-values.json", "sum-legacy"):
        (semantic / name).symlink_to((args.saved_semantic / name).resolve())
    (semantic / "run-legacy").symlink_to(root / "sum-before")
    (semantic / "run-values").symlink_to(root / "sum-after")
    acceptance = root / "semantic-acceptance.json"
    checker = Path(__file__).resolve().parents[1] / "marker-handoff/choice_diagnosis.py"
    run(["python3", checker, semantic, acceptance], root / "semantic.log")
    assert read(acceptance)["status"] == "pass"
    result["sum_native_acceptance_sha256"] = sha(acceptance)
    (root / "checks.json").write_text(json.dumps(result, indent=2) + "\n")
    print("short work comparison and sum-bits semantic acceptance: pass")


if __name__ == "__main__":
    if not __debug__:
        raise SystemExit("run without Python -O")
    main()
