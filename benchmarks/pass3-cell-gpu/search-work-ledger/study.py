"""Compare source-aligned candidate work in a single-threaded native execution."""
import argparse
import json
from pathlib import Path
import subprocess
import gzip
from ceiling import reference_ceiling
from tempfile import TemporaryDirectory

FIELDS = ('single_candidates','multi_extensions','multi_index_rows','exact_delivery',
          'exact_pivot','exact_expansion','verification_parent_reads','shortlist_candidates','page_headers_scored','unissued_residual_reads','receiver_domain_checks','exact_index_filter','exact_index_build','direct_owner_probes')
DISCOVERY = ('single_candidates','multi_extensions','exact_delivery','exact_pivot',
             'exact_expansion','shortlist_candidates','unissued_residual_reads','receiver_domain_checks','exact_index_filter')


def read(path):
    return json.loads(path.read_bytes())


def run(binary, bundle, request, allow_failure=False):
    result = subprocess.run([binary,bundle/'program.json',bundle/'plans.json'],
                            input=json.dumps(dict(request,audit=True))+'\n',text=True,
                            capture_output=True,check=True)
    data = json.loads(result.stdout)
    if not allow_failure and 'source_error' in data:
        raise ValueError(data['source_error'])
    return data


def endpoint_births(data):
    visible=set(data['visible_constructor_refs'])
    if len(visible)!=len(data['visible_constructor_refs']):
        raise ValueError('duplicate endpoint constructor')
    births={}
    offset=0
    for schedule, events in zip(data['schedule'],data['events'],strict=True):
        size=schedule[4]
        for e in events:
            if e[0]=='birth' and e[4] in visible and e[5] is not None:
                local,_=e[5]
                if not 0<=local<size or e[4] in births:
                    raise ValueError('ambiguous constructor birth')
                births[e[4]]=offset+local+1
        offset+=size
    return births


def study(binary, bundle, dest, model=None, budgets=(1,2,4,8), controls=True):
    base = run(binary,bundle,dict(baseline=True))
    config = read(bundle/'request.json')
    for name in ('single_config','multi_weights','merge_config','root_config'):
        config[name] = str(bundle/config[name])
    total = sum(row[4] for row in base['schedule'])
    source_births=endpoint_births(base)
    report = {}
    with TemporaryDirectory() as work:
        arms = ['exact','certified']
        if controls:
            arms.extend(['assisted','owner','empty','all-single','relocated','all-both-bounded'])
        if model:
            arms.extend(f'{policy}-{budget}' for budget in budgets
                        for policy in ('fixed','learned','jointfixed','jointlearned'))
        for arm in arms:
            req = config.copy()
            if arm.startswith(('fixed-','learned-','jointfixed-','jointlearned-')):
                policy,budget=arm.split('-')
                weights=read(model)['weights'] if policy.endswith('learned') else [1,1,1,0,0,0]
                if policy.startswith('joint'):
                    root_weights=read(model)['root_weights'] if policy.endswith('learned') else [1,1,1]
                    req['root_page_policy']=dict(weights=root_weights,budget=int(budget))
                req.update(page_policy=dict(weights=weights,budget=int(budget)),multi_residual=True)
                opts=Path(work)/'single.json'
                opts.write_text(json.dumps(dict(read(Path(config['single_config'])),residual=True)))
                req['single_config']=str(opts)
                control=Path(work)/'root.json'
                control.write_text(json.dumps(dict(read(Path(config['root_config'])),forbid_fallback=False)))
                req['root_config']=str(control)
            elif arm in ('assisted','owner'):
                req['owner_ports']=arm=='owner'
                req['multi_residual']=True
                opts=Path(work)/'owner-single.json'
                opts.write_text(json.dumps(dict(read(Path(config['single_config'])),residual=True)))
                req['single_config']=str(opts)
                control=Path(work)/'owner-root.json'
                control.write_text(json.dumps(dict(read(Path(config['root_config'])),forbid_fallback=False)))
                req['root_config']=str(control)
            elif arm not in ('exact','certified'):
                # Missing provider winners must be allowed to allocate from exact bindings.
                control = Path(work)/'root.json'
                control.write_text(json.dumps(dict(read(Path(config['root_config'])),forbid_fallback=False)))
                req['root_config'] = str(control)
                scfg = read(Path(config['single_config']))
                scfg.update(mode='none' if arm=='empty' else 'all',residual=arm in ('empty','all-both-bounded'))
                options = Path(work)/'single.json'
                options.write_text(json.dumps(scfg))
                req['single_config'] = str(options)
                if arm=='relocated':
                    req['relocate_single']=True
                if arm=='empty':
                    req.update(multi_mode='sealnone',multi_residual=True)
                if arm=='all-both-bounded':
                    req.update(multi_mode='sealall',multi_residual=True,multi_generation='bounded',cap=4096)
            if arm=='certified':
                req['capture_pages']=True
            data = base if arm=='exact' else run(binary,bundle,req)
            for key in ('schedule','rhs','writes','resumes','state_sha'):
                if data[key]!=base[key]:
                    raise ValueError(f'{arm}: source mismatch in {key}')
            def unions(trace):
                return [[e for e in events if e[0]=='union'] for events in trace]
            if unions(data['events'])!=unions(base['events']):
                raise ValueError(f'{arm}: source union mismatch')
            single=data['single'] or {}
            multi=data['multi'] or {}
            claimed=[s[0] for s in single.get('committed',[])]+[s['ordinal'] for s in multi.get('tickets',[])]
            if len(set(claimed))!=len(claimed) or any(i<1 or i>total for i in claimed):
                raise ValueError('invalid/duplicate winning ordinal')
            work_counts=dict(zip(FIELDS,data['search_work'],strict=True))
            sites=data['search_sites']
            if [sum(row[2][i] for row in sites) for i in range(len(FIELDS))]!=data['search_work']:
                raise ValueError('site ledger differs from global counts')
            with gzip.open(dest.with_suffix('.'+arm+'.json.gz'),'wt') as out:
                json.dump(dict(fields=FIELDS,sites=sites),out,separators=(',',':'))
            births=endpoint_births(data)
            winners=set(claimed)
            paid_single=single.get('work',[0,0])[1]
            paid_multi=multi.get('counts',{}).get('raw_tuples',0)
            paid_child=(data.get('merge_child') or {}).get('counts',[0,0])[1]
            paid=paid_single+paid_multi+paid_child
            credited=sum(ordinal in winners for ordinal in births.values())
            if births!=source_births:
                raise ValueError(f'{arm}: source retained birth attribution differs')
            result=dict(source_rhs=total,provider_winners=len(claimed),
                        verifier_suffix_points=(single.get('work') or [0]*4)[3]+multi.get('counts',{}).get('point_reads',0),
                        verifier_primitives=(single.get('work') or [0]*5)[4]+multi.get('counts',{}).get('primitive_evals',0),
                        single_winners=len(single.get('committed',[])),multi_winners=len(multi.get('tickets',[])),
                        paid=dict(single=paid_single,multi=paid_multi,child=paid_child),
                        visible=credited,source_visible=len(births),fept=credited/paid if paid else None,work=work_counts,
                        discovery=sum(work_counts[k] for k in DISCOVERY))
            if arm=='relocated':
                result['fept']=None
                result['eligible_explicit_parent_protocol']=False
                if result['discovery']!=report['all-single']['discovery'] or work_counts['receiver_domain_checks']!=report['all-single']['work']['single_candidates']:
                    raise ValueError('moving the address search changed its charge')
            if arm=='certified':
                tickets=multi['tickets']
                plans=read(bundle/'plans.json')
                result['oracle_multi_winners']={str(b):reference_ceiling(tickets,plans,b) for b in budgets}
            if arm=='owner' or arm.startswith(('jointlearned-','learned-')):
                options = Path(work)/'strict-single.json'
                options.write_text(json.dumps(dict(read(Path(req['single_config'])),residual=False)))
                strict=run(binary,bundle,dict(req,multi_residual=False,single_config=str(options)),allow_failure=True)
                prefix=0
                for actual,expected in zip(strict.get('rhs',[]),base['rhs']):
                    if actual!=expected:
                        break
                    prefix+=1
                result['unassisted']=dict(equal_rhs_digest_prefix=prefix,runs=strict['runs'],
                    aligned=all(strict.get(k)==base[k] for k in ('schedule','rhs','writes','resumes','state_sha'))
                    and unions(strict.get('events',[]))==unions(base['events']),
                    source_error=strict.get('source_error'))
            report[arm]=result
            print(arm,result,flush=True)
            dest.write_text(json.dumps(report,indent=2)+'\n')
    if report['certified']['provider_winners']!=total or (controls and report['empty']['provider_winners']):
        raise ValueError('coverage control failed')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('binary','bundle','dest'):
        p.add_argument(arg,type=Path)
    p.add_argument('--model',type=Path)
    p.add_argument('--budgets',nargs='+',type=int,default=[1,2,4,8])
    p.add_argument('--skip-controls',action='store_true')
    a=p.parse_args()
    study(a.binary,a.bundle,a.dest,a.model,a.budgets,not a.skip_controls)
