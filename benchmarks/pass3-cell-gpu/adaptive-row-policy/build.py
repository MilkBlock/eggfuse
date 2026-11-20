"""Build the high-coverage Rust executor with the adaptive-row experiment overlay."""

import argparse
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "joint-witness"))
import build as joint

spec = importlib.util.spec_from_file_location("adaptive_impl", HERE / "overlay.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("out", type=Path)
    native = joint.install

    def install(name, crate, file="patch.py"):
        native(name, crate, file)
        if name == "joint-root-cells":
            mod.install(crate)

    joint.install = install
    joint.build(p.parse_args().out, True, True, True)
