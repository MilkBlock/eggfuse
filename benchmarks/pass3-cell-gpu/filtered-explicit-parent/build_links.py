from argparse import ArgumentParser
from pathlib import Path
from runpy import run_path

HERE=Path(__file__).resolve().parent
src=run_path(str(HERE/"build.py"))

if __name__=="__main__":
    p=ArgumentParser()
    p.add_argument("out",type=Path)
    src["base"]["joint"].build(p.parse_args().out,True,True,True,cli_allocator=True,
                               extensions=(*src["extensions"], HERE.name))
