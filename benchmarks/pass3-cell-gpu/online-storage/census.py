"""Observed physical parent ports and exact source-generation coverage opportunity. No neural credit."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path


def read(path):return json.loads(path.read_bytes())
def fields(x):return json.dumps(x,separators=(',',':'),sort_keys=True)


def analyze(folder,oracle):
    r=read(folder/'references.json');audit=read(folder/'audit.json')
    for k in ('rhs','writes','resumes'):assert audit[k]==read(oracle/f'{k}.json')
    assert read(folder/'state.json')==read(oracle/'state.json')
    reference_events=read(oracle/'events.json')
    def norm(events):return [[v[:5] if v[0]=='birth' else v for v in run if v[0] in ('birth','write','resume','union')] for run in events]
    assert norm(audit['events'])==norm(reference_events)
    lhs=r['lhs'];effects=r['effects'];assert len(lhs)==len(effects)
    # The source snapshot is taken before any sibling write. A receipt is identified by
    # actual physical row, table, full observable tuple, epoch and later mutation history.
    initial={tuple(addr):(t,epoch,fields(value)) for t,addr,epoch,value in r['initial']}
    witnesses=defaultdict(list);latest_mutation={};peak=Counter();both=Counter();reasons=Counter()
    depth={};proofs=Counter();edges=Counter();examples={};runs=defaultdict(list)
    for i,(l,ef) in enumerate(zip(lhs,effects),1):
        epoch,ordinal,rid,_,_=l
        assert ef[:2]==[epoch,rid] and ordinal==len(runs[epoch]);runs[epoch].append(i)
    for run_number,events in enumerate(audit['events'],1):
        ids=runs[run_number]
        for idx in ids:
            epoch,ordinal,rid,ports,status=lhs[idx-1]
            for code in status:reasons[code]+=1
            unresolved=any(c not in (0,1) for c in status)
            have_inputs=[];have_parent=[];recursive=[];recheck=[];rebuild=[];versions=[]
            choices=[]
            for pos,port in enumerate(ports):
                if port is None:continue
                t,addr,version,row=port;addr=tuple(addr);signature=(t,version,fields(row))
                m=latest_mutation.get(addr)
                is_initial=initial.get(addr)==signature and m is None
                candidates=witnesses.get(addr,())
                valid=[c for c in candidates if c[3]==signature and (m is None or m<=c[:2])]
                accepted=[c for c in valid if c[1] in depth]
                # Every genuine immediate mutation can also certify a source effect where its
                # unique typed site was observed. Stale generations remain visible as a diagnostic.
                have_parent.append(bool(valid));have_inputs.append(is_initial)
                recursive.append(0 if is_initial else min((depth[c[1]] for c in accepted),default=None))
                recheck.append(bool(candidates) and not valid)
                rebuild.append(m is not None and m[1]==float('inf') and not valid)
                versions.append(bool(valid))
                edges['table_reads']+=1;edges['initial_live']+=int(is_initial);edges['strict_parent']+=bool(valid)
                edges['mutated_since_last_proof']+=bool(candidates) and not valid
                if valid:
                    parent=valid[-1];assert parent[0]<epoch
                    choices.append(dict(position=pos,table=t,physical=list(addr),epoch=version,producer=parent[1],effect=parent[2]))
                    edges['parent_known_type_pairs']+=1
            n=len(have_inputs)
            if not n and not unresolved:cls='no_table_prerequisite'
            elif not unresolved and all(have_parent):cls='all_table_premises_have_prior_effects'
            elif not unresolved and all(x or y for x,y in zip(have_parent,have_inputs)) and any(have_parent):cls='mixed_initial_and_prior_effects'
            elif not unresolved and all(have_inputs):cls='initial_only'
            elif unresolved:cls='source_witness_not_uniquely_reconstructed'
            else:cls='missing_live_version_or_prior_effect'
            peak[cls]+=1
            peak['at_least_one_live_source_parent']+=any(have_parent)
            if not unresolved and all(d is not None for d in recursive):
                depth[idx]=1+max(recursive,default=0);proofs[depth[idx]]+=1
            if any(recheck):both['some_stale_effect']+=1
            if any(rebuild):both['repair_without_source_writer']+=1
            if cls not in examples and (choices or n==0):
                examples[cls]=dict(rhs=idx,run=epoch,rule=rid,table_premises=n,parents=choices)
        # Publish each *actual* completed effect only at the end of its Run, carrying
        # the row and full snapshot re-read from its own native frame's named operands.
        for idx in ids:
            epoch,rid,finished,outputs=effects[idx-1]
            if not finished:continue
            for op,t,addr,version,row in outputs:
                witnesses[tuple(addr)].append((epoch,idx,op,(t,version,fields(row))))
        # The function index / newly born fact id comes directly from the ordered CPU event.
        # A repair-only update has no source RHS and invalidates prior receipts for this row.
        for ev in events:
            if ev[0]=='birth':
                _,table,key,value,physical,source=ev;addr=(0,physical)
            elif ev[0]=='write':
                _,epoch,source,table,index,key,old,value=ev;addr=(1,index)
            else:continue
            if source is None:latest_mutation[addr]=(run_number,float('inf'))
            else:
                ordinal,rid=source;idx=ids[ordinal];assert lhs[idx-1][2]==rid
                latest_mutation[addr]=(run_number,idx)
    assert sum(v for k,v in peak.items() if k!='at_least_one_live_source_parent')==len(lhs)
    return dict(rhs=len(lhs),runs=r['runs'],classified=dict(peak),recursive_observed_reachable=len(depth),
                remaining_without_observed_closed_chain=len(lhs)-len(depth),min_depth_histogram=dict(sorted(proofs.items())),
                table_witnesses=dict(edges),source_exceptions=dict(both),lookup_reasons=dict(reasons),examples=examples,
                all_observed_graphs_and_ordered_reference_events_equal=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('data','ref','corpus','out'):p.add_argument(k,type=Path)
    a=p.parse_args();report={}
    for case in ('sum-bits','dot-product','gemm-bias-relu','stable-argmax'):
        oracle=a.ref/f'events-{case}' if case in ('sum-bits','dot-product') else a.corpus/case/'observation'
        report[case]=analyze(a.data/f'v3-{case}',oracle)
        print(case,report[case]['rhs'],report[case]['recursive_observed_reachable'],report[case]['classified'],flush=True)
    a.out.write_text(json.dumps(report,indent=1)+'\n')
