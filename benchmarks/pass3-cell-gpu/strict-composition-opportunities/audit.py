"""Offline ownership-constrained composition audit. No plan or macro drives native execution."""
import argparse
from collections import Counter,defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from runpy import run_path

HERE=Path(__file__).resolve().parent
wave=run_path(str(HERE.parent/'verified-wave-execution/study.py'))
source=wave['source']
DONORS=('dot-product','jacobi-1d')
HOLDOUT=('sum-bits','3mm')


def digest(obj):
    return sha256(json.dumps(obj,sort_keys=True,separators=(',',':')).encode()).hexdigest()


@dataclass
class Root:
    serial:int
    ordinal:int
    rid:int
    run:int
    epoch:int
    provider:str
    named:dict
    complete:bool


def address(dep):
    if 'Fact' in dep:
        f=dep['Fact'];return 'Fact',(f['cell']<<32)|f['op']
    assert set(dep)=={'Function'}
    return 'Function',dep['Function']


def rule_id(r):
    return digest([r[k] for k in ('metadata','query','effects','slots','interface')])


def summarize(case,program,v,gold,exact_births,exact_state):
    exact=source.base.summarize(v,gold)
    assert exact['aligned'] and all(exact['checks'].values()) and v['state_sha']==exact_state
    r=v['root_recipe'];b=v['constructor_births']
    tables={t['name']:i for i,t in enumerate(program['recipe']['tables'])}
    rules=program['recipe']['rules'];names=[t['name'] for t in program['recipe']['tables']]
    types=[{i:tables[a['call']['table']] for i,a in enumerate(rule['query']) if 'table' in a['call']} for rule in rules]
    fingerprints=[rule_id(rule) for rule in rules]
    assert len(fingerprints)==len(set(fingerprints))
    schedule={step[1]:i+1 for i,step in enumerate(v['schedule'])}
    assert len(schedule)==v['runs']
    roots={};stats=Counter();parts=Counter();reasons=Counter();sample={}
    for ordinal,provider,serial,rid,template,epoch,refs,_ in r['commits']:
        named={}
        for ref in refs:
            i=ref['atom'];assert i in types[rid] and i not in named
            tag,refid=address(ref['row'])
            named[i]=(types[rid][i],tag,refid,ref['version'])
        resolved=set(named)==types[rid].keys()
        root=Root(serial,ordinal,rid,schedule[epoch],epoch,provider,named,resolved)
        assert serial not in roots;roots[serial]=root
        stats['root_commits']+=1;stats['with_unprovided_table_atoms' if not resolved else 'all_table_atoms_named']+=1
    assert len(roots)==exact['rhs']
    loc_by_cell={x[0]:x[5] for x in r['fresh']}
    dyn_cells={x['allocated'] for x in v['merge_child']['issued'] if x['allocated'] is not None}
    native_births=[e for events in v['events'] for e in events if e[0]=='birth']
    assert digest(native_births)==exact_births
    native={e[4]:e for e in native_births};births={};visible={e[0] for e in b['endpoint'] if not e[2]}
    visible_by_root=Counter()
    for fid,t,ep,ctor,sid,_,_,flags in b['rows']:
        if not (ctor and flags&1 and sid):continue
        if fid in visible:visible_by_root[sid]+=1
        if flags&2 or fid>>32 in dyn_cells:
            stats['dynamic_or_child_births_excluded']+=1;continue
        owner=roots[sid];op=fid&0xffffffff
        assert owner.epoch==ep and loc_by_cell.get(fid>>32)==sid
        ef=rules[owner.rid]['effects'][op]
        assert ef['op'] in ('let','set') and ef['call']['table']==names[t]
        event=native[fid];assert event[1]==t and event[5][1]==owner.rid
        assert fid not in births;births[fid]=(t,sid,op,ep)
    assert len(native)==len(native_births)
    stats['eligible_typed_new_constructor_births']=len(births)
    tables_by_ref={serial:defaultdict(list) for serial in roots if roots[serial].complete and roots[serial].named}
    for serial,index in tables_by_ref.items():
        for atom,ref in roots[serial].named.items():index[ref].append(atom)
    pairs=Counter();chains=Counter();edge={};chain_ids=set();edge_ids=set()
    census=defaultdict(Counter);maps={}
    for child in roots.values():
        arity=len(types[child.rid]);kind='multi' if arity>=2 else 'unary' if arity==1 else 'ground'
        def decline(reason):
            census[kind][reason]+=1
        if not child.complete:decline('missing_named_child_table_atom');continue
        if arity==0:decline('no_table_parent');continue
        possible=set();same_run=False;wrong_version=False;source_not_named=False
        for table,tag,fid,version in child.named.values():
            if tag!='Fact' or fid not in births:continue
            t,serial,_,born=births[fid];assert t==table
            producer=roots[serial]
            if producer.run>=child.run or producer.ordinal>=child.ordinal:same_run=True;continue
            if version!=born:wrong_version=True;continue
            if not producer.complete:source_not_named=True;continue
            possible.add(serial)
        if not possible:
            decline('producer_has_unnamed_table_atom' if source_not_named else 'only_stale_birth' if wrong_version else 'no_earlier_source_run' if same_run else 'no_named_typed_birth');continue
        valid=[];ambiguous_port=False;stale=False
        for serial in sorted(possible):
            producer=roots[serial];index=tables_by_ref.get(serial,{})
            wires=[];uses_birth=False
            for i,key in sorted(child.named.items()):
                table,tag,fid,version=key;origin=births.get(fid) if tag=='Fact' else None
                choices=[('input',j) for j in index.get(key,())]
                if origin and origin[1]==serial and origin[3]==version:choices.append(('op',origin[2]));uses_birth=True
                if not choices:
                    stale|=any(k[:3]==key[:3] for k in index) or bool(origin and origin[1]==serial and origin[3]!=version)
                    break
                if len(choices)>1:ambiguous_port=True;break
                wires.append((i,*choices[0]))
            else:
                if uses_birth:valid.append((producer,tuple(wires)))
        if len(valid)!=1 or ambiguous_port:
            decline('ambiguous_owner_or_port' if len(valid)>1 or ambiguous_port else 'uncovered_or_stale_version' if stale else 'uncovered_other_table_parent');continue
        producer,wires=valid[0]
        delta=child.run-producer.run
        shape=(fingerprints[producer.rid],fingerprints[child.rid],delta,wires)
        sig=digest(shape);pairs[sig]+=1
        assert child.serial not in edge_ids;edge_ids.add(child.serial)
        edge[child.serial]=(producer.serial,sig)
        maps[sig]=[producer.rid,child.rid,delta,[list(x) for x in wires],arity]
        decline('unique_complete_direct_composition')
        parts['edge_multiple_distinct_physical_parents']+=int(len(set(child.named.values()))>=2)
        parts['edge_multiple_distinct_table_names']+=int(len(set(types[child.rid].values()))>=2)
        parts['edge_has_named_external_input']+=int(any(x[1]=='input' for x in wires))
        parts['edge_child_final_visible_constructors_including_nested']=parts.get('edge_child_final_visible_constructors_including_nested',0)+visible_by_root[child.serial]
        example_kind=kind+('_input_and_op' if any(w[1]=='input' for w in wires) else '_only_ops')
        def describe(rt):
            return dict(serial=rt.serial,ordinal=rt.ordinal,run=rt.run,epoch=rt.epoch,rule=rt.rid,provider=rt.provider,
                        source=rules[rt.rid]['metadata']['name'][:180],named=[[i,names[key[0]],*key[1:]] for i,key in sorted(rt.named.items())])
        if example_kind not in sample:
            sample[example_kind]=dict(producer=describe(producer),child=describe(child),wiring=wires,
                newly_born_evidence=[native[key[2]] for i,key in sorted(child.named.items()) if next(w for w in wires if w[0]==i)[1]=='op'])
    stats['pair_children']=len(edge_ids)
    for child_id,(parent_id,second) in edge.items():
        if parent_id not in edge:continue
        grand,first=edge[parent_id]
        key=digest([first,second]);chains[key]+=1;chain_ids.add(child_id)
        maps[key]=[first,second,len(types[roots[child_id].rid])]
        if 'three_member_chain' not in sample:
            sample['three_member_chain']={'serials':[grand,parent_id,child_id],'runs':[roots[s].run for s in (grand,parent_id,child_id)],
               'rules':[roots[s].rid for s in (grand,parent_id,child_id)],'edge_maps':[maps[first],maps[second]]}
    assert sum(pairs.values())==len(edge_ids) and sum(chains.values())==len(chain_ids)
    stats['chain_terminal_children']=len(chain_ids)
    parts['edge_strictly_new_child_births']=sum(owner in edge_ids for _,owner,_,_ in births.values())
    stats['strictly_new_typed_child_births_finally_visible']=sum(owner in edge_ids and fid in visible for fid,(_,owner,_,_) in births.items())
    assert sum(sum(c.values()) for c in census.values())==len(roots)
    return dict(workload=case,counts=dict(stats),parts=dict(parts),census={k:dict(c) for k,c in census.items()},
                pairs=dict(pairs),triples=dict(chains),shapes=maps,examples=sample,reference=dict(runs=v['runs'],rhs=exact['rhs'],state_sha=v['state_sha'],
                    checks=exact['checks'],commits=exact['commits'],physical=exact['physical'],ordered_source_birth_events=exact_births),
                pair_children_sha=digest(sorted(edge_ids)),chain_children_sha=digest(sorted(chain_ids)))


def aggregate(cases):
    summary={}
    for metric in ('pairs','triples'):
        donor=Counter();support=Counter()
        for case in DONORS:
            c=Counter(cases[case][metric]);donor.update(c);support.update(c.keys())
        sets={'seen':set(donor),'repeated':{k for k,v in donor.items() if v>=2},'both_donors':{k for k,v in support.items() if v==2}}
        values={}
        for policy,selected in sets.items():
            values[policy]={'shapes':len(selected),'donor_occurrences':sum(donor[k] for k in selected),'heldout':{}}
            for case in HOLDOUT:
                counts=cases[case][metric];by_kind=Counter()
                for k in selected&counts.keys():by_kind['multi' if cases[case]['shapes'][k][-1]>=2 else 'unary']+=counts[k]
                values[policy]['heldout'][case]=dict(by_kind)
        summary[metric]=values
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('exp','native','out'):p.add_argument(k,type=Path)
    a=p.parse_args();a.seed=1703;a.cap=8192
    a.policy=json.loads((HERE.parent/'speculative-allocation-policy/policy.json').read_bytes());a.fraction=json.loads((HERE.parent/'wave-demand-policy/policy.json').read_bytes())['models']['fraction']
    a.out.mkdir(parents=True,exist_ok=False);cases={}
    for case in (*DONORS,*HOLDOUT):
        program,plans,req=source.common.config(a,case);pr=json.loads(program.read_bytes())
        with source.base.session(a.exp/'compact-vanilla-20261121/vanilla-audit',program) as ref:gold=ref({'audit':True})
        with source.base.session(a.native,program,plans) as run:
            exact=run({'baseline':True,'audit':True,'birth_ledger':True})
            source_events=[e for events in exact['events'] for e in events if e[0]=='birth']
            source_births=digest(source_events);source_state=exact['state_sha'];del exact,source_events
            v=run(dict(wave['settings'](req,a)['packed'],audit=True,birth_ledger=True))
            cases[case]=summarize(case,pr,v,gold,source_births,source_state);del v,gold
        (a.out/(case+'.json')).write_text(json.dumps(cases[case],indent=1)+'\n')
        print(case,cases[case]['counts'],cases[case]['census'].get('multi'),flush=True)
    (a.out/'transfer.json').write_text(json.dumps(aggregate(cases),indent=1)+'\n')
if __name__=='__main__':main()
