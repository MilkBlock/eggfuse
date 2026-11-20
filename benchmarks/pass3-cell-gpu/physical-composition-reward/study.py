"""Freeze candidate edges and empirical rewards on training families; price physical switches on unseen programs."""
import argparse
from collections import Counter,defaultdict
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
import subprocess


def save(p,data):p.write_text(json.dumps(data,indent=1)+'\n')
def read(p):return json.loads(p.read_bytes())
def program_path(corpus,name):
    local=corpus/name/'program.json'
    if local.is_file():return local
    return corpus.parent/'pass3-atlas-integration-20261120'/name/'program.json'
def digest(v):return sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def key(e):return tuple(e[k] for k in ('parent','member','operation','child'))
def edge(k):return dict(zip(('parent','member','operation','child'),k))
def go(*cmd):subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)


def inspect(result):
    c=result['integral']['composition'];s=result['integral']['storage'];p=result['physical']
    # Arrays include view headers, fact and result arrays. Owner storage and root directory
    # are additional charges; hash buckets/allocator padding are outside this accounting.
    scope=p['integral_array_bytes']+s['instance_header_capacity_bytes']+s['root_directory_payload_estimate_bytes']+s['exception_payload_capacity_bytes']+c['compiled_added_layout_payload_bytes']
    return dict(runs=result['runs'],source_sha=result['graph'],instances=p['integral_instances'],external_handles=p['integral_view_handles'],
                committed_views=s['issued_views'],retired_views=s['retired_views'],source_frames=p['ordinary_source_frames'],
                standalone_descriptors=p['completed_source_descriptors'],live_facts=p['integral_live_facts'],switches=c['layout_switches'],
                avoided_child_owners=c['child_instances_avoided'],avoided_root_holds=c['root_holds_avoided'],
                exceptions=p['integral_fact_exceptions'],compiled_bytes=c['compiled_added_layout_payload_bytes'],
                array_bytes=p['integral_array_bytes'],directory_estimate=s['root_directory_payload_estimate_bytes'],
                charged_bytes=scope,unused_reserved_members=c['uninstalled_reserved_members'],
                instance_header_capacity=s['instance_header_capacity_bytes'],timing_ms=result['inference_ms'])


class Case:
    def __init__(self,a,name):
        self.a=a;self.name=name;self.program=program_path(a.corpus,name)
        self.path=a.out/name;self.path.mkdir(exist_ok=True)
        self.valid={};self.seq=0
    def candidate(self,k):
        if k not in self.valid:
            f=self.path/'edge.json';save(f,[edge(k)])
            p=subprocess.run([self.a.observer,self.program,'compile',self.path/'check.json',f],
                              stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True)
            if p.returncode and not any(e in p.stderr for e in ('integral library parent unavailable','integral library child unavailable',
                    'integral composition member','integral boundary is not a constructor','integral root table proof mismatch',
                    'integral composition duplicates an existing internal boundary','integral composition member limit')):
                raise RuntimeError((self.name,k,p.stderr))
            self.valid[k]=p.returncode==0
        return self.valid[k]
    def catalog(self,name,keys):
        selected=[k for k in keys if self.candidate(k)]
        f=self.path/(name+'.edges');p=self.path/(name+'.json')
        save(f,[edge(k) for k in selected]);go(self.a.observer,self.program,'compile',p,f)
        return p
    def execute(self,arm,mask=None,task='calibrate'):
        self.seq+=1;dest=self.path/f'run-{self.seq}'
        go(self.a.driver,self.program,dest,task,arm,'3',mask or 'all')
        return read(dest/'result.json')
    def stable(self,arms):
        mask=None;rest={}
        for _ in range(10):
            actual={}
            for name,cat in arms.items():
                val=self.execute(cat,mask);rest[name]=val
                actual[name]={tuple(a) for a in val['admissions']}
            common=set.intersection(*actual.values())
            if all(c==common for c in actual.values()):
                f=self.path/'matched-admissions.json';save(f,sorted(a[1] for a in common))
                assert all(rest[n]['graph']==rest['empty']['graph'] for n in arms)
                return f,rest
            path=self.path/'intersection.json'
            ids=sorted(a[1] for a in common)
            if mask and read(mask)==ids:raise ValueError('admission identities changed without shrinking mask')
            save(path,ids);mask=path
        raise ValueError('storage admissions did not stabilize')


def main(a):
    a.out.mkdir(parents=True,exist_ok=False)
    corpus=read(a.corpus/'collection.json')
    train=[k for k,v in corpus.items() if v['split']=='train']
    assert train and all(corpus[n]['split']!='train' for n in a.evaluate)
    if a.reuse_frozen:
        prior=read(a.reuse_frozen)
        assert prior['train']==train and prior['candidate_budget']==a.budget and len(prior['pool'])==a.pool
        evaluate(a,corpus,prior)
        return
    support=defaultdict(Counter)
    for n in train:
        f=a.out/f'{n}.train.json';go(a.observer,program_path(a.corpus,n),'train',f)
        for candidate in read(f)['training']:
            k=key(candidate['edge'])
            if candidate['published'] and k[0]<0x80000000 and candidate['parent_members']+candidate['child_members']<=64:
                support[k][n]+=candidate['published']
    pool=sorted((k for k,v in support.items() if len(v)>=2),key=lambda k:(-sum(support[k].values()),k))[:a.pool]
    assert len(pool)>=a.budget
    benefit=defaultdict(Counter);training={}
    for n in train:
        case=Case(a,n)
        arms={'empty':case.catalog('empty',[])}
        for i,k in enumerate(pool):arms[str(i)]=case.catalog(f'candidate-{i}',[k])
        _,out=case.stable(arms)
        reference=inspect(out['empty'])
        metrics={}
        for i,k in enumerate(pool):
            arm=inspect(out[str(i)]);metrics[i]=arm
            benefit[k]['owners']+=reference['instances']-arm['instances']
            benefit[k]['retirements']+=arm['retired_views']-reference['retired_views']
            benefit[k]['bytes']+=reference['charged_bytes']-arm['charged_bytes']
        training[n]=dict(controls=reference,candidate=metrics,admissions=len(out['empty']['admissions']))
        print('calibrated',n,len(pool),flush=True)
    frozen=dict(train=train,eval=a.evaluate,candidate_budget=a.budget,pool=[dict(edge=edge(k),train_support=support[k],benefit=dict(benefit[k])) for k in pool],training=training)
    evaluate(a,corpus,frozen)


def evaluate(a,corpus,frozen):
    pool=[key(v['edge']) for v in frozen['pool']]
    benefit={k:v['benefit'] for k,v in zip(pool,frozen['pool'])}
    support={k:sum(v['train_support'].values()) for k,v in zip(pool,frozen['pool'])}
    def rank(field):
        return sorted(pool,key=lambda k:(-benefit[k][field],-support[k],k))
    policies={'empty':[],'published':pool[:a.budget],
              'owner_reward':rank('owners')[:a.budget],'retirement_reward':rank('retirements')[:a.budget],
              'net_bytes':[k for k in rank('bytes') if benefit[k]['bytes']>0][:a.budget]}
    frozen.update(eval=a.evaluate,policies={name:[pool.index(k) for k in v] for name,v in policies.items()})
    save(a.out/'frozen.json',frozen)
    reports={}
    for n in a.evaluate:
        case=Case(a,n);arms={k:case.catalog(k,v) for k,v in policies.items()}
        # First measure the deployment-like, unmasked exact scheduler with the frozen policies.
        natural={name:inspect(case.execute(cat)) for name,cat in arms.items()}
        assert all((v['source_sha'],v['runs'])==(natural['empty']['source_sha'],natural['empty']['runs']) for v in natural.values())
        mask,st=case.stable(arms)
        baseline=None;scope={}
        for name,cat in arms.items():
            audit=case.execute(cat,mask,'audit')
            trace=digest(audit['stage_checks'])
            if baseline is None:baseline=trace
            assert trace==baseline
            summary=inspect(audit)
            summary.update(runs=audit['runs'],mask_size=len(audit['admissions']),source_sha=audit['graph'],
                           run_ledger_sha=trace,accessible_old_fact_refs=max(row[2] for row in audit['view_checks']),
                           last_view_check=audit['view_checks'][-1],compiled_edges=len(read(cat)['edges']),times=[])
            assert summary['avoided_child_owners']==summary['switches']
            scope[name]=summary
        ids=list(arms)
        for trial in range(a.repeats+1):
            i=trial%len(ids);order=ids[i:]+ids[:i]
            for name in reversed(order) if trial%2 else order:
                result=case.execute(arms[name],mask,'timing')
                assert result['graph']==scope[name]['source_sha'] and result['physical']==st[name]['physical']
                if trial:scope[name]['times'].append(result['inference_ms'])
        for v in scope.values():v['median_ms']=median(v['times'])
        reports[n]=dict(split=corpus[n]['split'],unmasked=natural,paired=scope,oracle_neural_rhs=0,
                        usable_neural_issue_id=False)
        save(a.out/'results.json',reports)
        print(n,[(k,x['instances'],x['retired_views'],x['compiled_bytes'],round(x['median_ms'],1)) for k,x in scope.items()],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('observer','driver','corpus','out'):p.add_argument(k,type=Path)
    p.add_argument('--reuse-frozen',type=Path)
    p.add_argument('--evaluate',nargs='+',default=['dot-product','stable-argmax'])
    p.add_argument('--pool',type=int,default=12);p.add_argument('--budget',type=int,default=4)
    p.add_argument('--repeats',type=int,default=4);main(p.parse_args())
