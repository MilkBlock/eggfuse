"""Count actual incident donor links separately from matching signatures and exercise the production join."""
import argparse,copy,json
from collections import Counter
from pathlib import Path
from runpy import run_path
HERE=Path(__file__).resolve().parent
adapter=run_path(str(HERE.parent/'ripsat-strict-programs/compile.py'))

def info(a):
    src=a['sample'];return (src['producer']['rule'],src['producer_op'],src['consumer']['rule'])

def stages(samples):
    out=Counter()
    for a in samples:
        for b in samples:
            if info(a)[2]!=info(b)[0]:continue
            out['schema_adjacent']+=1
            if a['donor']!=b['donor']:continue
            out['same_donor_schema_adjacent']+=1
            old=a['sample'];new=b['sample'];u=old['consumer'];v=new['producer']
            if not all(u[k]==v[k] for k in ('ordinal','serial','epoch')):continue
            out['same_middle_occurrence']+=1
            fid=old['original_fact'];named={'atom':old['consumer_atom'],'row':{'Fact':{'cell':fid>>32,'op':fid&0xffffffff}},
                                            'version':old['original_version']}
            if any(row['named']==named for row in v['rows']):out['same_middle_and_input_ref']+=1
    return {key:out[key] for key in ('schema_adjacent','same_donor_schema_adjacent','same_middle_occurrence','same_middle_and_input_ref')}

def join_controls(cards):
    join=adapter['two_step_proofs'];assert not join(cards)
    first=copy.deepcopy(cards[0]);second=copy.deepcopy(first)
    # Function-level positive sentinel only; this fabricated card is never passed to the admission compiler.
    first['sample_id']='fixture-first';second['sample_id']='fixture-second'
    second['target']['producer_rule']=first['target']['consumer_rule']
    second['target']['consumer_rule']=90
    a=first['original'];b=second['original']
    for k in ('serial','ordinal','run'):b['producer_'+k]=a['consumer_'+k]
    f=a['result_fact'];b['producer_named']=[{'atom':first['static']['pivot'],'row':{'Fact':{'cell':f>>32,'op':f&0xffffffff}},'version':a['version']}]
    pos=join([first,second]);assert len(pos)==1 and pos[0]['sample_chains']==[['fixture-first','fixture-second']]
    def adjust(x,keys,val):
        for i in keys[:-1]:x=x[i]
        x[keys[-1]]=val
    cases=(
       ('other-donor',['donor'],'foreign'),('other-serial',['original','producer_serial'],b['producer_serial']+1),
       ('other-ordinal',['original','producer_ordinal'],b['producer_ordinal']+1),
       ('other-run',['original','producer_run'],b['producer_run']+1),
       ('other-middle-schema',['target','producer_rule'],99999),
       ('absence-of-explicit-premise',['original','producer_named'],[]),
       ('different-slot',['original','producer_named',0,'atom'],first['static']['pivot']+1),
       ('different-source-cell',['original','producer_named',0,'row','Fact','cell'],(f>>32)+1),
       ('different-source-op',['original','producer_named',0,'row','Fact','op'],(f&0xffffffff)+1),
       ('different-version',['original','producer_named',0,'version'],a['version']+1))
    failures=[]
    for label,keys,v in cases:
        x=copy.deepcopy(second);adjust(x,keys,v)
        assert not join([first,x]),label
        failures.append(label)
    return {'synthetic_positive_paths':len(pos),'rejected_controls':failures,'genuine_two_step_paths':len(join(cards))}

def audit(evidence,donors,target):
    meta=json.loads(evidence.read_bytes());art=adapter['compile_library'](evidence,donors,target)
    default={c['sample_id'] for c in art['certificates']};statics={c['sample_id'] for c in art['static_only']}
    raw=[];local={}
    for donor,d in meta['donors'].items():
        for a in d['samples']:
            if a['scope_mode']!='full' or not a['native_accepted']:continue
            def read(name):return json.loads((evidence.parent/a['artifacts'][name]['path']).read_bytes())
            sample=read('origin.json')['sample'];sid=a['sample_id']
            row=dict(donor=donor,sample_id=sid,sample=sample,directed=bool(a['port_binding'].get('local_causal_edges')))
            raw.append(row)
            if sid not in default:continue
            h=read('native/history.json');records=h['records'];rules=h['rules'];pairs=[]
            for i,source in enumerate(records):
                if rules[source['rule']]['name']!=sample['producer']['source_name']:continue
                for j,middle in enumerate(records[i+1:],i+1):
                    if i not in middle['parents'] or rules[middle['rule']]['name']!=sample['consumer']['source_name']:continue
                    single=set(source['produced'])&set(middle['required'])
                    single=[t for t in single if h['tokens'][t]['sort']=='Fact:Single']
                    for k,tail in enumerate(records[j+1:],j+1):
                        if j not in tail['parents'] or rules[tail['rule']]['name']!=sample['producer']['source_name']:continue
                        get=[t for t in set(middle['produced'])&set(tail['required']) if h['tokens'][t]['sort']=='Fact:Get']
                        if len(single)==len(get)==1:pairs.append({'local_records':[source['id'],middle['id'],tail['id']],
                            'required_return_tokens':[single[0],get[0]],'local_record_indices':[i,j,k]})
            assert pairs
            local[donor]=dict(sample_id=sid,history_sha=a['artifacts']['native/history.json']['sha256'],triples=pairs)
    return {'strict_paths':art['strict_named']['library'],'strict_certificates':len(default),'static_only_paths':art['strict_named_static_consumer']['library'],
        'static_only_certificates':len(statics),'local_replay_triples':local,'catalog_counts':{
            'all_native_accepted_full_regions':stages(raw),
            'native_directed_edges_before_source_schema':stages([a for a in raw if a['directed']]),
            'default_strict_cards':stages([a for a in raw if a['sample_id'] in default]),
            'including_static_only_cards':stages([a for a in raw if a['sample_id'] in default|statics])},
        'production_join':join_controls(art['certificates'])}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('evidence','target','out'):p.add_argument(n,type=Path)
    p.add_argument('--donor',action='append',required=True);a=p.parse_args()
    donors={k:Path(v) for k,v in (s.split('=',1) for s in a.donor)}
    r=audit(a.evidence,donors,a.target);a.out.write_text(json.dumps(r,indent=2)+'\n')
    print(r['production_join'],r['catalog_counts'])
