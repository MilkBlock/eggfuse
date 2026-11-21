import importlib.util,json
from pathlib import Path
from policy import shapes,mask
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('paired_pages',HERE.parent/'pair-source-frontier/study.py')
source=importlib.util.module_from_spec(spec);spec.loader.exec_module(source)
original=source.common.config

def configure(a,case):
    program,plans,req=original(a,case)
    a.shapes=shapes(json.loads(program.read_bytes()),json.loads(plans.read_bytes()))
    return program,plans,req

def base(req):
    return dict(req,header_mode=3,derived_ports={'mode':1,'cache':True},lazy_equations=4,multi_page_tuples=8192)

def route(req,rows,selected):
    return dict(req,factor_page=2,page_premises=9,coordinate_verify=2,page_library=mask(rows,selected))
