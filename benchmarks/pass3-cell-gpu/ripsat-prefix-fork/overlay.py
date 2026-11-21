from pathlib import Path
from runpy import run_path

edit = run_path(str(Path(__file__).resolve().parent.parent / "ripsat-set-receipt/overlay.py"))["edit"]


def install(crate):
    strict = crate / "src/strict_named.rs"
    pub = crate / "src/ripsat_set_publication.rs"
    edit(strict, "struct State {", "struct State {withhold_root:Option<u64>,")
    edit(strict, "s.set_plan=plan_set", 's.withhold_root=spec["withhold_root"].as_u64();\n    s.set_plan=plan_set')
    edit(pub, 'if s.set_fault == "missing" {',
         'if s.set_fault == "missing" || s.withhold_root == Some(record.root) {')
