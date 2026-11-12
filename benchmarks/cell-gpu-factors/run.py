#!/usr/bin/env python3
"""Compile a finite relational Cell DAG into resident Metal matrix operations.

Standalone experiment: no production egglog runtime, learned accuracy claim,
or native constructor/union commit. Python integer sets form the independent
semantic oracle; Python timings are NOT a CPU performance baseline.
"""
import argparse
import array
import hashlib
import json
import random
import statistics
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES = [
    dict(name="tails", batch=3, x=19, z=23, y=17, o=13, rank=5),
    dict(name="small", batch=1, x=48, z=64, y=40, o=32, rank=4),
    dict(name="narrow", batch=8, x=512, z=384, y=256, o=128, rank=8),
    dict(name="single", batch=1, x=512, z=384, y=256, o=128, rank=8),
    dict(name="wide", batch=4, x=256, z=256, y=192, o=96, rank=32),
]


def require(ok, why):
    if not ok:
        raise ValueError(why)


def indices(bits):
    while bits:
        low = bits & -bits
        yield low.bit_length() - 1
        bits ^= low


def join(left, right):
    """Independent set-valued relational join: no factorized rewrite."""
    result = []
    for row in left:
        answer = 0
        for i in indices(row):
            answer |= right[i]
        result.append(answer)
    return result


def oracle(c, data):
    expected = [[], []]
    intermediates = [[], []]
    for item in data:
        parent = list(range(c["rank"]))

        def root(i):
            while parent[i] != i:
                i = parent[i]
            return i

        for phase in range(2):
            if phase:
                for a, b in item["events"]:
                    parent[root(b)] = root(a)
            # Explicit matching of original witnesses modulo the current Eq.
            u = [{root(i) for i in indices(row)} for row in item["U0"]]
            v = [{root(i) for i in indices(row)} for row in item["V0"]]
            m = [sum(1 << z for z, right in enumerate(v) if left & right) for left in u]
            p, q = join(m, item["S"]), join(m, item["T"])
            d = [a & b for a, b in zip(p, q)]
            expected[phase].extend(join(d, item["W"]))
            intermediates[phase].append((m, p, q, d))
    return expected, intermediates


def generate(c, seed):
    rng = random.Random(seed)
    data = []

    def memberships(rows):
        values = []
        for _ in range(rows):
            count = 0 if rng.random() < .12 else (2 if rng.random() < .22 else 1)
            values.append(sum(1 << i for i in rng.sample(range(c["rank"]), count)))
        return values

    def edges(rows, cols):
        result = [0] * rows
        for col in range(cols):
            count = 0 if rng.random() < .1 else rng.choice((1, 2, 3))
            for row in rng.sample(range(rows), count):
                result[row] |= 1 << col
        return result

    for _ in range(c["batch"]):
        ports = rng.sample(range(c["rank"]), 4)
        a, b, d, e = ports
        events = [(a, b), (b, d), (a, d), (e, e)]
        data.append(dict(U0=memberships(c["x"]), V0=memberships(c["z"]),
                         S=edges(c["z"], c["y"]), T=edges(c["z"], c["y"]),
                         W=edges(c["y"], c["o"]), events=events))
    return data


def diagonal_only_wrong(c, data):
    """Deliberately WRONG: omit cross-factor pairs at the branch intersection.

    The fixture must detect this tempting but unsound rank-preserving rewrite.
    This uses the pre-union phase, whose membership factors are the input data.
    """
    output = []
    for item in data:
        p = [0] * c["rank"]
        q = [0] * c["rank"]
        for z, members in enumerate(item["V0"]):
            for k in indices(members):
                p[k] |= item["S"][z]
                q[k] |= item["T"][z]
        rows = []
        for members in item["U0"]:
            row = 0
            for k in indices(members):
                row |= p[k] & q[k]
            rows.append(row)
        output.extend(join(rows, item["W"]))
    return output


def half_rows(rows, width):
    return array.array("H", (0x3c00 if row >> col & 1 else 0
                            for row in rows for col in range(width))).tobytes()


class Plan:
    def __init__(self, c, mode, initial):
        self.c = c
        self.mode = mode
        self.buffers = list(initial)
        self.ops = []
        self.multiply_adds = 0
        self.element_ops = 0

    def temp(self, name, rows, cols):
        self.buffers.append(dict(name=name, bytes=self.c["batch"] * rows * cols * 2))

    def op(self, kernel, buffers, args, count, threads=128, groups=False):
        self.ops.append(dict(kernel=kernel, buffers=buffers, args=args,
                             count=count, threads=threads, groups=groups))

    def mm(self, a, b, out, m, n, k, ta=False, tb=False):
        require(0 < k <= 2**24, "exact FP32 binary sum bound")
        self.temp(out, m, n)
        self.op("boolean_mm", [a, b, out], [m, n, k, self.c["batch"], int(ta), int(tb)],
                self.c["batch"] * ((m + 7) // 8) * ((n + 7) // 8), 32, True)
        self.multiply_adds += self.c["batch"] * m * n * k

    def pair(self, a, b, out, rows, rank):
        self.temp(out, rows, rank * rank)
        count = self.c["batch"] * rows * rank * rank
        self.op("pair_columns", [a, b, out], [rows, rank, self.c["batch"]], count)
        self.element_ops += count

    def intersection(self, a, b, out, rows, cols):
        self.temp(out, rows, cols)
        count = self.c["batch"] * rows * cols
        self.op("intersect", [a, b, out], [count], count)
        self.element_ops += count

    def compile(self):
        c = self.c
        x, z, y, o, r = (c[k] for k in ("x", "z", "y", "o", "rank"))
        for phase in range(2):
            if phase:
                self.op("merge_columns", ["U", "V", "parent", "events"],
                        [x, z, r, c["batch"], 4], c["batch"], 128, True)
            name = lambda s: f"{s}{phase}"
            if self.mode == "dense":
                self.mm("U", "V", name("M"), x, z, r, tb=True)
                self.mm(name("M"), "S", name("P"), x, y, z)
                self.mm(name("M"), "T", name("Q"), x, y, z)
            else:
                self.mm("S", "V", name("VS"), y, r, z, ta=True)
                self.mm("T", "V", name("VT"), y, r, z, ta=True)
                if self.mode == "factor":
                    self.pair("U", "U", name("L2"), x, r)
                    self.pair(name("VS"), name("VT"), name("R2"), y, r)
                    self.mm("W", name("R2"), name("R3"), o, r*r, y, ta=True)
                    self.mm(name("L2"), name("R3"), name("F"), x, o, r*r, tb=True)
                    continue
                self.mm("U", name("VS"), name("P"), x, y, r, tb=True)
                self.mm("U", name("VT"), name("Q"), x, y, r, tb=True)
            self.intersection(name("P"), name("Q"), name("D"), x, y)
            self.mm(name("D"), "W", name("F"), x, o, y)
        return dict(name=f'{c["name"]}-{self.mode}', case=c["name"], mode=self.mode,
                    buffers=self.buffers, ops=self.ops, outputs=["F0", "F1"],
                    reset=[["U0", "U"], ["V0", "V"], ["parent0", "parent"]],
                    logical_multiply_adds=self.multiply_adds, element_ops=self.element_ops)


def write_inputs(out, c, data):
    initial = []
    for name, width in [("U0", c["rank"]), ("V0", c["rank"]),
                        ("S", c["y"]), ("T", c["y"]), ("W", c["o"])]:
        blob = half_rows([row for item in data for row in item[name]], width)
        file = f'{c["name"]}-{name}.f16'
        (out / file).write_bytes(blob)
        initial.append(dict(name=name, bytes=len(blob), file=file))
        if name in ("U0", "V0"):
            initial.append(dict(name=name[0], bytes=len(blob)))
    parent = array.array("I", list(range(c["rank"])) * c["batch"]).tobytes()
    events = array.array("I", [v for item in data for pair in item["events"] for v in pair]).tobytes()
    for name, blob in [("parent0", parent), ("events", events)]:
        file = f'{c["name"]}-{name}.u32'
        (out / file).write_bytes(blob)
        initial.append(dict(name=name, bytes=len(blob), file=file))
    initial.append(dict(name="parent", bytes=len(parent)))
    return initial


def decode(path, rows, cols):
    values = array.array("H")
    values.frombytes(path.read_bytes())
    require(len(values) == rows * cols, "output size")
    require(all(v in (0, 0x3c00) for v in values), "non-binary activation")
    return [sum(1 << col for col in range(cols) if values[row*cols+col]) for row in range(rows)]


def summary(report, bundle, reference, out):
    output = []
    for c in CASES:
        rows = c["batch"] * c["x"]
        expected = reference[c["name"]]
        lanes = [lane for lane in report["lanes"] if lane["case"] == c["name"]]
        control = next(lane for lane in lanes if lane["mode"] == "dense")
        choices = [p for p in bundle["lanes"] if p["case"] == c["name"]]
        # A deliberately simple compile-time selector, not trained on timings.
        selected = min(choices, key=lambda p: p["logical_multiply_adds"] + p["element_ops"])["mode"]
        for lane in lanes:
            for phase in range(2):
                actual = decode(out / f'{lane["name"]}-F{phase}.f16', rows, c["o"])
                require(actual == expected[phase], f'{lane["name"]}: phase {phase} mismatch')
            plan = next(p for p in choices if p["mode"] == lane["mode"])
            lane["gpu_ms_median"] = statistics.median(lane["gpu_seconds"]) * 1000
            lane["submit_wait_ms_median"] = statistics.median(lane["submit_wait_seconds"]) * 1000
            lane["speedup_vs_dense_gpu"] = statistics.median(control["gpu_seconds"]) / statistics.median(lane["gpu_seconds"])
            lane["speedup_vs_dense_submit_wait"] = statistics.median(control["submit_wait_seconds"]) / statistics.median(lane["submit_wait_seconds"])
            lane["with_output_readback_ms_median"] = statistics.median(lane["with_output_readback_submit_wait_seconds"]) * 1000
            lane["paired_readback_speedup_median"] = statistics.median(
                a/b for a, b in zip(control["with_output_readback_submit_wait_seconds"], lane["with_output_readback_submit_wait_seconds"]))
            lane["readback_faster_pairs"] = sum(a > b for a, b in zip(
                control["with_output_readback_submit_wait_seconds"], lane["with_output_readback_submit_wait_seconds"]))
            lane["logical_multiply_adds"] = plan["logical_multiply_adds"]
            lane["kernels_per_job"] = len(plan["ops"])
        output.append(dict(config=c, selected_by_static_work=selected,
                           output_ones=[sum(row.bit_count() for row in stage) for stage in expected],
                           output_bits_per_stage=rows*c["o"],
                           added_output_bits_after_union=sum((b & ~a).bit_count() for a, b in zip(*expected)),
                           lanes=lanes))
    return dict(status="pass", scope=report["scope"], device=report["device"], os=report["os"],
                gpu_execution=True, runtime_takeover=False, native_semantic_acceptance=False,
                repeats=report["repeats"], cases=output)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=9)
    args = parser.parse_args()
    require(args.repeats >= 3, "at least three rotated rounds")
    args.output.mkdir(parents=True, exist_ok=False)
    out = args.output.resolve()
    lanes, reference = [], {}
    started = time.perf_counter()
    for i, c in enumerate(CASES):
        data = generate(c, 741 + i)
        expected, _ = oracle(c, data)
        require(any(a != b for a, b in zip(*expected)), "fixture has no observable union effect")
        require(diagonal_only_wrong(c, data) != expected[0], "fixture does not exercise correlated cross factors")
        require(all(0 < sum(row.bit_count() for row in phase) < c["batch"]*c["x"]*c["o"]
                    for phase in expected), "vacuous all-zero/all-one fixture")
        reference[c["name"]] = expected
        initial = write_inputs(out, c, data)
        for mode in ("dense", "factor", "cut"):
            lanes.append(Plan(c, mode, initial).compile())
    bundle = dict(schema="cell-factor-gpu/v1", cases=[c["name"] for c in CASES],
                  repeats=args.repeats, lanes=lanes)
    (out / "bundle.json").write_text(json.dumps(bundle, indent=2) + "\n")
    prep_seconds = time.perf_counter() - started
    subprocess.run(["xcrun", "swiftc", "-O", str(HERE / "runner.swift"), "-o", str(out / "runner")], check=True)
    subprocess.run([str(out / "runner"), str(out / "bundle.json"), str(HERE / "kernels.metal"),
                    str(out / "device.json")], check=True)
    result = summary(json.loads((out / "device.json").read_text()), bundle, reference, out)
    result["input_generation_compile_oracle_seconds"] = prep_seconds
    result["source_sha256"] = {name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                               for name in ("run.py", "runner.swift", "kernels.metal")}
    (out / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    for case in result["cases"]:
        print(case["config"]["name"], "selected", case["selected_by_static_work"],
              [(lane["mode"], round(lane["gpu_ms_median"], 3),
                round(lane["submit_wait_ms_median"], 3)) for lane in case["lanes"]])
    print("PASS: all GPU outputs before and after union agree with independent explicit joins")


if __name__ == "__main__":
    main()
