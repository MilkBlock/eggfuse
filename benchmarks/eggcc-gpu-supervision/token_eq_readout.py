"""Dictionary-free Eq boundary readout audit of frozen whole-Cell tokens.

This is not the inference model: it cannot create constructors, scalar results,
match candidates, or authorize union. Captured CPU equality is the audit label.
"""
import argparse
from collections import defaultdict
import hashlib,json,time
from pathlib import Path
import numpy as np
import mlx.core as mx
from collect_observed_corpus import read_bytes
from multi_entry_ridge import dataset,template,vec,WIDTH
from whole_cell_ridge import train
from packed_cell_replay import prepare,executor,audit


def pair_layout(rule):
    roles,q=template(rule);groups=defaultdict(list)
    for i,s in enumerate(rule['slots']):
        if s['sort']['kind']=='eq':groups[s['sort']['name']].append(i)
    pairs=[(a,b) for slots in groups.values() for j,a in enumerate(slots) for b in slots[j+1:]]
    positioned=np.array([np.tanh(v+vec(('static_slot',i))) for i,v in enumerate(roles)],np.float32)
    a=np.array([positioned[i] for i,_ in pairs],np.float32).reshape(-1,64)
    b=np.array([positioned[j] for _,j in pairs],np.float32).reshape(-1,64)
    return pairs,q,a+b,abs(a-b),a*b


def static_equalities(rule,pairs):
    sorts={i:s['sort']['name'] for i,s in enumerate(rule['slots']) if s['sort']['kind']=='eq'}
    parent={i:i for i in sorts}
    def root(i):
        while parent[i]!=i:i=parent[i]
        return i
    def unite(a,b):
        if a in sorts and b in sorts and sorts[a]==sorts[b]:parent[root(b)]=root(a)
    for op in rule['effects']:
        if op['kind']=='copy' and 'slot' in op.get('arg',{}):unite(op['dst'],op['arg']['slot'])
        elif op['kind']=='union' and all('slot' in a for a in op['args']):unite(op['args'][0]['slot'],op['args'][1]['slot'])
    return np.array([root(a)==root(b) for a,b in pairs],bool)


def quotient_layout(rule,pairs,proof):
    """Compile class-pair queries and expansion using completed static facts only."""
    parent={a:a for pair in pairs for a in pair}
    def root(a):
        while parent[a]!=a:a=parent[a]
        return a
    for (a,b),yes in zip(pairs,proof):
        if yes:parent[root(b)]=root(a)
    classes=defaultdict(list)
    for a in sorted(parent):classes[root(a)].append(a)
    roles,_=template(rule)
    descriptors={k:np.mean([np.tanh(roles[i]+vec(('static_slot',i))) for i in members],axis=0)
        for k,members in classes.items()}
    lookup={};representatives=[];expansion=[];left=[];right=[]
    for i,(a,b) in enumerate(pairs):
        a,b=sorted((root(a),root(b)))
        if a==b:expansion.append(-1);continue
        key=(a,b)
        if key not in lookup:
            lookup[key]=len(representatives);representatives.append(i)
            left.append(descriptors[a]);right.append(descriptors[b])
        expansion.append(lookup[key])
    a=np.array(left,np.float32).reshape(-1,64);b=np.array(right,np.float32).reshape(-1,64)
    return dict(expansion=np.array(expansion,int),representatives=np.array(representatives,int),
        s=a+b,d=abs(a-b),p=a*b)


def readout_rows(rows,quotient):
    if not quotient:return rows
    out=[]
    for r in rows:
        plan=r['quotient'];ids=plan['representatives'];y=r['y'][ids]
        dynamic=plan['expansion']>=0
        if not np.array_equal(y[plan['expansion'][dynamic]],r['y'][dynamic]):
            raise ValueError('static quotient labels inconsistent')
        out.append(dict(r,pairs=[r['pairs'][i] for i in ids],y=y,static=np.zeros(len(ids),bool),
            s=plan['s'],d=plan['d'],p=plan['p']))
    return out


def expand_scores(row,scores,skip_static,quotient):
    if quotient:
        mapping=row['quotient']['expansion'];mask=mapping>=0
        result=np.ones(len(mapping),np.float32);result[mask]=scores[mapping[mask]]
    else:
        mask=~row['static'] if skip_static else np.ones(len(row['pairs']),bool)
        result=np.ones(len(mask),np.float32);result[mask]=scores
    return result


def examples(trace,channels,zero,quotient=False,encoding="slot"):
    nodes=dataset(trace,channels,zero,encoding);layouts=[pair_layout(r) for r in trace['recipe']['rules']]
    proofs=[static_equalities(r,layout[0]) for r,layout in zip(trace['recipe']['rules'],layouts)]
    plans=[quotient_layout(r,layout[0],proof) for r,layout,proof in zip(trace['recipe']['rules'],layouts,proofs)] if quotient else None
    out=[];index=0
    for run in trace['runs']:
        for ordinal,b in enumerate(run['audit']['bindings']):
            n=nodes[index];index+=1
            if not n['valid']:continue
            pairs,q,s,d,p=layouts[b['rule']]
            ports={v['slot']:v['eq_port'] for v in b['rhs']['slots'] if 'eq_port' in v}
            truth=[]
            for i,j in pairs:
                if i not in ports or j not in ports:raise ValueError('missing typed Eq result')
                x,y=ports[i],ports[j]
                truth.append(x['sort']==y['sort'] and x['after_run']==y['after_run'])
            y=np.array(truth,bool);proof=proofs[b['rule']]
            if (proof&~y).any():raise ValueError('static equality contradicted by captured result')
            out.append(dict(index=index-1,run=run['ordinal'],ordinal=ordinal,rule=b['rule'],node=n,pairs=pairs,q=q,s=s,d=d,p=p,y=y,static=proof,quotient=plans[b['rule']] if plans else None))
    return nodes,out


def features(z,q,s,d,p,w,xp):
    raw=xp.concatenate([z,q,s,d,p,z[:,:64]*s,z[:,64:]*d],axis=1)
    return xp.concatenate([xp.ones((len(z),1),dtype=xp.float32),raw,xp.tanh(raw@w)],axis=1)


def materialize(rows,tokens,w,skip_static=False):
    chunks=[];labels=[]
    for r in rows:
        mask=~r['static'] if skip_static else np.ones(len(r['pairs']),bool);n=int(mask.sum())
        if not n:continue
        z=np.broadcast_to(tokens[r['index']],(n,WIDTH));q=np.broadcast_to(r['q'],(n,64))
        chunks.append(features(z,q,r['s'][mask],r['d'][mask],r['p'][mask],w,np));labels.append(r['y'][mask])
    if not chunks:return np.empty((0,1+w.shape[0]+w.shape[1]),np.float32),np.empty(0,bool)
    return np.concatenate(chunks),np.concatenate(labels)


def check_partition(pairs,truth,scores):
    predicted=scores>=.5;parent={}
    def root(a):
        parent.setdefault(a,a)
        while parent[a]!=a:a=parent[a]
        return a
    for (a,b),yes in zip(pairs,predicted):
        if yes:parent[root(b)]=root(a)
    closed=np.array([root(a)==root(b) for a,b in pairs],bool)
    return dict(pairs=len(pairs),true_equal=int(truth.sum()),false_merges=int((predicted&~truth).sum()),
        missed_equalities=int((~predicted&truth).sum()),
        nontransitive=bool((closed!=predicted).any()),
        closure_false_merges=int((closed&~truth).sum()),
        exact=bool(len(pairs)>0 and np.array_equal(predicted,truth)))


def main():
    p=argparse.ArgumentParser();p.add_argument('training',type=Path);p.add_argument('validation',type=Path)
    p.add_argument('test_trace',type=Path);p.add_argument('model',type=Path);p.add_argument('model_report',type=Path)
    p.add_argument('decoder',type=Path);p.add_argument('output',type=Path);p.add_argument('--static-equalities',action='store_true');p.add_argument('--marks',type=Path);p.add_argument('--quotient',action='store_true');a=p.parse_args()
    if a.quotient and not a.static_equalities:p.error('--quotient requires --static-equalities')
    report=json.loads(a.model_report.read_text())
    if hashlib.sha256(a.model.read_bytes()).hexdigest()!=report['model_sha256']:raise ValueError('model mismatch')
    with np.load(a.model) as saved:
        mw=saved['w'];mc=saved['coef'];channels=int(saved['channels']);zero=bool(saved['zero_role_channels'])
        encoding=str(saved['encoding']) if 'encoding' in saved else 'slot'
    w=np.random.default_rng(208).normal(0,1/np.sqrt(512),(512,256)).astype(np.float32)
    xs=[];ys=[];parts=[];seen=set();families=set();unique_counts={}
    preparation_started=time.monotonic()
    for name,path in [('train',a.training),('validation',a.validation)]:
        raw=path.read_bytes();manifest=json.loads(raw)
        if hashlib.sha256(raw).hexdigest()!=report['provenance'][name] or manifest['partition']!=name:raise ValueError('partition provenance mismatch')
        dedup=set()
        for entry in manifest['cases']:
            if entry['status']!='complete':continue
            if entry['split']!=name:raise ValueError('case partition mismatch')
            data=read_bytes(Path(entry['trace']))
            if hashlib.sha256(data).hexdigest()!=entry['trace_sha256']:raise ValueError('trace mismatch')
            nodes,rows=examples(json.loads(data),channels,zero,a.quotient,encoding);selected=[]
            for r in rows:
                n=r['node'];key=(n['family'],n['state_key'])
                if name=='train':seen.add(key);families.add(n['family'])
                if key in dedup:continue
                dedup.add(key);selected.append(r)
            if selected:
                x,y=materialize(readout_rows(selected,a.quotient),np.array([n['target'] for n in nodes]),w,a.static_equalities)
                xs.append(x);ys.append(y);parts.extend([name]*len(y))
        unique_counts[name]=len(dedup)
    x=np.concatenate(xs);y=np.concatenate(ys);parts=np.array(parts)
    preparation_seconds=time.monotonic()-preparation_started;clock=time.monotonic()
    coef,fit=train(x,y[:,None].astype(np.float32),parts=='train',parts=='validation')
    fit_seconds=time.monotonic()-clock
    with a.decoder.open('wb') as f:np.savez_compressed(f,w=w,coef=coef,static_equalities=a.static_equalities,quotient=a.quotient)
    raw=read_bytes(a.test_trace)
    if hashlib.sha256(raw).hexdigest()!=report['provenance']['test_trace']:raise ValueError('test mismatch')
    clock=time.monotonic();nodes,rows=examples(json.loads(raw),channels,zero,a.quotient,encoding)
    test_preparation_seconds=time.monotonic()-clock
    plans={id(r['quotient']):r['quotient'] for r in rows if r['quotient'] is not None}
    quotient_layout_bytes=sum(v.nbytes for plan in plans.values() for v in plan.values())
    if not mx.metal.is_available():raise RuntimeError('Metal required')
    mx.set_default_device(mx.gpu)
    # Frozen whole-Cell model still runs on GPU; the boundary probe is separate.
    predicted=np.array(executor(nodes,mw,mc,prepare(nodes,'two'),True)())
    tokens={'oracle':np.array([n['target'] for n in nodes]),'predicted':predicted}
    results={};gc=mx.array(coef);mark_file=a.marks.open('w') if a.marks else None;mark_count=0
    for mode,state in tokens.items():
        clock=time.monotonic();matrix,labels=materialize(readout_rows(rows,a.quotient),state,w,a.static_equalities);encoding_seconds=time.monotonic()-clock
        clock=time.monotonic();chunks=[]
        for begin in range(0,len(matrix),4096):
            out=mx.array(matrix[begin:begin+4096])@gc;mx.eval(out);chunks.append(np.array(out[:,0]))
        scores=np.concatenate(chunks) if chunks else np.empty(0,np.float32);readout_seconds=time.monotonic()-clock
        reference=(matrix@coef)[:,0];numeric=audit(scores,reference)
        numeric['threshold_disagreements']=int(((scores>=.5)!=(reference>=.5)).sum())
        summaries=defaultdict(lambda:dict(instances=0,query_instances=0,no_comparable_pairs=0,exact_partitions=0,pairs=0,true_equal=0,false_merges=0,missed_equalities=0,nontransitive=0,closure_false_merges=0,static_equal_pairs=0,learned_pairs=0,learned_queries=0,static_only_instances=0,static_baseline_exact=0,wins_vs_static=0,losses_vs_static=0))
        offset=0;clock=time.monotonic()
        for r in rows:
            n=r['node'];key=(n['family'],n['state_key']);count=len(r['pairs'])
            mask=~r['static'] if a.static_equalities else np.ones(count,bool);learned=int(mask.sum())
            queries=len(r['quotient']['representatives']) if a.quotient else learned
            complete_scores=expand_scores(r,scores[offset:offset+queries],a.static_equalities,a.quotient);offset+=queries
            result=check_partition(r['pairs'],r['y'],complete_scores)
            baseline=check_partition(r['pairs'],r['y'],r['static'].astype(np.float32))
            if mark_file is not None and count and not result['exact']:
                errors=[dict(slots=list(pair),predicted_equal=bool(score>=.5),expected_equal=bool(truth))
                    for pair,score,truth in zip(r['pairs'],complete_scores,r['y']) if (score>=.5)!=truth]
                mark_file.write(json.dumps(dict(mode=mode,run=r['run'],binding=r['ordinal'],rule=r['rule'],
                    node_index=r['index'],reason='Eq boundary readout disagrees with CPU capture',
                    false_merges=result['false_merges'],missed_equalities=result['missed_equalities'],
                    nontransitive=result['nontransitive'],errors=errors,union_authorized=False))+'\n');mark_count+=1
            subset='seen_state' if key in seen else 'new_state_known_template' if n['family'] in families else 'new_template'
            for group in ('all',subset):
                s=summaries[group];s['static_baseline_exact']+=int(baseline['exact']);s['wins_vs_static']+=int(result['exact'] and not baseline['exact']);s['losses_vs_static']+=int(baseline['exact'] and not result['exact']);s['static_equal_pairs']+=count-learned;s['learned_pairs']+=learned;s['learned_queries']+=queries;s['static_only_instances']+=int(count>0 and learned==0);s['instances']+=1;s['query_instances']+=int(count>0);s['no_comparable_pairs']+=int(count==0);s['exact_partitions']+=int(result['exact'])
                for field in ('pairs','true_equal','false_merges','missed_equalities','nontransitive','closure_false_merges'):s[field]+=result[field]
        for summary in summaries.values():
            summary['marked_partitions']=summary['query_instances']-summary['exact_partitions']
            summary['mark_rate']=summary['marked_partitions']/summary['query_instances'] if summary['query_instances'] else None
            positives=summary['true_equal']-summary['static_equal_pairs']
            summary['learned_positive_recall']=(positives-summary['missed_equalities'])/positives if positives else None
        audit_seconds=time.monotonic()-clock
        if offset!=len(scores):raise ValueError('query alignment error')
        results[mode]=dict(boundary_feature_bytes=matrix.nbytes,subsets=dict(summaries),numerical_audit=numeric,feature_encoding_seconds=encoding_seconds,
            gpu_readout_and_transfer_seconds=readout_seconds,cpu_partition_audit_seconds=audit_seconds)
    if mark_file is not None:mark_file.close()
    result=dict(local_marks=mark_count,marks_sha256=hashlib.sha256(a.marks.read_bytes()).hexdigest() if a.marks else None,
        union_authorized=False,scalar_and_external_identity_validation_required=True,scope='dictionary-free Eq boundary decoder of whole-Cell tokens, not Eq-only inference',
        model_sha256=report['model_sha256'],decoder_sha256=hashlib.sha256(a.decoder.read_bytes()).hexdigest(),
        provenance=report['provenance'],fit=fit,unique_training_states=unique_counts,
        training_pairs=int((parts=='train').sum()),validation_pairs=int((parts=='validation').sum()),
        training_equal_pairs=int(y[parts=='train'].sum()),preparation_seconds=preparation_seconds,fit_seconds=fit_seconds,
        test_preparation_seconds=test_preparation_seconds,quotient_layout_bytes=quotient_layout_bytes,
        test_total_instances=len(nodes),test_complete_instances=len(rows),incomplete_capture_marks=len(nodes)-len(rows),
        results=results,token_encoding=encoding,static_equalities=a.static_equalities,quotient=a.quotient,backpropagation=False,threshold=.5,
        limitations=['Only local typed Eq partition is decoded; scalar results and external identities remain unverified',
            'No proposed Eq is applied to a runtime; CPU captured labels are the audit reference',
            'The main whole-Cell model and observed candidate routing remain unchanged',
            'Boundary feature encoding is on CPU, not an integrated GPU-only decoder',
            'No state dictionary or test labels enter decoder fit; validation selects ridge alpha',
            'Timing is one diagnostic and excludes source matching and native graph proof'])
    a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    if not all(v['numerical_audit']['passed'] and not v['numerical_audit']['threshold_disagreements'] for v in results.values()):raise SystemExit(1)

if __name__=='__main__':main()
