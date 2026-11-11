#!/usr/bin/env python3
"""Compare v4/v5 on short actual executions; no throughput campaign."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, log):
    with log.open("w") as output:
        subprocess.run(list(map(str, command)), check=True, stdout=output,
                       stderr=subprocess.STDOUT, timeout=180)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("compiler", "runtime", "fixture_program", "sum_program",
                 "ray_program", "saved_semantic", "output"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    args.output.mkdir()
    root = args.output.resolve()
    result = {"scope": "standalone Cell CPU; fixture, complete sum-bits, 128-Run Raytrace prefix; no speed evidence",
              "binaries": {k: sha(getattr(args, k)) for k in ("compiler", "runtime")}, "cases": {}}
    fields = ("ordinal", "ruleset", "path", "iterations", "epoch", "logical_matches", "executed_bindings", "changed")
    effects = ("constructor_requests", "function_updates", "unions", "union_requests", "logical_facts_created")
    for case, source, limit in (("fixture", args.fixture_program, 100),
                                ("sum", args.sum_program, 2000),
                                ("ray128", args.ray_program, 128)):
        lanes = {}
        reference = None
        for label, enabled in (("v4", "false"), ("v5", "true")):
            baked = root / f"{case}-{label}-baked"
            run([args.compiler.resolve(), "bake-cell-completion", "--program", source.resolve(),
                 "--output", baked, "--lazy-unions", enabled], root / f"{case}-{label}-compile.log")
            program = read(baked / "program.json")
            assert program["recipe"] == read(source)["recipe"]
            output = root / f"{case}-{label}"
            run([args.runtime.resolve(), baked / "program.json", output, limit, 4, 64,
                 "canonical", "--repair-ports", "--entry-publications", "--cell-absorption"],
                root / f"{case}-{label}.log")
            report = read(output / "report.json")
            assert report["program_sha256"] == program["sha256"]
            evidence = (sha(output / "state.json"), [[s[k] for k in fields] for s in report["steps"]],
                        {k: report["stats"][k] for k in effects})
            if reference is None:
                reference = evidence
            else:
                assert evidence == reference, (case, "state, Run or effect mismatch")
            spine = report["stage_spine"]["stats"]
            plans = program["iterative_bake"]["rhs_handoffs"]["completion_states"]
            unions = [p["lazy_unions"] for p in plans if p and "lazy_unions" in p]
            lanes[label] = {
                "program_sha256": sha(baked / "program.json"), "report_sha256": sha(output / "report.json"),
                "state_sha256": evidence[0], "runs": len(report["steps"]), "effects": evidence[2],
                "direct_states": sum(p is not None for p in plans), "union_states": len(unions),
                "union_programs": len({json.dumps(p, sort_keys=True) for p in unions}),
                "queries": report["key_lookup_calls"],
                "graph_work": {k: report["stats"][k] for k in ("handoff_attempts", "rhs_frames_avoided", "register_result_writes", "decoded_rows")},
                "spine": {k: v for k, v in spine.items() if k.startswith("ripsat_") or k in (
                    "history_capture_reads", "history_slots_written", "history_allocations", "history_inherited_reads",
                    "effect_slots_initialized", "effect_slot_probes", "effect_output_copies", "output_registrations",
                    "cell_output_slot_reads", "cell_output_deliveries")},
            }
        if case == "fixture":
            assert lanes["v5"]["spine"]["ripsat_union_cells"] > 0, "must exercise actual takeover"
            assert lanes["v5"]["graph_work"]["handoff_attempts"] < lanes["v4"]["graph_work"]["handoff_attempts"]
        result["cases"][case] = {"source_sha256": sha(source), "lanes": lanes}
    semantic = root / "semantic"
    semantic.mkdir()
    for name in ("native-source.json", "native-legacy.json", "native-values.json", "sum-legacy"):
        (semantic / name).symlink_to((args.saved_semantic / name).resolve())
    (semantic / "run-legacy").symlink_to(root / "sum-v4")
    (semantic / "run-values").symlink_to(root / "sum-v5")
    acceptance = root / "semantic-acceptance.json"
    checker = Path(__file__).resolve().parents[1] / "marker-handoff/choice_diagnosis.py"
    run(["python3", checker, semantic, acceptance], root / "semantic.log")
    proof = read(acceptance)
    assert proof["status"] == "pass"
    result["sum_native_acceptance_sha256"] = sha(acceptance)
    (root / "checks.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({c: {l: v["spine"]["ripsat_union_cells"] for l, v in d["lanes"].items()}
                      for c, d in result["cases"].items()}))


if __name__ == "__main__":
    if not __debug__:
        raise SystemExit("run without Python -O")
    main()
