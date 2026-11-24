"""Differential native replay of CSUnit-000004. A final-value contract is local."""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import tempfile


def run(cell, binary):
    entry = (cell / "entry.egg").read_text()
    marker = "\n(fail (check (= (ExtractedExpr"
    if entry.count(marker) != 1:
        raise ValueError("unrecognized entry export")
    # Contains the three fixture inputs, their checked Const row and Potential.
    prefix = entry[:entry.index(marker)]
    row = "(Const (RipenInput_4_ 1) (RipenInput_22_ 2) (RipenInput_0_ 0))"
    target = "(ExtractedExpr " + row + ")"
    candidate = "(TCPair (TermConst (RipenInput_4_ 1)) 1)"
    sentinel = "(TCPair (NoTerm) 10000000000000000)"
    stages = "(run terms 1)\n(run terms-helpers 1)\n(run terms-helpers-helpers 1)\n"
    checks = []

    def execute(name, src):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "test.egg"
            f.write_text(src)
            subprocess.run([binary, str(f)], check=True)
        checks.append(name)

    execute("original-ripened", (cell / "ripened.egg").read_text())
    for name, incumbent, expected in [
        ("sentinel", sentinel, candidate),
        ("better", "(TCPair (NoTerm) 0)", "(TCPair (NoTerm) 0)"),
        ("tie", "(TCPair (NoTerm) 1)", "(TCPair (NoTerm) 1)"),
    ]:
        initial = prefix + f"(set {target} {incumbent})\n"
        post = f"(check (= {target} {expected}))\n"
        ref = initial + stages * 2
        direct = initial + f"(set {target} {candidate})\n(run terms-helpers-helpers 1)\n"
        execute(name + "-reference", ref + post)
        execute(name + "-single-update", direct + post)
        if name == "tie":
            # Same final value, but the unconditional write publishes an extra
            # constructor that a later rule can match.
            witness = f"(check (Smaller {incumbent} {candidate}))"
            execute("tie-reference-no-new-Smaller", ref + "(fail " + witness + ")")
            execute("tie-direct-publishes-Smaller", direct + witness)

    # Exchange only the two cost operands in the Const contract. The marker
    # address, scheduling counts and operation positions retain their integers.
    new_cost = 10**16
    swapped = prefix.replace("(TCPair (TermConst c) 1)", f"(TCPair (TermConst c) {new_cost})")
    swapped = swapped.replace(candidate, f"(TCPair (TermConst (RipenInput_4_ 1)) {new_cost})")
    swapped = swapped.replace("(TCPair (NoTerm ) 10000000000000000)", "(TCPair (NoTerm) 1)")
    execute("swapped-costs-reverse-winner-preserve-boundary", swapped
            + f"(set {target} (TCPair (NoTerm) 1))\n" + stages * 2
            + f"(check (= {target} (TCPair (NoTerm) 1)))\n"
            + f"(check (PotentialExtractedExpr {row} (TCPair (TermConst (RipenInput_4_ 1)) {new_cost})))")
    observe = f"""
(relation SeenSentinel ())
(ruleset observer)
(rule ((= {target} {sentinel})) ((SeenSentinel)) :ruleset observer)
"""
    execute("between-runs-reference-observes-sentinel", prefix + observe
            + "(run terms 1)\n(run terms-helpers 1)\n(run observer 1)\n"
            + stages * 2 + "(check (SeenSentinel))")
    execute("between-runs-single-update-misses-sentinel", prefix + observe
            + f"(set {target} {candidate})\n(run observer 1)\n"
            + "(fail (check (SeenSentinel)))")
    state = json.loads((cell / "observed-saturated-state.json").read_bytes())
    marker_rows = [r for r in state["rows"] if r["op"].startswith("RipenInput")]
    fields = {v for r in state["rows"] if not r["op"].startswith("RipenInput") for v in r["args"]}
    ints = [state["values"][v]["literal"] for v in fields if state["values"][v]["sort"] == "i64"]
    statuses = Counter(json.loads(f.read_bytes())["saturated_rule_composition"]["status"]
                       for f in cell.parent.glob("*/ripen.json"))
    recipe = json.loads((cell.parents[3] / "program.json").read_bytes())["recipe"]["rules"]
    source = json.loads((cell / "ripen.json").read_bytes())["origin"]["reuse_recipe"][0]["rule"]
    matching = [r for r in recipe if r["metadata"]["name"] in source and
                [a["call"] for a in r["query"]] == [{"table": "Const"}]]
    if len(matching) != 1:
        raise ValueError("ambiguous Const entry in executable program")
    rows = matching[0]["interface"]["rows"]
    return dict(native_checks=checks, observed_marker_rows=len(marker_rows), observed_i64=sorted(ints),
                export_status=statuses, reference_parent_rows=len(rows), projected_row_columns=rows[0]["columns"])


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cell", type=Path)
    p.add_argument("native", help="egglog executable built from the vendored revision")
    args = p.parse_args()
    print(json.dumps(run(args.cell, args.native), indent=2))
