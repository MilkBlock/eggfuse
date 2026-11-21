"""Actual CPU proposer, stable facts and independent complete Pass 3 controls."""
import importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('spec_source',HERE.parent/'pair-source-frontier/study.py')
source=importlib.util.module_from_spec(s);s.loader.exec_module(source)

def base(req):
    return dict(req,header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4,multi_page_tuples=8192)
