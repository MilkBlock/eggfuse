"""Measure complete native passes against vanilla with the same allocator and frozen inputs."""
import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import json
from pathlib import Path
from statistics import median
import subprocess


def read(path):
    return json.loads(path.read_bytes())


def digest(value):
    return hashlib.sha256(json.dumps(value,separators=(',',':'),sort_keys=True).encode()).hexdigest()


@contextmanager
def session(*args):
    proc = subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    def run(request):
        proc.stdin.write(json.dumps(request).encode()+b'\n')
        proc.stdin.flush()
        line=proc.stdout.readline()
        if not line:
            raise RuntimeError(f'{args[0]} exited with status {proc.poll()}')
        return json.loads(line)
    try:
        yield run
    finally:
        proc.stdin.close()
        if proc.wait():raise RuntimeError(f'failed process {args[0]}')


def compare(out,gold):
    if 'source_error' in out:return dict(aligned=False,error=out['source_error'],completed=out['runs'])
    checks={k:out[k]==gold[k] for k in ('rhs','writes','resumes','state_sha','schedule','runs')}
    checks['unions']=[[e for e in group if e[0]=='union'] for group in out['events']]==gold['unions']
    multi,single,root,merge=(out[k] for k in ('multi','single','root_recipe','merge_child'))
    ids=set(); rhs=set()
    for event in single['committed']:
        ordinal=event[0]
        assert ordinal not in rhs and ordinal>0
        rhs.add(ordinal)
    for event in multi['tickets']:
        ordinal=event['ordinal']
        assert ordinal not in rhs and ordinal>0
        rhs.add(ordinal)
    fresh={row[1]:row for row in out['cell_ids'] if not row[4]}
    for cell,ordinal,rule,template,*_ in root['fresh']:
        assert cell not in ids and fresh[cell][0]==ordinal and ordinal in rhs and fresh[cell][2]==template
        ids.add(cell)
    for token in merge['issued']:
        cell=token['allocated']
        if cell is not None:
            ordinal=token['parent']['ordinal']
            assert cell not in ids and ordinal in rhs and fresh[cell][0]==ordinal and fresh[cell][2]==token['template']
            ids.add(cell)
    return dict(aligned=all(checks.values()),checks=checks,rhs=multi['total_rhs'],neural_rhs=len(rhs),
                fresh=len(fresh),direct_cells=len(ids),source_pass_rhs=gold['rhs_count'],state_sha=out['state_sha'],
                wire_bytes=root['wire_bytes'],root_row_decodes=root.get('root_row_decodes'),
                root_header_checks=root.get('root_header_checks'),owned_slot_transfers=root.get('owned_slot_transfers'),raw=root['raw_hash'],emitted=root['emitted'],wire_hash=root['wire_hash'],
                commits=digest(root['commits']),physical=digest(root['fresh']),multi=multi['raw_sha256'],
                children=digest(merge['issued']),cells=digest(out['cell_ids']),rejected=root['rejected'],
                root_allocated=root['allocated'],applied=root['applied'])


def trial(bundle,case,seed,a):
    request=read(bundle/'request.json')
    for field in ('single_config','multi_weights','merge_config','root_config'):
        request[field]=str(bundle/request[field])
    program=bundle/'program.json'
    if hashlib.sha256(program.read_bytes()).hexdigest()!=request['source_sha256']:raise ValueError('wrong source')
    with session(a.vanilla/'vanilla-audit',program) as run:gold=run(dict(audit=True))
    root_config=read(bundle/'root.json');requests={};report={}
    with ExitStack() as stack:
        infer=stack.enter_context(session(a.native,program,bundle/'plans.json'))
        vanilla=stack.enter_context(session(a.vanilla/'vanilla',program))
        for name in a.formats:
            path=a.out/f'{case}-{seed}-{name}.json'
            path.write_text(json.dumps(dict(root_config,encoding=name)))
            req=dict(request,root_config=str(path))
            result=compare(infer(dict(req,audit=True)),gold)
            report[name]=result
            if not result['aligned']:
                print(case,seed,name,'diverged',result.get('error',result.get('checks')),flush=True)
                continue
            assert result['rhs']==gold['rhs_count'] and result['neural_rhs']*100>=98*result['rhs']
            assert result['direct_cells']*100>=98*result['fresh']
            if name!='full' and 'full' in report and report['full']['aligned']:
                for k in ('raw','commits','physical','multi','children','cells','emitted','rhs','neural_rhs'):
                    assert result[k]==report['full'][k],(case,name,k)
            requests[name]=req
        if a.negative:
            for enc in requests:
                for control in ('wrong-template','wrong-port'):
                    path=a.out/f'{case}-{seed}-{enc}-{control}.json'
                    path.write_text(json.dumps(dict(root_config,encoding=enc,control=control,forbid_fallback=False)))
                    observed=infer(dict(request,audit=True,root_config=str(path)))
                    result=compare(observed,gold)
                    assert result['aligned'] and result['applied']==result['root_allocated']==0 and result['rejected']>0
                    report[enc][control]=dict(rejected=result['rejected'],applied=0,aligned=True)
        modes=['vanilla',*requests];report['vanilla']=dict(rhs=gold['rhs_count'],runs=gold['runs'],state_sha=gold['state_sha'])
        if a.audit_only:return report
        for k in modes:report[k]['ms']=[]
        for warm in range(1+2*len(modes)):
            start=warm%len(modes);order=modes[start:]+modes[:start]
            for k in order if warm%2==1 else reversed(order):
                got=vanilla({}) if k=='vanilla' else infer(dict(requests[k],audit=False))
                assert got['state_sha']==gold['state_sha'] and got['runs']==gold['runs']
                if k!='vanilla':
                    assert got['root_recipe']['allocated']==report[k]['root_allocated']
                    assert got['multi']['total_rhs']==gold['rhs_count']
                if warm:report[k]['ms'].append(got['ms'])
        for k in modes:
            report[k]['median_ms']=median(report[k]['ms'])
            report[k]['speedup']=median(report['vanilla']['ms'])/report[k]['median_ms']
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('native','vanilla','holdout','out'):p.add_argument(k,type=Path)
    p.add_argument('--cases',nargs='+',default=['sum-bits','dot-product','jacobi-1d','conjugate-gradient'])
    p.add_argument('--seeds',type=int,nargs='+',default=[1703,1709])
    p.add_argument('--formats',nargs='+',default=['full','shared_wire','resident'])
    p.add_argument('--negative',action='store_true')
    p.add_argument('--audit-only',action='store_true')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False);results={}
    for case in a.cases:
        for seed in a.seeds:
            bundle=a.holdout/f'{case}-{seed}'
            data=trial(bundle,case,seed,a);results[f'{case}/{seed}']=data
            (a.out/'results.json').write_text(json.dumps(results,indent=1)+'\n')
            print(case,seed,[(k,round(v.get('median_ms',0),2)) for k,v in data.items()],flush=True)
