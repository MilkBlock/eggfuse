"""Full-program CPU/Metal matching audit, including service-disconnect fallback."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("runtime", type=Path)
    parser.add_argument("program", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    runtime = args.runtime.resolve()
    service = Path(__file__).with_name("runtime_match_service.py").resolve()
    broken = args.output / "disconnect.py"
    broken.write_text(
        "import socket,sys\n"
        "with socket.create_connection(('127.0.0.1',int(sys.argv[1]))) as connection:\n"
        "    connection.recv(1)\n"
    )
    reports = {}
    for name, worker, minimum in [
        ("cpu", None, None), ("gpu", service, 2),
        ("large_batches", service, 32), ("disconnect", broken.resolve(), 2),
    ]:
        directory = args.output / name
        command = [str(runtime), "--program", str(args.program.resolve()), "--output", str(directory)]
        if worker:
            command += ["--gpu-selector-python", sys.executable, "--gpu-selector-service", str(worker),
                        "--gpu-selector-min-rows", str(minimum)]
        with (args.output / (name + ".log")).open("w") as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
        reports[name] = json.loads((directory / "report.json").read_text())
    reference = args.output / "cpu"
    comparisons = {}
    for name in ("gpu", "large_batches", "disconnect"):
        checks = {}
        for filename in ("state.json", "rhs.json", "writes.json", "resumes.json"):
            checks[filename] = json.loads((reference / filename).read_text()) == json.loads(
                (args.output / name / filename).read_text())
        def control(report):
            fields = ("ordinal", "ruleset", "path", "iterations", "changed", "executed_bindings")
            return [tuple(step.get(field) for field in fields) for step in report["steps"]]
        checks["schedule"] = control(reports[name]) == control(reports["cpu"])
        checks["complete"] = reports[name]["status"] == "complete"
        comparisons[name] = checks
    active = reports["gpu"]["gpu_selector"]
    fallback = reports["disconnect"]["gpu_selector"]
    passed = (all(all(checks.values()) for checks in comparisons.values())
              and active["batches"] > 0 and active["rejected_rows"] > 0 and active["failures"] == 0
              and fallback["failures"] == 1 and fallback["batches"] == 0)
    result = dict(
        scope="complete standalone Cell CPU program with live Metal candidate filtering; CPU reference equivalence",
        native_egglog_audit=False, program_sha256=digest(args.program), runtime_sha256=digest(runtime),
        service_sha256=digest(service), python=sys.executable, passed=passed,
        runs=len(reports["cpu"]["steps"]), comparisons=comparisons,
        measurements={name: {key: report.get(key) for key in
                      ("status", "inference_seconds", "setup_seconds", "gpu_selector")}
                      for name, report in reports.items()},
        timing_scope="single diagnostic execution per lane; inference includes transfer audit; no speedup estimate",
    )
    (args.output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(passed=passed, runs=result["runs"], gpu=active)))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
