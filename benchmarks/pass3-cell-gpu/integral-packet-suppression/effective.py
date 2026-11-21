"""Count original constructor fact identities created during applied tickets and visible at export."""
import json,argparse
import importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
sp=importlib.util.spec_from_file_location('proof_measure',HERE/'probe.py')
probe=importlib.util.module_from_spec(sp);sp.loader.exec_module(probe)

def run(a):
    a.out.mkdir(parents=True,exist_ok=True);results={}
    for case in a.cases:
        prog,plan,req=probe.src.config(a,case);req.update(header_mode=3,derived_ports=dict(mode=1,cache=True),lazy_equations=4,multi_page_tuples=8192,proposal_wave=65536,integral_root='apply',birth_ledger=True,audit=True)
        cases={}
        for label,active in [('external',False),('closed',True)]:
            with probe.src.base.session(a.native,prog,plan) as infer:v=infer(dict(req,integral_packets=active))
            records=v['constructor_births'];vis={r[0] for r in records['endpoint'] if r[2]==0}
            root_serials={r[2] for r in v['root_recipe']['commits']};owned=set();without=set()
            for fid,tab,epoch,ctor,token,root,cross,flags in records['rows']:
                if not ctor or not flags&1:continue
                if token:
                    assert token in root_serials;owned.add(fid)
                else:without.add(fid)
            nroot=v['root_recipe']['emitted'];child=v['merge_child']['issued'];counts=v['integral_root']['counts']
            packet_count=sum(nroot)+sum(int(c['selected']) for c in child)
            cases[label]=dict(issued=nroot,all_child_decisions=len(child),selected_child=sum(int(c['selected'])for c in child),root_and_selected_child=packet_count,
                              owned_births=len(owned),owned_visible=len(owned&vis),other_births=len(without),other_visible=len(without&vis),
                              birth_per_packet=len(owned)/packet_count,visible_per_packet=len(owned&vis)/packet_count,
                              release_checks={k:counts[k] for k in ('delta_ports','anchor_reads','point_reads','primitives','offers')},
                              wire_bytes=v['root_recipe']['wire_bytes'])
        assert all(cases['external'][k]==cases['closed'][k] for k in ('owned_births','owned_visible','other_births','other_visible','all_child_decisions','selected_child'))
        results[case]=cases;(a.out/'effective.json').write_text(json.dumps(results,indent=1)+'\n')
        print(case,cases,flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','3mm'])
    run(p.parse_args())
