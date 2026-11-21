"""Build an observer of already-chosen return values; the relation and candidate generators are unchanged."""
import argparse
from pathlib import Path
from runpy import run_path
HERE=Path(__file__).resolve().parent
base=run_path(str(HERE.parent/"strict-partial-named-ports/build.py"))
if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("out",type=Path)
    base["base"]["base"]["joint"].build(p.parse_args().out,True,True,True,cli_allocator=True,
                                        extensions=(*base["EXTENSIONS"],HERE.name))
