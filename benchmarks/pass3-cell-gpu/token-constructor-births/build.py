"""Build source-owned multi-parent proofs into the verified-wave native engine."""
from argparse import ArgumentParser
from pathlib import Path
from runpy import run_path

HERE=Path(__file__).resolve().parent
build=run_path(str(HERE.parent/"verified-wave-execution/build.py"))
if __name__=="__main__":
    p=ArgumentParser(description=__doc__);p.add_argument("output",type=Path)
    build["base"]["joint"].build(p.parse_args().output,True,True,True,cli_allocator=True,
                                 extensions=(*build["extensions"],HERE.name))
