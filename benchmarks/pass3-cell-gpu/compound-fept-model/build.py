"""Link the actual donor-trained single dispatch and compiled arithmetic family action."""
import argparse
from pathlib import Path
from runpy import run_path
HERE=Path(__file__).resolve().parent
wide=run_path(str(HERE.parent/"wide-fept-composition/build.py"))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("out",type=Path)
    wide["base"]["base"]["joint"].build(p.parse_args().out,True,True,True,cli_allocator=True,
        extensions=(*wide["EXTENSIONS"],"compound-family-ports"))
