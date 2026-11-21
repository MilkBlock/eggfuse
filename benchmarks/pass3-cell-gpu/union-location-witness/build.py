"""Build pre-enumeration neural union position proposals."""
import argparse
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("composed_build", HERE.parent / "composed-cpu/build.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    base.joint.build(parser.parse_args().out, True, True, True,
                     cli_allocator=True, extensions=(*base.EXTENSIONS, HERE.name))
