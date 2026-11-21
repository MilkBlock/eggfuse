"""Lower only verified native RipSat donor return/read evidence to explicit-parent Cell programs."""
from argparse import ArgumentParser
from collections import Counter,defaultdict
import hashlib,json
from pathlib import Path
from runpy import run_path

HERE=Path(__file__).resolve().parent
native=run_path(str(HERE/'native_proof.py'))
sp=native['s'];Recipe=sp['Recipe'];require=sp['require'];Refusal=sp['Refusal']
SOURCE_DIR=HERE.parents[2]/'workloads/pass3/inputs'
TRUST=HERE.parent/'ripsat-donor-evidence/trust.json'
NEEDED=('origin.json','entry.egg','native/entry.egg','native/acceptance.json','native/ripen.json',
        'native/history.json','native/initial-state.json','native/saturated-rule-composition.json')
def digest(data):return hashlib.sha256(data).hexdigest()

def bind_source_forms(profile,parts,source_dir,orig):
    # Verify original source bytes independently of the editable native JSON.
    forms=run_path(str(HERE.parent/'ripsat-donor-evidence/region.py'))['forms']
    files=[]
    for name,identity in parts.items():
        require(Path(name).name==name,'unsafe_source_part')
        p=source_dir/name;require(p.is_file() and digest(p.read_bytes())==identity,'foreign_original_source_blob')
        files.append(p)
    expected={tuple([f['path'],f['line'],f['sha256']]):native['rule_ast'](native['one'](f['code']))
              for f in forms(files) if f['code'].lstrip().startswith('(rule ')}
    declared=[]
    for r in profile['source_rules']:
        k=(r['path'],r['line'],r['sha256']);require(k in expected,'foreign_original_source_rule');declared.append(expected[k])
    for kind in ('producer','consumer'):
        require(any(native['equivalent'](native['one'](orig[kind]['source_name']),body) for body in declared),'original_source_does_not_define_rule')

def read_artifacts(root,sample,blobs=None):
    data={};identities={}
    for name in NEEDED:
        pointer=sample['artifacts'].get(name)
        require(isinstance(pointer,dict),'missing_native_artifact')
        rel=Path(pointer['path'])
        require(not rel.is_absolute() and '..' not in rel.parts and rel.as_posix().endswith('/'+name),'unsafe_native_artifact_path')
        path=(root/rel).resolve();require(root==path or root in path.parents,'unsafe_native_artifact_path')
        if path.is_file():raw=path.read_bytes()
        else:
            require(blobs is not None and pointer['sha256'] in blobs,'missing_native_artifact')
            raw=blobs[pointer['sha256']].encode()
        require(digest(raw)==pointer.get('sha256'),'artifact_digest_mismatch')
        identities[name]=digest(raw)
        data[name]=json.loads(raw) if name.endswith('.json') else raw.decode()
    require(data['entry.egg']==data['native/entry.egg'],'native_source_copy_mismatch')
    return data,identities

def authenticated(directory,sample,pins,blobs):
    data,identities=read_artifacts(directory,sample,blobs)
    require(identities['origin.json']==pins.get('origin_sha256'),'untrusted_donor_origin')
    require(identities['native/acceptance.json']==pins.get('acceptance_sha256'),'untrusted_native_acceptance')
    acceptance=data['native/acceptance.json']
    raw_hashes=acceptance.get('artifact_sha256',{})
    for key in ('entry.egg','history.json','initial-state.json','ripen.json','saturated-rule-composition.json'):
        require(raw_hashes.get(key)==identities['native/'+key],'native_receipt_artifact_mismatch')
    require(digest(json.dumps(sample,sort_keys=True,separators=(',',':')).encode())==pins.get('sample_sha256'),'untrusted_sample_descriptor')
    return data,identities

def evidence_card(directory,sample,donor,source,parts,source_dir,pins,blobs):
    require(sample.get('scope_mode')=='full','non_full_pair_scope')
    require(sample.get('native_accepted') is True,'native_export_not_accepted')
    data,identities=authenticated(directory,sample,pins,blobs)
    bundle=data['origin.json'];o=bundle['sample'];profile=bundle['profile']
    for field,val in dict(producer_rule=o['producer']['rule'],consumer_rule=o['consumer']['rule'],producer_fingerprint=o['producer']['fingerprint'],consumer_fingerprint=o['consumer']['fingerprint'],
                          producer_op=o['producer_op'],consumer_atom=o['consumer_atom'],producer_serial=o['producer']['serial'],consumer_serial=o['consumer']['serial'],original_fact=o['original_fact'],original_version=o['original_version'],relative_runs=o['relative_runs']).items():
        require(sample.get(field)==val,'candidate_origin_mismatch_'+field)
    require(sample.get('wires')==[[o['consumer_atom'],'op',o['producer_op']]],'foreign_ordered_wiring')
    static,root=sp['verify_origin'](source,o)
    bind_source_forms(profile,parts,source_dir,o)
    led=native['check_native'](source,o,profile,data['entry.egg'],data['native/ripen.json'],data['native/initial-state.json'],
          data['native/saturated-rule-composition.json'],data['native/history.json'],data['native/acceptance.json'],static)
    # The manifest's derived index is untrusted. Recompute both endpoints
    # and require its published claims to be consistent with the raw records.
    b=sample.get('port_binding',{})
    require(b.get('certified_producer_new_port') is True and b.get('operator')==static['table'] and b.get('argument_classes')==led['local_args']
            and b.get('result_class')==led['local_result'],'foreign_manifest_port_binding')
    index=b.get('final_row');raw_graph=data['native/saturated-rule-composition.json']
    require(sp['checked_i'](index,raw_graph['rows'],'bad_manifest_row')==dict(op=static['table'],args=led['local_args'],result=led['local_result']),'foreign_manifest_row')
    require(bool(b.get('eligible_full_edge'))==bool(led['native_consumer_reads']),'manifest_local_read_disagrees')
    require(digest(json.dumps(sample,sort_keys=True,separators=(',',':')).encode())==pins.get('sample_sha256'),'untrusted_sample_descriptor')
    return dict(sample_id=sample['sample_id'],donor=donor,donor_program_sha256=source.file_sha,artifacts=identities,
        original=dict(result_fact=o['original_fact'],version=o['original_version'],producer_named=[x['named'] for x in o['producer']['rows'] if x.get('named')],producer_serial=o['producer']['serial'],consumer_serial=o['consumer']['serial'],
                      producer_ordinal=o['producer']['ordinal'],consumer_ordinal=o['consumer']['ordinal'],producer_run=o['producer']['epoch'],consumer_run=o['consumer']['epoch']),
        static=static,producer_input_proof=root,native=led)

def local_extra(directory,sample,mapped,name,source,parts,source_dir,pins,blobs):
    # A non-nominated local read is evaluated against its actual producer in
    # this run; independently corroborated source events retain their identity.
    require(sample['scope_mode'] in ('augmented','full') and sample['native_accepted'] is True,'non_full_pair_scope')
    data,ids=authenticated(directory,sample,pins,blobs)
    o=data['origin.json']['sample'];profile=data['origin.json']['profile'];loc=mapped['local'];w=mapped.get('donor_receipt')
    require(isinstance(w,dict),'missing_original_donor_edge')
    pi,ci,op,pivot=loc['producer_rule'],loc['consumer_rule'],mapped['producer_op'],mapped['consumer_atom']
    require(pi==o['producer']['rule'] and ci in profile.get('selected_rules',[]) and pi in profile.get('selected_rules',[]),'foreign_augmented_rule')
    require(mapped['compatible_producer_ops']==[op] and mapped['compatible_consumer_atoms']==[pivot],'ambiguous_augmented_mapping')
    proof=source.certify(pi,op,ci,pivot)
    pr=source.rule(pi);cr=source.rule(ci)
    require(o['producer']['fingerprint']==sp['capture_fingerprint'](pr) and o['producer']['source_name']==pr['metadata']['name'],'foreign_augmented_origin')
    root=sp['verify_producer_inputs'](pr,o['producer']['rows'])
    require(all(w[field]==value for field,value in [('producer_rule',pi),('producer_op',op),('consumer_rule',ci),('consumer_atom',pivot)]),'foreign_mapped_receipt')
    fact=w['fact'];birth=w['birth_event'];require(sp['integer'](fact) and fact&0xffffffff==op and w['producer_epoch']==w['consumer_version']<w['consumer_epoch'] and w['producer_serial']!=w['consumer_serial'],'invalid_mapped_source_event')
    require(birth[0]=='birth' and birth[4]==fact and birth[5][1]==pi and sp['checked_i'](birth[1],list(source.tables),'unknown_birth_table')==proof['table'],'foreign_mapped_birth')
    relation='same_producer' if o['producer']['serial']==w['producer_serial'] else 'other_producer'
    require(mapped['donor_join']==relation,'wrong_donor_join')
    so={**o,'consumer':dict(source_name=cr['metadata']['name'],ruleset=cr['metadata']['source_set'])}
    bind_source_forms(profile,parts,source_dir,so)
    h=data['native/history.json']
    led=native['check_native'](source,so,profile,data['entry.egg'],data['native/ripen.json'],data['native/initial-state.json'],data['native/saturated-rule-composition.json'],h,data['native/acceptance.json'],proof,derived=True)
    require(mapped['operator']==led['table'] and mapped['argument_classes']==led['local_args'] and mapped['result_class']==led['local_result'],'foreign_mapped_row')
    require(any(y['producer_record']==loc['producer_record'] and y['consumer_record']==loc['consumer_record'] and y['write_read_token']==loc['token'] and y['producer_index']==loc['producer_index'] and y['consumer_index']==loc['consumer_index'] for y in led['native_consumer_reads']),'foreign_mapped_history')
    return dict(sample_id=sample['sample_id'],donor=name,static=proof,native=led,artifacts=ids,producer_input_proof=root,
                local_seed_producer_serial=o['producer']['serial'],corroborating_receipt=w,donor_join=relation,
                observation='native_local_writer_and_reader_plus_independent_original_source_receipt')

def edge(card):
    t=card['target'];return(t['producer_rule'],t['producer_op'],t['consumer_rule'])

def two_step_proofs(accepted):
    chains=defaultdict(list)
    for a in accepted:
        for b in accepted:
            aa,bb=a['original'],b['original']
            if not (a['donor']==b['donor'] and aa['consumer_serial']==bb['producer_serial'] and aa['consumer_ordinal']==bb['producer_ordinal'] and aa['consumer_run']==bb['producer_run'] and edge(a)[2]==edge(b)[0]):continue
            f=aa['result_fact']
            named={'atom':a['static']['pivot'],'row':{'Fact':{'cell':f>>32,'op':f&0xffffffff}},'version':aa['version']}
            if named in bb['producer_named']:
                chains[(edge(a),edge(b))].append([a['sample_id'],b['sample_id']])
    return [dict(path=[list(e) for e in path],sample_chains=refs)for path,refs in sorted(chains.items())]

def relink(card,recipe):
    q=card['static'];p,c=recipe.resolve(q['producer_schema']),recipe.resolve(q['consumer_schema'])
    actual=recipe.certify(p,q['producer_op'],c,q['pivot'])
    for k in ('table','sorts','producer_columns','consumer_slots','rhs_projections'):require(actual[k]==q[k],'target_projection_mismatch')
    card['target']=actual
    return list(edge(card))

def compile_library(evidence:Path,donors:dict,target:Path,*,source_dir:Path=SOURCE_DIR,trust_index:Path=TRUST):
    evidence=Path(evidence).resolve();raw=evidence.read_bytes();report=json.loads(raw)
    require(report.get('schema')=='eggfuse-ripsat-donor-evidence/v1','unsupported_evidence_schema')
    trust_raw=Path(trust_index).read_bytes();trust=json.loads(trust_raw)
    require(trust.get('schema')=='eggfuse-ripsat-donor-trust/v1','unknown_trust_index')
    require(trust['binary_sha256']==report['binary_sha256'],'foreign_native_binary')
    dest=Recipe(target);notes=[];accepted=[];weaker=[];independent=[];extras=[];seen=set();sources={};directories=report['donors']
    require(set(donors)==set(directories) and bool(donors),'donor_set_mismatch')
    blobs=json.loads((evidence.parent/'native-text.json').read_bytes()) if (evidence.parent/'native-text.json').is_file() and not (evidence.parent/'samples').exists() else None
    for name,doc in directories.items():
        src=Recipe(donors[name]);sources[name]=src.file_sha
        require(doc['program_sha256']==src.file_sha and trust['donors'].get(name,{}).get('program_sha256')==src.file_sha,'foreign_donor_program')
        require(doc['source_parts']==trust['donors'][name]['source_parts'] and doc['recipe_sha256']==trust['donors'][name]['recipe_sha256'],'foreign_donor_context')
        for sample in doc['samples']:
            ident=sample['sample_id']
            require(isinstance(ident,str) and ident not in seen,'duplicate_sample_id')
            seen.add(ident)
            try:
                require(ident in trust['samples'],'untrusted_sample_id')
                card=evidence_card(evidence.parent,sample,name,src,doc['source_parts'],Path(source_dir),trust['samples'][ident],blobs)
                wired=relink(card,dest)
                strength='locally_linked' if card['native']['native_consumer_reads'] else 'static_consumer_only'
                (accepted if strength=='locally_linked' else weaker).append(card)
                notes.append(dict(sample_id=ident,donor=name,status=strength,reason=None,target_edge=wired))
            except (Refusal,KeyError,ValueError,IndexError,TypeError,AttributeError) as bad:
                reason=str(bad) if isinstance(bad,Refusal) else 'invalid_evidence_structure'
                notes.append(dict(sample_id=ident,donor=name,status='rejected',reason=reason))
            # Rank-independent local applications; there may be a different
            # actual source occurrence corroborating the same portable edge.
            for mapped in sample.get('mapped_native_edges',[]):
                if mapped.get('nominated') or sample['scope_mode'] not in ('full','augmented'):continue
                diag=dict(sample_id=ident,donor=name)
                try:
                    card=local_extra(evidence.parent,sample,mapped,name,src,doc['source_parts'],Path(source_dir),trust['samples'][ident],blobs)
                    diag.update(status=card['donor_join'],target_edge=relink(card,dest))
                    independent.append(card)
                except (Refusal,KeyError,ValueError,IndexError,TypeError,AttributeError) as exc:
                    diag.update(status='rejected',reason=str(exc) if isinstance(exc,Refusal) else 'invalid_evidence_structure')
                extras.append(diag)
    proofs=defaultdict(list)
    for x in accepted:proofs[(edge(x),)].append([x['sample_id']])
    for chain in two_step_proofs(accepted):
        proofs[tuple(tuple(e)for e in chain['path'])]=chain['sample_chains']
    routes=sorted(proofs);weak=sorted({(edge(c),) for c in weaker})
    spec=lambda xs:dict(depth=max([len(x) for x in xs]or[1]),library=[[list(e)for e in path] for path in xs])
    return dict(schema='eggfuse-ripsat-strict-programs/v1',target_sha256=dest.file_sha,evidence_sha256=digest(raw),trust_index_sha256=digest(trust_raw),donor_sha256=sources,
                strict_named=spec(routes),library_sha256=sp['sha'](spec(routes)),strict_named_static_consumer=spec(weak),
                strict_named_independent_corroboration=spec(sorted({(edge(c),)for c in independent})),mapped_decisions=extras,independently_corroborated=independent,paths=[dict(path=[list(e)for e in p],sample_chains=proofs[p])for p in routes],
                decisions=notes,certificates=accepted,static_only=weaker,rejections=dict(Counter(x['reason'] for x in notes if x['status']=='rejected')),
                obligations=['producer must expose the authenticated fresh physical FactRef at the exact source operation','consume only in the original later Run at its watermark','recheck visible current source identity, table and version','original ordered RHS, mutation visibility, deduplication and union remain authoritative'])

def main():
    p=ArgumentParser(description=__doc__);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--donor',action='append',required=True)
    p.add_argument('--target',type=Path,required=True);p.add_argument('--source-dir',type=Path,default=SOURCE_DIR);p.add_argument('--out','--output',dest='out',type=Path,required=True)
    p.add_argument('--trust-index',type=Path,default=TRUST,help='Independent native receipt and original donor capture pins')
    a=p.parse_args();donors=dict(x.split('=',1) for x in a.donor)
    out=compile_library(a.evidence,donors,a.target,source_dir=a.source_dir,trust_index=a.trust_index)
    a.out.parent.mkdir(parents=True,exist_ok=True);tmp=a.out.with_suffix(a.out.suffix+'.tmp');tmp.write_text(json.dumps(out,indent=1)+'\n');tmp.replace(a.out)
    print('native linked / static-only / rejected',len(out['certificates']),len(out['static_only']),sum(out['rejections'].values()),'target programs',out['strict_named'])

if __name__=='__main__':main()
