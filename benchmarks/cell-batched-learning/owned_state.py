"""Summarize same-catalog completed-owner representation measurements."""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
checks = json.loads((root / "owned-state/checked.json").read_text())["cases"]
rows = []
for check in checks:
    case = check["case"]
    before = json.loads((root / case / "candidate-live-parent-owner-heap.json").read_text())
    after = json.loads((root / case / "candidate-owned-fact-heap.json").read_text())
    assert check["all_saved_run_checks_equal"] is True
    assert before["program_sha256"] == after["program_sha256"] == check["program"]
    assert before["final_state_sha256"] == after["final_state_sha256"]
    owner = after["source_storage"]["completed_owners"]
    rows.append({
        "case": case, "program_sha256": after["program_sha256"],
        "runs_checked": check["runs"], "same_final_state": True,
        "graph_before": before["graph_owned_teardown_bytes"],
        "graph_after": after["graph_owned_teardown_bytes"],
        "graph_saved": before["graph_owned_teardown_bytes"] - after["graph_owned_teardown_bytes"],
        "owned_fact_bytes": owner["owned_fact_bytes"],
        "representation_fallbacks": owner["representation_fallbacks"],
        "stored_fact_entries": owner["stored_fact_entries"],
        "live_fact_entries": owner["live_fact_entries"],
        "source_records": owner["source_records"],
        "execution_peak_before": before["execution_and_takeover_peak_bytes"],
        "execution_peak_after": after["execution_and_takeover_peak_bytes"],
        "takeover_extra_before": before["max_takeover_extra_bytes"],
        "takeover_extra_after": after["max_takeover_extra_bytes"],
        "retained_program_bytes": after["retained_program_teardown_bytes"],
    })
report = {"scope": "standalone Cell runtime, same shared seed catalog; not native egglog or speed measurements",
          "peak_scope": "execution peaks include retained Program and executor; final Graph is measured separately by teardown",
          "cases": rows}
Path(sys.argv[2]).write_text(json.dumps(report, indent=2) + "\n")
