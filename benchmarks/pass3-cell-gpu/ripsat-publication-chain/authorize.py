"""Authorize one additional typed constructor-Set publication path from one real history and donor occurrence."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path

HERE=Path(__file__).resolve().parent
base=run_path(str(HERE.parent/'ripsat-strict-programs/compile.py'))
sp=base['sp'];native=base['native'];Recipe=base['Recipe'];require=sp['require'];Refusal=sp['Refusal']
V2=HERE.parent/'ripsat-donor-evidence';ACCEPT=HERE.parent/'ripsat-strict-acceptance'
read=lambda f:json.loads(Path(f).read_bytes())
digest=lambda b:sha256(b).hexdigest()


def set_contract(recipe,mid,op,terminal,pivot):
    """Compile a distinct fresh-publication operation. No generic Set or merge is a returning Let."""
    middle=recipe.rule(mid);last=recipe.rule(terminal)
    require(middle['metadata']['seminaive'] and last['metadata']['seminaive'],'non_seminaive_set_publication')
    require(len(middle['query'])==len(last['query'])==1 and pivot==0,'set_publication_requires_one_complete_parent')
    mquery=middle['query'][0];q=last['query'][0]
    mid_slots=middle['slots'];out_slots=last['slots'];known={}
    for j,v in enumerate(mquery['args']):
        require(set(v)=={'slot'} and sp['integer'](v['slot']) and v['slot'] not in known,'middle_requires_unprovided_binding')
        known[v['slot']]=['column',j]
    before=middle['effects'][:op]
    require(op==1 and len(before)==1,'unsupported_middle_set_prefix')
    initial=before[0]
    require(initial['op']=='let' and initial['kind']=='construct' and initial['call']==mquery['call'] and initial['args']==mquery['args'][:-1],
            'preceding_let_not_proven_same_named_constructor')
    dst=initial['dst'];last_input=mquery['args'][-1]['slot'];require(dst not in known,'duplicate_preceding_definition')
    known[dst]=known[last_input]
    alias={'rule':mid,'operation':0,'dst':dst,'value':{'slot':last_input}}
    metadata=read(recipe.path)
    require(alias in metadata['known_results']['static_aliases'],'missing_source_alias_proof')
    effect=sp['checked_i'](op,middle['effects'],'missing_middle_operation')
    require(effect.get('op')=='set' and effect.get('kind')=='set' and 'dst' not in effect,'middle_not_a_constructor_set')
    table=effect.get('call',{}).get('table');decl=recipe.tables.get(table,{})
    require(decl.get('kind')=='constructor' and decl.get('merge') is None and q['call']=={'table':table},
            'set_target_not_checked_constructor')
    require(op in recipe.templates[mid]['fact_operations'],'set_does_not_own_source_fact_operation')
    cols=[*effect['args'],effect['value']];schema=decl['schema']
    require(len(cols)==len(schema)==len(q['args']),'set_column_arity')
    expressions=[];slots=[]
    for x,row_input,ty in zip(cols,q['args'],schema):
        if 'slot' in x:
            require(x['slot'] in known,'set_needs_independent_input')
            expressions.append(known[x['slot']])
        else:
            require(set(x)=={'literal','sort'},'unsupported_set_operand')
            expressions.append(['literal',x['literal'],x['sort']['name']])
        require(recipe.actual_sort(x,mid_slots)==sp['sort_key'](ty),'set_operand_sort_mismatch')
        require(set(row_input)=={'slot'} and row_input['slot'] not in slots and
            recipe.actual_sort(row_input,out_slots)==sp['sort_key'](ty),'terminal_independent_or_wrong_sort')
        slots.append(row_input['slot'])
    needed={i for i,v in enumerate(out_slots) if v['definition']=='query'}
    require(needed==set(slots),'terminal_needs_additional_input')
    return dict(table=table,pivot=pivot,sorts=[t['name'] for t in schema],columns=expressions,terminal_slots=slots,
                middle_return_alias=alias,portable_middle=recipe.identities[mid],portable_terminal=recipe.identities[terminal])


def arguments_from(contract,incoming,literal):
    return [incoming[c[1]] if c[0]=='column' else literal(c[1],c[2]) for c in contract['columns']]


def signature(ref):
    f=ref['row'].get('Fact');require(f is not None,'unprovided_physical_parent')
    return (f['cell']<<32)|f['op'],ref['version']


def check_source_occurrence(sample,companion,certificate,recipe,proof):
    """Join the same actual occurrence, not two separately sampled edges with matching schemas."""
    p=sample['producer'];m=sample['consumer'];second=companion['companions'][0];t=second['consumer']
    require(companion['first_origin_sample']==sample and second['producer']==m,'middle_occurrence_mismatch')
    require(len(companion['companions'])==1 and companion['later_143_internal_serials']==[] and companion['later_143_paid_serials']==[t['serial']],
            'terminal_not_a_real_separate_external_proposal')
    require(p['serial']!=m['serial']!=t['serial'] and len({d['serial'] for d in (p,m,t)})==3 and
            p['epoch']<m['epoch']<t['epoch'] and p['ordinal']<m['ordinal']<t['ordinal'],'invalid_original_order')
    require(t['fingerprint']==sp['capture_fingerprint'](recipe.rule(t['rule'])) and t['source_name']==recipe.rule(t['rule'])['metadata']['name']
            and t['ruleset']==recipe.rule(t['rule'])['metadata']['source_set'],'foreign_terminal_schema')
    require(second['relative_runs']==t['epoch']-m['epoch'] and second['consumer_atom']==0,'wrong_terminal_release')
    original=companion['original_committed_roots']
    for event in (p,m,t):
        row=original[str(event['serial'])];rs=recipe.rule(event['rule'])
        require(row['root_ordinal']==event['ordinal'] and row['epoch']==event['epoch'] and row['rule']==event['rule'] and
                row['template']==event['rule'],'foreign_ordinary_root')
        sp['verify_producer_inputs'](rs,event['rows'])
        require(row['refs']==[z['named'] for z in event['rows']],'ordinary_named_parent_mismatch')
        for atom in event['rows']:
            for col,val in zip(rs['query'][atom['atom']]['args'],atom['values']):
                if 'slot'in col:require(row['slot_values'][str(col['slot'])]==val,'ordinary_bound_slot_mismatch')
    fst=sample['original_fact'];fact=second['original_fact'];v=second['original_version']
    require(companion['middle_signed_trail']==[m['serial'],p['serial'],[[p['rule'],sample['producer_op'],m['rule']]],
            [[fst>>32,fst&0xffffffff,p['epoch'],p['epoch']]],m['epoch']],'wrong_signed_first_step')
    require(signature(m['rows'][0]['named'])==(fst,p['epoch']),'wrong_named_middle_input')
    require(fact!=fst and fact&0xffffffff==second['producer_op'] and v==m['epoch'] and fact==companion['middle_set_fact']
            and v==companion['set_version'],'wrong_fresh_set_coordinates')
    birth=second['birth_event']
    require(birth==companion['middle_set_birth_event'] and len(birth)==6 and birth[0]=='birth' and birth[4]==fact and
            birth[5][1]==m['rule'] and list(recipe.tables)[birth[1]]==proof['table'],'foreign_fresh_set_birth')
    terminal=t['rows'][0]
    require(terminal['atom']==proof['pivot'] and terminal['table']==proof['table'] and signature(terminal['named'])==(fact,v),
            'terminal_did_not_read_fresh_set_fact')
    expect=arguments_from(proof,m['rows'][0]['values'],lambda v,s:{'Int':v} if s=='i64' else None)
    require(None not in expect and [*birth[2],birth[3]]==expect==terminal['values'],'set_keys_or_value_not_causal')
    return dict(serials=[e['serial'] for e in (p,m,t)],ordinals=[e['ordinal'] for e in (p,m,t)],
                runs=[e['epoch'] for e in (p,m,t)],named_root_inputs=[r['named'] for r in p['rows']],
                first_port=[fst,p['epoch']],second_port=[fact,v],set_columns=expect,
                first_root=certificate['original'],source_state_sha256=companion['reference']['state_sha'])


def check_history(data,first,static):
    h=data['native/history.json'];g=native['Graph'](data['native/saturated-rule-composition.json'])
    entry=data['entry.egg'];rows=h['records']
    first_edge=first['native']['native_consumer_reads']
    require(len(first_edge)==1,'ambiguous_first_native_edge')
    first_edge=first_edge[0];fi=first_edge['producer_index'];mi=first_edge['consumer_index']
    m=rows[mi]
    require(fi in m['parents'] and first_edge['write_read_token'] in m['required'],'broken_first_native_write_read')
    incoming=first['native']['local_args']+[first['native']['local_result']]
    expect=arguments_from(static,incoming,lambda lit,sort:g.literal(json.dumps(lit),sort))
    require(g.rows.get((static['table'],tuple(expect[:-1])))==expect[-1],'missing_set_publication_from_final_graph')
    seed=[(first['native']['table'],tuple(incoming[:-1]),incoming[-1])]
    published=native['valid_history_record'](h,m,entry,g,static['table'],expect,seed)
    require(len(published['output_sites'])==1,'ambiguous_set_publication_write')
    w=published['output_sites'][0];fresh=w['token']
    require(fresh in m['produced'] and fresh!=first_edge['write_read_token'] and published['record']==first_edge['consumer_record'],
            'not_a_distinct_native_set_write')
    hits=[]
    for ti,r in enumerate(rows):
        if not(ti>mi and mi in r['parents'] and fresh in r['required'] and r['rule']==rows[fi]['rule']):continue
        obs=native['valid_history_record'](h,r,entry,g,static['table'],None,[(static['table'],tuple(expect[:-1]),expect[-1])])
        for site in obs['read_sites']:
            if site['token']!=fresh or list(site['coordinates'])!=expect or site['operator']!=static['table']:
                continue
            port=sp['checked_i'](site['position'],r['ports'],'missing_terminal_parent_port').get('Parent')
            require(isinstance(port,list) and len(port)==2,'terminal_did_not_use_parent_output')
            require(sp['checked_i'](port[0],r['parents'],'unknown_terminal_parent')==mi and
                    sp['checked_i'](port[1],m['values'],'unknown_middle_output_port')==fresh and
                    m['outputs'][port[1]]=={'Row':w['span']},'wrong_same_record_terminal_port')
            hits.append(dict(index=ti,record=r['id'],read=site,parent_port=port))
    require(len(hits)==1,'missing_or_ambiguous_same_history_terminal')
    last=hits[0]
    return dict(local_record_ids=[rows[fi]['id'],m['id'],last['record']],local_indices=[fi,mi,last['index']],
        tokens=[first_edge['write_read_token'],fresh],first_edge=first_edge,second_output=w,terminal_read=last['read'],terminal_parent_port=last['parent_port'],
        first_classes=incoming,second_classes=expect)


def load_checked(certificate,evidence,donors,target,**kwargs):
    cached=read(certificate)
    require(cached==authorize(evidence,donors,target,**kwargs),'cached_publication_certificate_differs_from_proof')
    return cached


def authorize(evidence,donors,target,*,companion_dir=ACCEPT,source_dir=base['SOURCE_DIR']):
    """Authorize only on independently pinned donor evidence. Target access is confined to its static program."""
    ev_path=Path(evidence).resolve();ev=read(ev_path);target_recipe=Recipe(target)
    pins=read(V2/'trust.json');companion_pins=read(ACCEPT/'companion-pins.json')
    require(digest(ev_path.read_bytes())==pins['manifest_sha256'] and set(donors)==set(companion_pins),'untrusted_manifest_or_donor_set')
    blobs=read(ev_path.parent/'native-text.json') if (ev_path.parent/'native-text.json').exists() and not (ev_path.parent/'samples').exists() else None
    supports=[];excluded=[]
    for donor,source in sorted(donors.items()):
        recipe=Recipe(source);cp=companion_pins[donor];raw=(Path(companion_dir)/cp['file']).read_bytes()
        require(digest(raw)==cp['sha256'],'foreign_independent_source_receipt');comp=json.loads(raw);d=ev['donors'][donor]
        require(comp['donor']==donor and comp['source_sample_id']==cp['source_sample'] and comp['program_sha256']==d['program_sha256']==recipe.file_sha
                and comp['recipe_sha256']==d['recipe_sha256'] and comp['trust_index_sha256']==digest((V2/'trust.json').read_bytes()),'foreign_donor')
        sample=next(s for s in d['samples'] if s['sample_id']==cp['source_sample'])
        pin=pins['samples'][sample['sample_id']]
        data,identities=base['authenticated'](ev_path.parent,sample,pin,blobs)
        require(comp['source_origin_sha256']==identities['origin.json'] and comp['native_acceptance_sha256']==identities['native/acceptance.json'] and
                comp['native_history_sha256']==identities['native/history.json'],'foreign_native_history_or_donor_origin')
        require(all(comp['reference'][k]==d['reference'][k] for k in ('runs','rhs','state_sha')),
                'independent_source_reference_disagrees')
        if not comp['companions']:
            require(not cp['later_143'] and not comp['later_143_paid_serials'],'missing_pinned_terminal')
            excluded.append(dict(donor=donor,reason='no_observed_paid_terminal_consuming_this_middle',middle=cp['middle']));continue
        first=base['evidence_card'](ev_path.parent,sample,donor,recipe,d['source_parts'],source_dir,pin,blobs)
        orig=data['origin.json']['sample'];p,m,t=orig['producer']['rule'],orig['consumer']['rule'],comp['companions'][0]['consumer']['rule']
        require(t==p and cp['middle']==orig['consumer']['serial'] and cp['fact']==comp['middle_set_fact'] and cp['version']==comp['set_version'],'foreign_middle')
        op=comp['companions'][0]['producer_op'];static=set_contract(recipe,m,op,t,0)
        try:recipe.certify(m,op,t,0)
        except Refusal as exc:require(str(exc)=='not_a_returning_constructor','unexpected_legacy_refusal')
        else:raise Refusal('set_conflated_with_let')
        source_receipt=check_source_occurrence(orig,comp,first,recipe,static)
        history=check_history(data,first,static)
        path=[[p,orig['producer_op'],m],[m,op,t]]
        portable=[[recipe.identities[a],o,recipe.identities[b]] for a,o,b in path]
        local=[[target_recipe.resolve(a),o,target_recipe.resolve(b)] for a,o,b in portable]
        try:target_recipe.certify(*local[1],0)
        except Refusal as exc:require(str(exc)=='not_a_returning_constructor','unexpected_target_let_refusal')
        else:raise Refusal('target_set_conflated_with_let')
        first_static=target_recipe.certify(local[0][0],local[0][1],local[0][2],0)
        target_static=set_contract(target_recipe,*local[1],0)
        require(first_static['table']==first['static']['table'] and target_static['columns']==static['columns']
                and target_static['sorts']==static['sorts'] and target_static['terminal_slots']==static['terminal_slots'],'foreign_target_wiring')
        supports.append(dict(donor=donor,sample_id=sample['sample_id'],companion_sha256=cp['sha256'],
            native_history_sha256=identities['native/history.json'],origin_sha256=identities['origin.json'],source=source_receipt,
            native=history,portable_path=portable,path=local,target_static=target_static))
    require(len(supports)==1,'bounded_supplement_requires_one_same_middle_witness')
    s=supports[0];path=s['path'];static=s['target_static']
    spec=dict(depth=2,partial=True,library=[path[:1]],set_publication=dict(schema='eggfuse-set-publication-program/v1',
              target_sha256=target_recipe.file_sha,path=path,kinds=['fresh_constructor_let','fresh_constructor_set'],table=static['table'],pivot=0))
    return dict(schema='eggfuse-ripsat-publication-chain/v1',target_sha256=target_recipe.file_sha,
        strict_named=spec,program_sha256=sp['sha'](spec),support=supports,excluded=excluded,
        pins=dict(evidence_manifest=digest(ev_path.read_bytes()),native_trust=digest((V2/'trust.json').read_bytes()),
            source_companions=digest((ACCEPT/'companion-pins.json').read_bytes())))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence',type=Path,default=V2/'evidence.json')
    p.add_argument('--donor',action='append',required=True);p.add_argument('--target',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--companion-dir',type=Path,default=ACCEPT);a=p.parse_args();donors=dict(pair.split('=',1) for pair in a.donor)
    result=authorize(a.evidence,donors,a.target,companion_dir=a.companion_dir);a.output.parent.mkdir(parents=True,exist_ok=True)
    run_path(str(HERE.parent/'explicit-parent-cell-composition/ripsat_bridge.py'))['write_artifact'](a.output,result)
