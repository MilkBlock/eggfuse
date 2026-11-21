import importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
m=importlib.util.spec_from_file_location('source_pair',HERE.parent/'pair-source-frontier/study.py')
source=importlib.util.module_from_spec(m);m.loader.exec_module(source)


def settings(req):
    return dict(req,header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4)
