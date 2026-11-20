"""Freeze structural choices and compare supplying an i64, explaining an i64, and resolving a visible port."""
import argparse
from collections import Counter
import json
from pathlib import Path
from statistics import median
import sys
from time import perf_counter_ns

import numpy as np
import torch

from adapter import specialize,run
from plan import plan,read
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'recurrent-generator'))
from capture import inputs,verify


def analyze(folder,rules,definition,*,has_prediction=False):
    by_id={r['rule']:r for r in rules}
    with np.load(folder/'numeric.npz') as z,np.load(folder/'output.npz') as graph:
        f,args,out=z['features'],z['args'],z['outcomes'];ports=z['input_ports'];rhs,writes=graph['rhs'],graph['writes']
        profile={}
        def scope(records,outcomes):
            c=Counter()
            for ordinal in outcomes:
                o=out[ordinal]
                run,rid,had,old,candidate,visible,changed,provenance,disposition,physical,tab,epoch,pred,key=map(int,o[:14])
                expected=min(old,candidate) if had else candidate
                assert expected==visible and changed==int(not had or visible!=old)
                c['total']+=1;c['wrote']+=changed;c['noop']+=1-changed
                c['first' if not had else 'old_lt_candidate' if old<candidate else 'old_eq_candidate' if old==candidate else 'old_gt_candidate']+=1
                if changed:
                    # The source logs effective function writes with the rule-local binding ordinal inside the Run.
                    run_start=np.searchsorted(rhs[:,0],run)
                    matches=writes[(writes[:,0]==run)&(writes[:,1]==rid)&(writes[:,-1]==ordinal-run_start)&(writes[:,2]==tab)]
                    assert len(matches)==1 and tuple(matches[0,-3:-1])==(had,old) and matches[0,5]==visible
                if provenance:
                    i=provenance-1;assert f[i,13]==ordinal+1
                    expected_candidate=sum(map(int,args[i,:len(by_id[rid]['slots'])]))+by_id[rid]['literal']
                    assert expected_candidate==candidate,(rid,args[i],candidate)
                    if f[i,11]:
                        c['structural_winners']+=1
                        c['admitted']+=int(disposition==1);c['numeric_rejected_and_recovered']+=int(disposition==2)
                        c['admitted_writes']+=int(disposition==1)*changed
                        assert disposition in (1,2)
                        for argument,(address,parent) in enumerate(ports[i,:len(by_id[rid]['slots'])]):
                            if address:c['physical_operand_refs']+=1
                            if parent:
                                previous=out[parent-1]
                                assert 0<previous[0]<run and previous[9]==address-1
                                assert args[i,argument]==previous[5]
                                c['validated_parent_ports']+=1
                                c['parent_port_from_admitted_token']+=int(previous[8]==1)
                                c['parent_candidate_differs_from_visible']+=int(previous[4]!=previous[5])
            c['presented']=len(records);c['structural_proposals']=int(f[records,11].sum())
            c['routes_passed_for_selected']=int(((f[records,11]==1)&(f[records,12]==1)).sum())
            return dict(c)
        used=np.flatnonzero(out[:,0]);profile['all']=scope(np.arange(len(f)),used)
        for r in rules:
            rid=r['rule']
            if 'Concat' in definition[rid]['metadata']['name']:
                profile['concat']=scope(np.flatnonzero(f[:,1]==rid),np.flatnonzero((out[:,0]!=0)&(out[:,1]==rid)))
        profile['ports']=z['port_stats'].tolist()
        chosen=sorted((tuple(map(int,row[:4])) for row in f[f[:,11]==1]))
        audit=out[:,[0,1,2,3,4,5,6,9,10,11,13]].copy()
        profile['examples']=[]
        for ordinal in used:
            o=out[ordinal];rid=int(o[1])
            if 'Concat' not in definition[rid]['metadata']['name'] or not o[7]:continue
            if len(profile['examples'])>=3:break
            operands=args[o[7]-1,:len(by_id[rid]['slots'])]
            profile['examples'].append(dict(run=int(o[0]),rhs=int(ordinal+1),rule=rid,operands=operands.tolist(),
                parent_rows=(ports[o[7]-1,:len(operands),0]-1).tolist(),source_rhs_ports=ports[o[7]-1,:len(operands),1].tolist(),
                old=int(o[3]) if o[2] else None,candidate=int(o[4]),visible=int(o[5]),write=bool(o[6]),selected=bool(f[o[7]-1,11]),
                predicted=int(o[12]) if has_prediction and o[8] else None,disposition=int(o[8])))
        return profile,chosen,audit


def study(a):
    a.out.mkdir(parents=True,exist_ok=False);summary={}
    for case in a.cases:
        image,program,gold=inputs(a.corpus,a.ref,case)
        rules=plan(program,image);ingress=read(image/'ingress.json');definition=read(program)['recipe']['rules']
        for seed in a.seeds:
            model=read(a.model/f'model-{seed}.json');sessions={};reports={}
            for arm,mode,direct in [('engine',None,False),('trace-control','structural',False),('predicted','predict',False),('structural','structural',False),
                                     ('visible-port','structural',1),('candidate-as-visible','structural',2),('forced-wrong','wrong',False)]:
                policy=model if arm!='trace-control' else {**model,'selector':[0.]*7+[-1e6]}
                fn=run.execute if not mode else specialize(rules,ingress,policy,mode,direct)
                def bind(infer,buf,*_):
                    original={k:buf[k].clone() for k in ('state','meta','head','dyn','wm')}
                    def reset():
                        for k,t in original.items():buf[k].copy_(t)
                        for k in ('regs','count','rhs','runs','writes','resumes'):buf[k].zero_()
                    sessions[arm]=reset,infer,buf
                timed=arm in ('engine','trace-control','predicted','structural','visible-port')
                dest=a.out/f'{case}-{seed}-{arm}'
                fn(image/'device.json',a.reader,a.ref/'ports-1703.pt',2048,2,dest,measure_resident=bind if timed else None)
                verify(dest,gold,image)
                if mode:
                    reports[arm],selected,trace=analyze(dest,rules,definition,has_prediction=mode in ('predict','wrong'))
                    if arm=='trace-control':assert not selected
                    elif arm=='predicted':ref_selection,ref_trace=selected,trace
                    else:assert selected==ref_selection;np.testing.assert_array_equal(trace,ref_trace)
                else:reports[arm]={}
                if timed:reports[arm]['ms']=[]
            order=list(sessions)
            with np.load(gold/'output.npz') as z:truth={k:z[k] for k in ('rhs','runs','writes','resumes')}
            for t in range(len(order)*2):
                seq=order[t%len(order):]+order[:t%len(order)]
                for arm in seq if t<len(order) else seq[::-1]:
                    reset,infer,buf=sessions[arm];reset();torch.mps.synchronize()
                    start=perf_counter_ns();infer();torch.mps.synchronize();reports[arm]['ms'].append((perf_counter_ns()-start)/1e6)
                    state=buf['state'].cpu().tolist();assert state[7] and not state[5]
                    for k,i in [('runs',11),('rhs',9),('writes',10),('resumes',16)]:
                        got,want=buf[k][:state[i]].cpu().numpy(),truth[k]
                        if k=='rhs':np.testing.assert_array_equal(got[:,:2],want[:,:2]);got,want=got[:,4:],want[:,4:]
                        np.testing.assert_array_equal(got,want)
            for arm in order:reports[arm]['median_ms']=median(reports[arm]['ms'])
            summary[f'{case}/{seed}']=reports
            (a.out/'results.json').write_text(json.dumps(summary,indent=1)+'\n')
            print(case,seed,reports['predicted']['concat'],reports['visible-port']['ports'],flush=True)
            sessions.clear()


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    for s in ('corpus','ref','reader','model','out'):ap.add_argument(s,type=Path)
    ap.add_argument('--cases',nargs='+',default=['sum-bits','dot-product'])
    ap.add_argument('--seeds',nargs='+',type=int,default=[1703,1709])
    with torch.inference_mode():study(ap.parse_args())
