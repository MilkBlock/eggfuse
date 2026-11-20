"""Independent commit-order, stream, isolation and Cell provenance audit. Does not import evaluate.py."""
import argparse
from collections import Counter,defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

import numpy as np


def read(path):return json.loads(path.read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def single_plan(rule):
    q=rule['q']
    for pivot in [None,*[i for i,(op,_) in enumerate(q) if isinstance(op,int)]]:
        seen=set() if pivot is None else {s for s in q[pivot][1] if s>=0}
        remaining=[i for i in range(len(q)) if i!=pivot]
        while remaining:
            i=next((i for i in remaining if all(a<0 or a in seen for a in q[i][1][:-1])),None)
            if i is None:break
            seen.update(x for x in q[i][1] if x>=0);remaining.remove(i)
        if not remaining:return True,pivot
    return False,None


def check_tickets(tickets,source,packet,require_alignment):
    seen=set();serial=set()
    low=[single_plan(r)[0] for r in packet['rules']]
    def ticket(n,rid,run,kind):
        assert n>0 and n not in seen and low[rid]==(kind=='single')
        seen.add(n)
        if require_alignment:
            assert n<=len(source)
            np.testing.assert_array_equal(source[n-1,:2],(run,rid))
    for n,epoch,rid,piv,w,version,initial,score,identity,witness in tickets['single']:
        ticket(n,rid,epoch,'single')
        assert identity>0 and identity not in serial and np.isfinite(score);serial.add(identity)
        if piv is not None:assert dict(witness)[piv]==w and w[0] in (1,2)
    for t in tickets['multi']:
        ticket(t['ordinal'],t['rule'],t['run'],'multi')
        assert len(t['anchors'])>=t['width']>=2 and len(t['inputs'])==len(packet['rules'][t['rule']]['inputs'])
    return seen


def audit_recordings(exp,folder):
    summary={}
    for key,arms in read(folder/'results.json').items():
        name,seed=key.split('/');case=exp/'repair-bake-families-20261120'/name
        ref=exp/'pass3-atlas-integration-20261120'
        standard=name in ('sum-bits','dot-product')
        native=ref/f'events-{name}' if standard else case/'observation'
        packet=read((ref/f'release-input-{name}' if standard else case/'input')/'ingress.json')
        with np.load((exp/'recurrent-compositions-20261120'/name)/'output.npz') as z:source=z['rhs'][:,:2]
        assert len(source)==sum(s['executed_bindings'] for s in read(native/'report.json')['steps'])
        for arm,v in arms.items():
            if not v.get('aligned'):
                assert not v['valid_98'];summary[f'{key}/{arm}']=dict(aligned=False,error=v.get('source_error'));continue
            with gzip.open(folder/f'{name}-{seed}-{arm}-ordinals.json.gz','rt') as f:ticket=json.load(f)
            seen=check_tickets(ticket,source,packet,True)
            old_convention=arm=='zero-state' and v['neural_single']==0 and len(ticket['single'])>0
            reported=len(seen)-(len(ticket['single']) if old_convention else 0)
            assert reported==v['total_attributed'] and v['uncredited']==len(source)-reported
            threshold=(98*len(source)+99)//100
            assert v['required']==threshold and v['valid_98']==(reported>=threshold and arm!='broad')
            summary[f'{key}/{arm}']=dict(aligned=True,distinct=len(seen),reported=reported,zero_state_single_excluded=old_convention,source=len(source),required=threshold,
                    leftover=len(source)-len(seen),single=len(ticket['single']),multi=len(ticket['multi']))
    return summary


def score_floors(packet,model):
    if not model.get('certified_inputs'):return [model['threshold']]*len(packet['rules'])
    weights=np.asarray(model['x']);assert not weights[:,[6,7,8,10,11,12]].any()
    radius=np.abs(np.asarray(model['h'])).sum(1)
    out=np.array(model['out']);floors=[]
    for rid,r in enumerate(packet['rules']):
        supported,pivot=single_plan(r)
        if not supported:floors.append(model['threshold']);continue
        q=r['q'];f=np.zeros(14);f[0]=32;f[1]=len(q);f[2]=len(r['inputs'])
        f[3]=sum(isinstance(op,str) for op,_ in q);f[4]=sum(x<0 for _,args in q for x in args)
        if pivot is not None:f[9]=len(q[pivot][1]);f[13]=sum(x<0 for x in q[pivot][1])
        solo=pivot is not None and r['semi'] and all(isinstance(op,str) for i,(op,_) in enumerate(q) if i!=pivot)
        bounds=[]
        for fresh in ([0] if pivot is None else [32] if solo else [0,32]):
            f[5]=fresh;mid=weights@(f.clip(0,32)/32)+model['b']
            bounds.append(float(out@np.tanh(mid-np.sign(out)*radius))+model['bias']+model['rules'][rid%len(model['rules'])])
        floors.append(min(bounds)-.125)
    return floors


def native_value(v):
    if 'eq' in v:return {'Eq':int(v['eq'].removeprefix('Cell(').removesuffix(')'))}
    if v['sort']=='String':return {'Text':v['value']}
    if v['sort'] in ('i64','Unit','bool'):return {'Int':int(v['value'])}
    raise ValueError(f'unsupported native audit sort {v["sort"]}')


def compare_bindings(data,binding_audit):
    flat=[b for run in binding_audit['runs'] for b in run['bindings']]
    for t in data['multi']:
        b=flat[t['ordinal']-1]
        assert b['rule']==t['rule'] and [native_value(x['value']) for x in b['values']]==t['inputs']
    return len(data['multi'])


def prior_fact_audit(archive,packet,plans,events,initial):
    """Rebind sealed physical fact addresses from BEFORE the source Run, independent of the matcher."""
    by_run=defaultdict(list)
    for t in archive:by_run[t['run']].append(t)
    rows={};parents={};verified=0;example=None
    for dep,table,fields,hidden in initial['facts']:
        if not hidden and 'Fact' in dep:
            f=dep['Fact'];rows[(f['cell']<<32)|f['op']]=(table,fields)
    def canon(v):
        if 'Eq' not in v:return v
        a=v['Eq']
        while a in parents:a=parents[a]
        return {'Eq':a}
    for run,changes in enumerate(events,1):
        for t in by_run.get(run,()):
            rule=packet['rules'][t['rule']];q=rule['q'];plan=plans[t['rule']]
            order=[i for i,p,_ in plan['ins'] if p]
            # Check the complete independently reconstructible class here. Other
            # tuples with initial/function parents, primitives or point suffixes
            # are instead covered by the full execution and source digest checks.
            if len(order)!=len(q) or any('Fact' not in w for w in t['anchors']):continue
            refs=[(w['Fact']['cell']<<32)|w['Fact']['op'] for w in t['anchors']]
            if any(w not in rows for w in refs):continue
            if any(a<0 for _,xs in q for a in xs):continue
            bound={}
            for i,w in zip(order,refs):
                name,args=q[i];table,fields=rows[w];assert name==table and len(args)==len(fields)
                for slot,value in zip(args,fields):
                    value=canon(value);assert bound.setdefault(slot,value)==value
            assert [bound[s] for s in rule['inputs']]==t['inputs'],(run,t['ordinal'])
            verified+=1
            if t['rule']==90 and example is None:example=t
        for event in changes:
            if event[0]=='birth':
                _,table,keys,result,handle,*_=event;rows[handle]=(table,[*keys,result])
            elif event[0]=='union':
                _,hi,lo=event;parents[hi]=lo
            elif event[0]=='retire':
                rows.pop(event[1],None)
    assert verified>0
    return dict(fully_rebound_winners=verified,total_winners=len(archive),example=example)


def independent_gate(capture,model,floors,tickets):
    """Evaluate the recurrent scorer using source feature counts. Read positive labels only after masking."""
    c=read(capture/'report.json')['single_witness'];x=np.asarray(c['features'],np.float32)/32
    vec=lambda key:np.asarray(model[key],np.float32)
    base=x@vec('x').T+vec('b');hidden=np.zeros(4,np.float32);counts=[0,0,0,0]
    all_send=some_send=none_send=0
    by_serial={t[8]:t for t in tickets}
    for rid,n,groups in c['events']:
        ids=np.array([i for i,_ in groups]);dist=np.array([ab for _,ab in groups]);frequency=dist.sum(1)
        assert frequency.sum()==n
        score=np.tanh(base[ids]+hidden@vec('h').T)@vec('out')+model['bias']+model['rules'][rid%len(model['rules'])]
        mask=score>=floors[rid]
        sent=int(frequency@mask)
        winners=[by_serial[i] for i in range(counts[0]+1,counts[0]+n+1) if i in by_serial]
        assert all(t[2]==rid and t[7]>=floors[rid]-1e-4 for t in winners)
        positive_scores=np.repeat(score[mask],dist[:,1][mask])
        np.testing.assert_allclose(sorted(t[7] for t in winners),np.sort(positive_scores),rtol=2.e-5,atol=2.e-5)
        hidden=np.tanh(vec('recurrent')@hidden+vec('update')@np.array(
            [min(n,128)/128,sent/n,float(frequency@x[ids,5])/n,(rid%64)/63],np.float32)+vec('rbias'))
        counts[0]+=n;counts[1]+=sent;counts[2]+=int(dist[:,1].sum());counts[3]+=int(dist[:,1]@mask)
        all_send+=sent==n;none_send+=sent==0;some_send+=0<sent<n
    return dict(offered=counts[0],sent=counts[1],valid=counts[2],valid_sent=counts[3],
                full_rule_occurrences=all_send,partial_rule_occurrences=some_send,abstaining_rule_occurrences=none_send)


def isolated(exp,name,seed,arm,folder,build):
    ref=exp/'pass3-atlas-integration-20261120';case=exp/'repair-bake-families-20261120'/name
    standard=name in ('sum-bits','dot-product')
    native=ref/f'events-{name}' if standard else case/'observation'
    program=ref/name/'program.json' if standard else case/'program.json'
    packet=read((ref/f'release-input-{name}' if standard else case/'input')/'ingress.json')
    weights=exp/'joint-98-weights-v1'/str(seed)/'model.json'
    plans=folder/f'{name}-plans.json';cfg=folder/f'{name}-{seed}-{arm}.json'
    with tempfile.TemporaryDirectory(dir='/private/tmp') as tmp:
        root=Path(tmp).resolve()
        pairs={'engine':build/'session','source':program,'grammar':plans,'gate':cfg,'pointer':weights}
        for alias,p in pairs.items():shutil.copy2(p,root/alias)
        # Deny the host workspaces, reference volumes, user homes and other
        # temporary artifacts; the runtime can read the five copied inputs.
        # A separate process must actually fail to open the source oracle.
        profile=f'(version 1)(allow default)(deny network*)(deny file-read* (subpath "/Volumes") (subpath "/Users") (subpath "/private/tmp") (subpath "/private/var/folders") (subpath "/System/Volumes/Data/Volumes") (subpath "/System/Volumes/Data/Users"))(allow file-read* (subpath "{root}"))'
        guard=['/usr/bin/sandbox-exec','-p',profile]
        negative=subprocess.run([*guard,'/bin/cat',str(native/'rhs.json')],capture_output=True,cwd=root)
        assert negative.returncode and b'Operation not permitted' in negative.stderr and not negative.stdout,negative.stderr
        record=read(folder/'results.json')[f'{name}/{seed}'][arm]
        cfgdata=read(cfg)
        assert cfgdata['residual']==record['single_residual']
        if arm=='strict':assert not cfgdata['residual'] and not cfgdata.get('complete_unsupported',False) and not record['multi_residual']
        mode=('stackseal' if read(build/'build.json').get('shortlist') else 'seal')+'3xlearned'
        req=dict(single_config=str(root/'gate'),multi_weights=str(root/'pointer'),multi_mode=mode,
                 multi_residual=record['multi_residual'],radius=2,cap=1000000,audit=True)
        proc=subprocess.run([*guard,str(root/'engine'),str(root/'source'),str(root/'grammar')],input=json.dumps(req)+'\n',
                            capture_output=True,text=True,cwd=root,check=True,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
        run=json.loads(proc.stdout);inputs={k:sha(v) for k,v in pairs.items()}
    # Source references are first read by the independent auditor, after the child has exited.
    single,multi=run['single'],run['multi']
    assert single['residual']==cfgdata['residual']
    if 'complete_unsupported' in single:assert single['complete_unsupported']==cfgdata.get('complete_unsupported',cfgdata['residual'])
    with np.load(exp/'recurrent-compositions-20261120'/name/'output.npz') as z:source=z['rhs'][:,:2]
    data=dict(single=single['committed'],multi=multi['tickets'])
    with gzip.open(folder/f'{name}-{seed}-{arm}-ordinals.json.gz','rt') as f:assert data==json.load(f)
    seen=check_tickets(data,source,packet,True)
    for field in ('rhs','writes','resumes'):assert run[field]==read(native/f'{field}.json')
    events=read(native/'events.json')
    unions=lambda e:[[v for v in step if v[0]=='union'] for step in e]
    assert unions(run['events'])==unions(events)
    steps=read(native/'report.json')['steps']
    assert run['schedule']==[[s[k] for k in ('ruleset','epoch','path','iterations','executed_bindings','changed')] for s in steps]
    assert run['state_sha']==sha(native/'state.json') and multi['raw_sha256']==record['multi_raw_sha']
    assert len(seen)==record['total_attributed'] and single['rhs']==multi['total_rhs']==len(source)
    floors=score_floors(packet,cfgdata['model'])
    if 'floors' in single:np.testing.assert_allclose(single['floors'],floors,atol=1.e-4,rtol=1.e-5)
    gates=independent_gate(exp/'native-single-witness-capture2'/name,cfgdata['model'],floors,data['single'])
    assert gates['sent']==single['work'][1] and gates['offered']==single['work'][0] and gates['valid_sent']==len(data['single'])
    cells=run['cell_ids'];alloc=run['allocations'];assert len(alloc)==len(source)
    np.testing.assert_array_equal(source,np.asarray(alloc)[:,:2])
    assert len(cells)==run['new_cells']
    by_owner=Counter(c[0] for c in cells)
    assert all(by_owner[i]==a[2] for i,a in enumerate(alloc,1))
    fresh=[c for c in cells if not c[4]];assert len({c[1] for c in fresh})==len(fresh)
    owned=sum(c[0] in seen for c in fresh);direct=sum(c[0] in seen and c[2]==c[3] for c in fresh)
    templates={r['rule']:i for i,r in enumerate(read(program)['templates'])}
    for c in fresh:
        if c[0]:assert c[3]==templates[int(source[c[0]-1,1])]
    assert direct==record['instance_audit']['source_rule_template_matches']
    repair_events=read(case/'observation/events.json')
    assert unions(repair_events)==unions(events)
    result=dict(case=name,seed=seed,arm=arm,inputs=inputs,oracle_read_denied=True,distinct=len(seen),
                source=len(source),required=(98*len(source)+99)//100,single_work=single['work'],single_replay=gates,
                single_rules_always_send=sum(v[1]==v[2] and v[1]>0 for v in single['rules'].values()),
                single_wins_in_always_send_rules=sum(v[3] for v in single['rules'].values() if v[1]==v[2] and v[1]>0),
                multi_raw_hash=multi['raw_sha256'],raw_tuples=multi['counts']['raw_tuples'],statically_required_check=cfgdata['model'].get('certified_inputs',False),
                guarded_reissued=len(single.get('guarded_ordinals',[])),
                fresh=len(fresh),rhs_owned=owned,direct_template=direct,fresh_unowned=sum(not c[0] for c in fresh),
                promotions=len(cells)-len(fresh),actual_issued_before_verification=multi['sealed_before_verifier'],
                independent_all_multi_inputs=compare_bindings(data,read(ref/f'oracle-{name}'/'binding-audit.json')),
                source_fact_replay=prior_fact_audit(data['multi'],packet,read(plans),repair_events,read(case/'observation/repair-inputs.json')))
    if arm=='strict':assert single['work'][2]==single['work'][1] and single['work'][6]==0 and len(seen)==len(source)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('experiments',type=Path)
    parser.add_argument('--out',type=Path);parser.add_argument('--case',default='sum-bits');parser.add_argument('--seed',default='1703')
    a=parser.parse_args();e=a.experiments
    recordings=[('joint-98-checked-v4','joint-98-witness-build-v4','target'),('joint-98-autonomous-v1','joint-98-final-certified-v1','strict')]
    out={}
    for directory,build,arm in recordings:
        folder=e/directory
        archived=audit_recordings(e,folder)
        isolated_run=isolated(e,a.case,a.seed,arm,folder,e/build)
        out[directory]=dict(archive=archived,isolated=isolated_run)
        print(directory,isolated_run,flush=True)
    corrected=e/'joint-98-template-audit-v1';c=audit_recordings(e,corrected)
    for key,v in c.items():
        if key.endswith('/zero-state'):
            original=out['joint-98-checked-v4']['archive'][key]
            assert original['distinct']==v['reported']==v['distinct']
            name,seed,_=key.split('/')
            fname=f'{name}-{seed}-zero-state-ordinals.json.gz'
            assert json.load(gzip.open(corrected/fname))==json.load(gzip.open(e/'joint-98-checked-v4'/fname))
    out['corrected_zero_state']={k:v for k,v in c.items() if k.endswith('/zero-state')}
    expanded=e/'joint-98-autonomous-v2'
    if (expanded/'results.json').exists():
        stricts=audit_recordings(e,expanded)
        out['expanded_strict_archives']={k:v for k,v in stricts.items() if k.endswith('/strict')}
        assert all(v['aligned'] and v['distinct']==v['source'] for v in out['expanded_strict_archives'].values())
    if a.out:a.out.write_text(json.dumps(out,indent=1)+'\n')
