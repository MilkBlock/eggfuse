"""The count vector is frozen from a separate donor study before assigning specific physical lanes."""
import importlib.util,json
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("whole_run",HERE.parent/"run-proposal-waves/study.py")
wave=importlib.util.module_from_spec(spec)
spec.loader.exec_module(wave)
source=wave.parent
COUNT_POLICY=json.loads((HERE.parent/"speculative-allocation-policy/policy.json").read_bytes())["models"]["run"]["coverage"]["weights"]

def request(base,mode="first",capture=False,weights=None):
    rank=dict(mode=mode)
    if capture:rank.update(capture=True,groups=True)
    if weights:rank.update(weights)
    return dict(base,header_mode=3,derived_ports=dict(mode=1,cache=True),lazy_equations=4,
                multi_page_tuples=8192,proposal_wave=65536,
                spec_cells=dict(timing="run",storage="named",policy="score",cap=8192,
                                weights=COUNT_POLICY,lane_rank=rank))
