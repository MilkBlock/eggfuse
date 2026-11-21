"""Exercise the newer publication-ABI's independent source and native triple obligations."""
import argparse,copy,json
from pathlib import Path
from runpy import run_path
HERE=Path(__file__).resolve().parent
module=run_path(str(HERE.parent/'ripsat-publication-chain/authorize.py'))
old=module['base'];read=module['read']

def rejected(f):
    try:f()
    except ValueError as e:return str(e)
    raise AssertionError('invalid publication chain passed')

def run(a):
    donors={k:Path(p) for k,p in (v.split('=',1)for v in a.donor)}
    artifact=module['authorize'](a.evidence,donors,a.target)
    assert artifact==read(a.authorized)
    spec=artifact['strict_named'];assert spec['library']==[[[143,1,55]]] and spec['set_publication']['path']==[[143,1,55],[55,1,143]]
    base=old['compile_library'](a.evidence,donors,a.target)
    assert base['strict_named']['library']==[[[143,1,55]]] and not old['two_step_proofs'](base['certificates'])
    sid='dot-product-p143-o1-c55-full';first=next(c for c in base['certificates'] if c['sample_id']==sid)
    record=read(HERE/'dot-product-same-middle.json');s=record['first_origin_sample']
    recipe=module['Recipe'](donors['dot-product'])
    static=module['set_contract'](recipe,55,1,143,0)
    orig=module['check_source_occurrence'](s,record,first,recipe,static)
    assert orig['serials']==[1737,1822,2625] and orig['second_port']==[4170413244417,135]
    idx=next(x for x in read(a.evidence)['donors']['dot-product']['samples']if x['sample_id']==sid)
    raw,_=old['read_artifacts'](a.evidence.parent,idx)
    local=module['check_history'](raw,first,static);assert local['local_record_ids']==[0,8,12] and local['tokens']==[6,10]
    controls={}
    def source_fault(name,mutate):
        copy_record=copy.deepcopy(record);mutate(copy_record)
        controls[name]=rejected(lambda:module['check_source_occurrence'](s,copy_record,first,recipe,static))
    source_fault('different_committed_middle',lambda c:c['companions'][0]['producer'].__setitem__('serial',1605))
    source_fault('terminal_already_internal',lambda c:c['later_143_internal_serials'].append(2625))
    source_fault('different_set_fact',lambda c:c.__setitem__('middle_set_fact',c['middle_set_fact']+(1<<32)))
    source_fault('different_set_version',lambda c:c.__setitem__('set_version',c['set_version']+1))
    source_fault('different_actual_middle_port',lambda c:c['middle_signed_trail'][3][0].__setitem__(1,0))
    source_fault('different_terminal_release',lambda c:c['companions'][0].__setitem__('relative_runs',1))
    source_fault('different_terminal_ref',lambda c:c['companions'][0]['consumer']['rows'][0]['named']['row']['Fact'].__setitem__('cell',970))
    def replace_birth(c):
        c['middle_set_birth_event'][0]='union'
        c['companions'][0]['birth_event'][0]='union'
    source_fault('union_masquerades_as_birth',replace_birth)
    def invert_columns(c):
        c['middle_set_birth_event'][2].reverse();c['companions'][0]['birth_event'][2].reverse()
    source_fault('set_assignment_columns_permuted',invert_columns)
    def local_fault(name,mutate):
        r=copy.deepcopy(raw);mutate(r['native/history.json']['records'])
        controls[name]=rejected(lambda:module['check_history'](r,first,static))
    local_fault('terminal_reads_another_fact',lambda rows:rows[2]['required'].__setitem__(0,rows[0]['produced'][0]))
    local_fault('terminal_not_connected_to_middle',lambda rows:rows[2].__setitem__('parents',[]))
    local_fault('no_middle_Get_publication',lambda rows:rows[1].__setitem__('produced',[]))
    local_fault('foreign_first_parent_of_middle',lambda rows:rows[1].__setitem__('parents',[]))
    controls['Set_as_returning_Let']=rejected(lambda:recipe.certify(55,1,143,0))
    controls['Set_wrong_operation']=rejected(lambda:module['set_contract'](recipe,55,0,143,0))
    return {'source_serials':orig['serials'],'source_ports':[orig['first_port'],orig['second_port']],
            'local_records':local['local_record_ids'],'local_fact_tokens':local['tokens'],'faults':controls}
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('evidence','target','authorized','out'):p.add_argument(k,type=Path)
    p.add_argument('--donor',action='append',required=True);a=p.parse_args()
    r=run(a);a.out.write_text(json.dumps(r,indent=2)+'\n');print(len(r['faults']),'publication source, native history and ABI proof controls refused.')
