"""Independently perturb the upper evidence envelope and underlying occurrence/SSA contracts."""
from argparse import ArgumentParser
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from authorize import HERE,V2,ACCEPT,Recipe,Refusal,base,read,authorize,load_checked,set_contract,check_history,check_source_occurrence

def refused(label,fn,expected,log):
    try:fn()
    except Refusal as e:
        assert str(e)==expected,(label,str(e),expected)
        log[label]=str(e);return
    raise AssertionError('accepted '+label)


def main():
    p=ArgumentParser(description=__doc__);p.add_argument('exp',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();small=a.exp/'compact-holdouts-20261121-v1'
    donors={n:small/(n+'-1703')/'program.json' for n in ('dot-product','jacobi-1d')}
    evidence=V2/'evidence.json';ev=read(evidence);trust=read(V2/'trust.json');blobs=read(V2/'native-text.json')
    target=a.exp/'extra-pass3-transfer-v1/3mm-1703/program.json';auth=authorize(evidence,donors,target)
    d='dot-product';recipe=Recipe(donors[d]);sample=next(s for s in ev['donors'][d]['samples'] if s['sample_id']==auth['support'][0]['sample_id'])
    pins=trust['samples'][sample['sample_id']];data,_=base['authenticated'](V2,sample,pins,blobs)
    first=base['evidence_card'](V2,sample,d,recipe,ev['donors'][d]['source_parts'],base['SOURCE_DIR'],pins,blobs)
    orig=data['origin.json']['sample'];comp=read(ACCEPT/'dot-product-same-middle.json');sta=set_contract(recipe,55,1,143,0)
    assert check_source_occurrence(orig,comp,first,recipe,sta)==auth['support'][0]['source']
    assert check_history(data,first,sta)==auth['support'][0]['native']
    out={}
    bad=deepcopy(comp);bad['companions'][0]['producer']['serial']+=1
    refused('different_same_schema_middle',lambda:check_source_occurrence(orig,bad,first,recipe,sta),'middle_occurrence_mismatch',out)
    bad=deepcopy(comp);bad['middle_signed_trail'][3][0][2]+=1
    refused('first_step_stale_physical_port',lambda:check_source_occurrence(orig,bad,first,recipe,sta),'wrong_signed_first_step',out)
    bad=deepcopy(comp);bad['companions'][0]['consumer']['rows'][0]['named']['version']+=1
    term=bad['companions'][0]['consumer'];bad['original_committed_roots'][str(term['serial'])]['refs']=[r['named'] for r in term['rows']]
    refused('stale_terminal_physical_parent',lambda:check_source_occurrence(orig,bad,first,recipe,sta),'terminal_did_not_read_fresh_set_fact',out)
    bad=deepcopy(comp);bad['companions'][0]['birth_event'][2][1]['Int']=1;bad['middle_set_birth_event']=bad['companions'][0]['birth_event']
    refused('changed_set_key_same_fact_id',lambda:check_source_occurrence(orig,bad,first,recipe,sta),'set_keys_or_value_not_causal',out)
    bad=deepcopy(comp);bad['later_143_internal_serials']=[2625]
    refused('already_internal_terminal',lambda:check_source_occurrence(orig,bad,first,recipe,sta),'terminal_not_a_real_separate_external_proposal',out)
    bad=deepcopy(data);bad['native/history.json']['records'][2]['parents']=[]
    refused('no_second_raw_dependency',lambda:check_history(bad,first,sta),'missing_or_ambiguous_same_history_terminal',out)
    bad=deepcopy(data);rec=bad['native/history.json']['records'][2]
    pos=auth['support'][0]['native']['terminal_read']['position'];old=rec['ports'][pos];rec['ports'][pos]={'Parent':[old['Parent'][0],0]}
    refused('different_output_on_same_middle_record',lambda:check_history(bad,first,sta),'wrong_same_record_terminal_port',out)
    bad=deepcopy(data);bad['native/history.json']['records'][1]['produced']=[]
    refused('middle_only_reused_row',lambda:check_history(bad,first,sta),'history_did_not_emit_exact_typed_row',out)
    refused('ordinary_let_adapter_receives_set',lambda:recipe.certify(55,1,143,0),'not_a_returning_constructor',out)
    with TemporaryDirectory() as tmp:
        tmp=Path(tmp)
        j=read(target);j['known_results']['static_aliases'].remove({'rule':55,'operation':0,'dst':2,'value':{'slot':1}})
        path=tmp/'target.json';path.write_text(json.dumps(j))
        refused('target_lacks_elided_return_certificate',lambda:set_contract(Recipe(path),55,1,143,0),'missing_source_alias_proof',out)
        cp=read(ACCEPT/'companion-pins.json');fake=tmp/'comp';fake.mkdir()
        for donor,rec in cp.items():
            (fake/rec['file']).write_bytes((ACCEPT/rec['file']).read_bytes())
        foreign=deepcopy(comp);foreign['companions'][0]['consumer']['epoch']+=1
        (fake/cp['dot-product']['file']).write_text(json.dumps(foreign))
        refused('edited_independent_donor_file',lambda:authorize(evidence,donors,target,companion_dir=fake),'foreign_independent_source_receipt',out)
        bad=deepcopy(auth);bad['strict_named']['set_publication']['kinds'][1]='fresh_constructor_let'
        path=tmp/'artifact.json';path.write_text(json.dumps(bad))
        refused('cached_set_retyped_as_let',lambda:load_checked(path,evidence,donors,target),'cached_publication_certificate_differs_from_proof',out)
    a.output.write_text(json.dumps(out,indent=1)+'\n');print('Passed',len(out),'publication-chain controls')
if __name__=='__main__':main()
