"""Independent post-pass checker for an admitted prefix of actual eggcc Pass 3."""
import argparse
import json
from pathlib import Path
from statistics import median
from time import perf_counter_ns

import numpy as np
import torch

from certificate import compile_domain,generate_reference_proposal,require


def contract_rows(plan, members, claims):
    bindings=[(1,plan.initializer,()),(2,plan.base_rule,())]
    writes=[(2,plan.base_rule,plan.attribute,int(claims[0,1]),plan.initial_value)]
    for fields,token in zip(members,claims[1:]):
        present,result,parent,depth,value=map(int,token)
        if not present:continue
        slots=dict(zip(plan.constructor_slots,fields))
        slots[plan.value_slot]=int(claims[parent,4])
        bindings.append((2+depth,plan.step_rule,tuple(slots[s] for s in plan.inputs)))
        writes.append((2+depth,plan.step_rule,plan.attribute,result,value))
    events=sorted(bindings)
    rank={key:i for i,key in enumerate(events)}
    # Writes share the original RHS ordering, independent of token storage order.
    ordered_writes=[writes[0]]+[w for _,w in sorted(zip([rank[e] for e in bindings[2:]],writes[1:]))]
    return events, ordered_writes


def audit_prefix(gold, plan, packet, members, claims, init_writes):
    events,expected_writes=contract_rows(plan,members,claims)
    terminal=3+int(claims[:,3].max())
    helper_id=list(packet['sets']).index(plan.ruleset)
    with np.load(gold/'output.npz') as z:
        runs=z['runs'];rhs=z['rhs'];writes=z['writes'];spine=z['resumes']
        require(np.all(runs[1:terminal,0]==helper_id) and runs[terminal,0]!=helper_id and
                runs[terminal-1,1]==0 and runs[terminal-1,3]==0,'actual terminal boundary differs')
        actual=[]
        for row in rhs[rhs[:,0]<=terminal]:
            run,rule=map(int,row[:2]); width=len(packet['rules'][rule]['inputs'])
            actual.append((run,rule,tuple(map(int,row[4:4+width]))))
        require(actual==events,'ordered RHS audit failed')
        observed_writes=[(int(row[0]),int(row[1]),int(row[2]),int(row[4]),int(row[5])) for row in
                         writes[(writes[:,0]<=terminal)&(writes[:,1]!=plan.initializer)]]
        require(observed_writes==expected_writes,'ordered attribute writes audit failed')
        setup=[]
        for row in writes[writes[:,0]==1]:
            table=int(row[2]);arity=len(packet['tables'][table]['schema'])-1
            setup.append((table,tuple(map(int,row[4:4+arity])),int(row[4+arity])))
        require(setup==init_writes,'initializer writes differ')
        nullary={(plan.initializer,1),(plan.base_rule,2)}
        full_empty=[(int(r[1]),int(r[0])) for r in rhs if not packet['rules'][r[1]]['q']]
        require(len(full_empty)==len(nullary) and set(full_empty)==nullary,'later empty-LHS binding')
        later=[]
        initial_keys={fields[:-1] for fields in members}
        initial_classes=set(map(int,claims[:,1]))
        for row in rhs[(rhs[:,0]>terminal)&(rhs[:,1]==plan.step_rule)]:
            bound=dict(zip(plan.inputs,map(int,row[4:4+len(plan.inputs)])))
            key=tuple(bound[s] for s in plan.constructor_slots[:-1])
            result=bound[plan.result_slot];tail=bound[plan.prior_class_slot]
            later.append(dict(run=int(row[0]),constructor_key=key,output=result,tail=tail,
                              reused_constructor_key=key in initial_keys,reused_result=result in initial_classes,
                              used_initial_tail=tail in initial_classes))
        return dict(later_bindings=later,full_pass_empty_lhs_rhs=len(full_empty),source_runs=len(runs),source_rhs=len(rhs),aligned_prefix_runs=terminal,
                    ordered_prefix_rhs=len(events),ordered_prefix_effective_writes=len(init_writes)+len(expected_writes),
                    prefix_spine_resumes=int((spine[:,0]<=terminal).sum()),
                    later_same_step_rhs=int(((rhs[:,0]>terminal)&(rhs[:,1]==plan.step_rule)).sum()))


def naive_fixed_point(plan,domain):
    values={}
    sweeps=probes=0
    while True:
        known=values.copy()
        values[int(domain[0,0])]=plan.initial_value
        for c,parent in domain[1:]:
            probes+=1
            if int(parent) in known:values[int(c)]=known[int(parent)]+plan.increment
        sweeps+=1
        if len(known)==len(values):return values,sweeps,probes


def evaluate_shader(shader,domain,claims,plan,repetitions):
    device=torch.device('mps')
    table=torch.tensor(domain,device=device);tokens=torch.tensor(claims,device=device)
    cfg=torch.tensor([len(domain),plan.initial_value,plan.increment],device=device)
    out=torch.empty((len(domain),2),dtype=torch.int32,device=device)
    def check():
        shader.certify(table,tokens,cfg,out,threads=len(domain))
        torch.mps.synchronize()
        return tuple(map(int,out.cpu().sum(0).tolist()))
    edits={}
    def trial(label,values):
        tokens.copy_(torch.tensor(values,device=device));illegal,missing=check()
        edits[label]=dict(illegal=illegal,uncovered=missing,all_emitted_legal=illegal==0,
                          complete=illegal==0 and missing==0)
    trial('complete',claims)
    parents=set(map(int,claims[1:,2]))
    leaf=next(i for i in reversed(range(1,len(domain))) if i not in parents)
    missing=claims.copy();missing[leaf,0]=0
    trial('delete_valid_leaf',missing)
    empty=claims.copy();empty[:,0]=0
    trial('abstain',empty)
    early=claims.copy();early[leaf,3]-=1
    trial('publish_early',early)
    damaged=claims.copy();damaged[leaf,4]+=1
    trial('wrong_value',damaged)
    swapped=claims.copy()
    pair=next((i,j) for i in range(1,len(domain)) for j in range(i+1,len(domain))
              if claims[i,3]==claims[j,3] and claims[i,2]!=claims[j,2])
    swapped[pair[0],2]=claims[pair[1],2]
    trial('wrong_parent_same_value',swapped)
    duplicate=claims.copy();duplicate[leaf]=claims[0]
    trial('duplicate_seed_at_member_address',duplicate)
    require(edits['complete']['complete'],'valid certificate was rejected')
    require(edits['delete_valid_leaf']['all_emitted_legal'] and not edits['delete_valid_leaf']['complete'],
            'leaf omission escaped coverage')
    require(edits['abstain']['all_emitted_legal'] and edits['abstain']['uncovered']==len(domain),'abstention escaped')
    require(all(not edits[k]['all_emitted_legal'] for k in ('publish_early','wrong_value','wrong_parent_same_value',
                                                            'duplicate_seed_at_member_address')),'invalid evidence accepted')
    tokens.copy_(torch.tensor(claims,device=device));torch.mps.synchronize()
    samples=[]
    for _ in range(repetitions):
        start=perf_counter_ns();check();samples.append((perf_counter_ns()-start)/1000)
    return dict(controls=edits,resident_check_and_host_read_us=samples,median_us=median(samples),
                   token_bytes=claims.nbytes,domain_bytes=domain.nbytes,semantic_waves=int(claims[:,3].max()+2),
                   device_checker_dispatches=1,local_parent_token_reads=len(domain)-1,
                   covered_member_slots=len(domain),supplemental_rhs_from_checker=0)


def main(args):
    require(torch.backends.mps.is_available(),'MPS required')
    shader=torch.mps.compile_shader((Path(__file__).parent/'coverage.metal').read_text())
    results={}
    for case in args.cases:
        packet=json.loads((args.ref/f'release-input-{case}'/'ingress.json').read_text())
        plan,domain,members,setup_writes,build=compile_domain(packet)
        claims=generate_reference_proposal(plan,domain)
        values,sweeps,probes=naive_fixed_point(plan,domain)
        require(values==dict(zip(map(int,claims[:,1]),map(int,claims[:,4]))),'naive closure differs')
        results[case]=dict(build=build,rule_ids=[plan.initializer,plan.base_rule,plan.step_rule],
                           naive_helper_scans=sweeps,naive_edge_key_probes=probes,
                           proof=evaluate_shader(shader,domain,claims,plan,args.repetitions),
                           audit=audit_prefix(args.ref/f'release-{case}',plan,packet,members,claims,setup_writes))
        print(case,results[case]['audit'],flush=True)
    args.out.write_text(json.dumps(results,indent=1)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ref',type=Path);parser.add_argument('out',type=Path)
    parser.add_argument('--cases',nargs='+',default=['sum-bits','dot-product'])
    parser.add_argument('--repetitions',type=int,default=15)
    main(parser.parse_args())
